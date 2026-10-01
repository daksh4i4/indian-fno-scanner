import os
import time
import hashlib
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import requests
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from strategy import ScannerEngine, DEFAULT_SETTINGS


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

APP_NAME = "Indian F&O Scanner"

GROWW_API_KEY = os.getenv("GROWW_API_KEY", "").strip()
GROWW_API_SECRET = os.getenv("GROWW_API_SECRET", "").strip()

GROWW_BASE_URL = "https://api.groww.in"
GROWW_TOKEN_URL = f"{GROWW_BASE_URL}/v1/token/api/access"
GROWW_HISTORICAL_URL = f"{GROWW_BASE_URL}/v1/historical/candles"
GROWW_LTP_URL = f"{GROWW_BASE_URL}/v1/live-data/ltp"

INSTRUMENT_CSV_URL = (
    "https://growwapi-assets.groww.in/instruments/instrument.csv"
)

HISTORY_REFRESH_SECONDS = 60
LTP_REFRESH_SECONDS = 5

# We analyze equity/CASH candles for the underlying F&O stocks.
# The universe itself is restricted to stocks which have NSE F&O contracts.
HISTORY_SEGMENT = "CASH"

# Maximum safe-ish windows for requesting history.
HISTORY_WINDOWS = {
    "1m": 7,
    "2m": 7,
    "3m": 7,
    "5m": 15,
    "10m": 30,
    "15m": 30,
    "30m": 60,
    "1h": 120,
    "4h": 365,
    "1d": 1080,
    "1w": 3650,
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(APP_NAME)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version="4.0",
)


# ============================================================
# GLOBAL STATE
# ============================================================

STATE: Dict[str, Any] = {
    "access_token": None,
    "token_created_at": None,

    "authenticated": False,

    "instruments_loaded": False,
    "fno_stock_count": 0,

    "history_loaded": 0,
    "history_failed": 0,

    "last_history_update": None,
    "last_ltp_update": None,

    "last_error": None,

    "market_status": "STARTING",

    "fno_stocks": [],
}

STATE_LOCK = threading.Lock()

INSTRUMENTS_DF: Optional[pd.DataFrame] = None

# symbol -> metadata
FNO_STOCKS: Dict[str, Dict[str, Any]] = {}

# symbol -> cash groww symbol
CASH_SYMBOLS: Dict[str, str] = {}

# symbol -> historical dataframe by timeframe
HISTORY: Dict[str, Dict[str, pd.DataFrame]] = {}

# symbol -> latest LTP
LIVE_LTP: Dict[str, float] = {}

# last history fetch timestamp
HISTORY_FETCH_TIME: Dict[str, float] = {}


# ============================================================
# STRATEGY ENGINE
# ============================================================

ENGINE = ScannerEngine(
    settings=dict(DEFAULT_SETTINGS)
)


# ============================================================
# TIMEFRAME MAP
# ============================================================

GROWW_INTERVALS = {
    "1m": "1minute",
    "2m": "2minute",
    "3m": "3minute",
    "5m": "5minute",
    "10m": "10minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h": "1hour",
    "4h": "4hour",
    "1d": "1day",
    "1w": "1week",
}


def normalize_timeframe(value: Any, default: str = "5m") -> str:
    """
    Normalize dashboard timeframe values.
    """

    if value is None:
        return default

    value = str(value).strip().lower()

    aliases = {
        "1min": "1m",
        "1minute": "1m",
        "2min": "2m",
        "2minute": "2m",
        "3min": "3m",
        "3minute": "3m",
        "5min": "5m",
        "5minute": "5m",
        "10min": "10m",
        "10minute": "10m",
        "15min": "15m",
        "15minute": "15m",
        "30min": "30m",
        "30minute": "30m",
        "60min": "1h",
        "60minute": "1h",
        "1hour": "1h",
        "4hour": "4h",
        "1day": "1d",
        "daily": "1d",
        "1week": "1w",
        "weekly": "1w",
    }

    return aliases.get(value, value if value in GROWW_INTERVALS else default)


# ============================================================
# GROWW AUTHENTICATION
# ============================================================

def generate_access_token() -> str:
    """
    Generate Groww access token using API key + secret.

    Groww API Key + Secret approval flow:
        checksum = SHA256(secret + timestamp)
    """

    if not GROWW_API_KEY or not GROWW_API_SECRET:
        raise RuntimeError(
            "GROWW_API_KEY or GROWW_API_SECRET is missing."
        )

    timestamp = str(int(time.time()))

    checksum_input = (
        GROWW_API_SECRET + timestamp
    ).encode("utf-8")

    checksum = hashlib.sha256(
        checksum_input
    ).hexdigest()

    headers = {
        "Authorization": f"Bearer {GROWW_API_KEY}",
        "Accept": "application/json",
        "X-API-VERSION": "1.0",
        "Content-Type": "application/json",
    }

    payload = {
        "key_type": "approval",
        "checksum": checksum,
        "timestamp": timestamp,
    }

    response = requests.post(
        GROWW_TOKEN_URL,
        headers=headers,
        json=payload,
        timeout=20,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Groww token HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    data = response.json()

    if data.get("status") != "SUCCESS":
        raise RuntimeError(
            f"Groww token failed: {data}"
        )

    payload_data = data.get("payload", {})

    token = (
        payload_data.get("access_token")
        or payload_data.get("token")
    )

    if not token:
        raise RuntimeError(
            f"Groww token missing in response: {data}"
        )

    with STATE_LOCK:
        STATE["access_token"] = token
        STATE["token_created_at"] = datetime.utcnow().isoformat()
        STATE["authenticated"] = True
        STATE["last_error"] = None

    logger.info("Groww API authentication successful.")

    return token


def get_access_token(force: bool = False) -> str:
    """
    Return cached token.
    Generate a new one when necessary.
    """

    with STATE_LOCK:
        token = STATE.get("access_token")

    if token and not force:
        return token

    return generate_access_token()


# ============================================================
# GROWW HEADERS
# ============================================================

def groww_headers() -> Dict[str, str]:
    """
    Headers required by current Groww API.
    """

    token = get_access_token()

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-API-VERSION": "1.0",
    }


# ============================================================
# GENERIC GROWW GET
# ============================================================

def groww_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retry_auth: bool = True,
) -> Dict[str, Any]:

    try:

        response = requests.get(
            url,
            params=params,
            headers=groww_headers(),
            timeout=timeout,
        )

        # Access token may have expired.
        if response.status_code in (401, 403) and retry_auth:

            logger.warning(
                "Groww returned %s. Refreshing access token...",
                response.status_code,
            )

            get_access_token(force=True)

            response = requests.get(
                url,
                params=params,
                headers=groww_headers(),
                timeout=timeout,
            )

        if response.status_code != 200:

            try:
                error_body = response.json()
            except Exception:
                error_body = response.text

            raise RuntimeError(
                f"Groww HTTP {response.status_code}: "
                f"{error_body}"
            )

        data = response.json()

        if data.get("status") == "FAILURE":

            raise RuntimeError(
                f"Groww API failure: {data}"
            )

        return data

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Groww network error: {exc}"
        ) from exc


# ============================================================
# LOAD INSTRUMENTS
# ============================================================

def load_instruments() -> pd.DataFrame:

    global INSTRUMENTS_DF

    logger.info("Downloading Groww instrument CSV...")

    response = requests.get(
        INSTRUMENT_CSV_URL,
        timeout=60,
    )

    response.raise_for_status()

    from io import StringIO

    df = pd.read_csv(
        StringIO(response.text),
        low_memory=False,
    )

    # Normalize column names.
    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    logger.info(
        "Instrument CSV loaded: %s rows",
        len(df),
    )

    INSTRUMENTS_DF = df

    return df


# ============================================================
# BUILD F&O STOCK UNIVERSE
# ============================================================

def build_fno_stock_universe(
    df: pd.DataFrame,
) -> Dict[str, Dict[str, Any]]:

    required = {
        "exchange",
        "segment",
        "trading_symbol",
    }

    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            f"Instrument CSV missing columns: {missing}"
        )

    work = df.copy()

    work["exchange"] = (
        work["exchange"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    work["segment"] = (
        work["segment"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    work["trading_symbol"] = (
        work["trading_symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # --------------------------------------------------------
    # Find NSE FNO instruments.
    # --------------------------------------------------------

    fno = work[
        (work["exchange"] == "NSE")
        & (work["segment"] == "FNO")
    ].copy()

    if fno.empty:
        raise RuntimeError(
            "No NSE FNO instruments found in Groww instrument CSV."
        )

    # --------------------------------------------------------
    # Only individual stock underlyings.
    #
    # We exclude index derivatives such as:
    # NIFTY
    # BANKNIFTY
    # FINNIFTY
    # MIDCPNIFTY
    # NIFTYNXT50
    # etc.
    # --------------------------------------------------------

    index_symbols = {
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY",
        "MIDCPNIFTY",
        "NIFTYNXT50",
        "NIFTYIT",
        "NIFTYPHARMA",
        "NIFTYAUTO",
        "NIFTYFMCG",
        "NIFTYMETAL",
        "NIFTYREALTY",
        "NIFTYENERGY",
        "NIFTYINFRA",
        "NIFTYMIDCAP",
        "NIFTYSMALLCAP",
        "NIFTYCOMMODITIES",
        "NIFTYCONSUMPTION",
        "NIFTYCPSE",
        "NIFTYDIVOPP50",
        "NIFTY100",
        "NIFTY200",
        "NIFTY500",
    }

    universe: Dict[str, Dict[str, Any]] = {}

    # Prefer underlying_symbol where available.
    if "underlying_symbol" in fno.columns:

        fno["underlying_symbol_clean"] = (
            fno["underlying_symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        fno["underlying_symbol_clean"] = (
            fno["underlying_symbol_clean"]
            .replace(
                {
                    "NAN": "",
                    "NONE": "",
                    "NA": "",
                }
            )
        )

    else:

        fno["underlying_symbol_clean"] = ""

    for _, row in fno.iterrows():

        symbol = str(
            row.get("underlying_symbol_clean", "")
        ).strip()

        trading_symbol = str(
            row.get("trading_symbol", "")
        ).strip()

        # Fallback when underlying_symbol is absent.
        if not symbol:

            symbol = trading_symbol

            # Remove common FUT suffix/pattern.
            for suffix in (
                "FUT",
            ):
                if symbol.endswith(suffix):
                    symbol = symbol[:-len(suffix)]

        if not symbol:
            continue

        if symbol in index_symbols:
            continue

        # Ignore malformed derivative rows.
        if symbol in {
            "NAN",
            "NONE",
            "NULL",
        }:
            continue

        if symbol not in universe:

            universe[symbol] = {
                "symbol": symbol,
                "name": str(
                    row.get("name", symbol)
                ),
                "exchange": "NSE",
                "segment": "FNO",
                "fno_trading_symbol": trading_symbol,
                "lot_size": safe_number(
                    row.get("lot_size")
                ),
                "expiry_date": safe_string(
                    row.get("expiry_date")
                ),
            }

    logger.info(
        "NSE F&O stock universe created: %s stocks",
        len(universe),
    )

    return universe


# ============================================================
# FIND CASH SYMBOL
# ============================================================

def build_cash_symbol_map(
    df: pd.DataFrame,
    universe: Dict[str, Dict[str, Any]],
) -> Dict[str, str]:

    result = {}

    cash = df[
        (df["exchange"].astype(str).str.upper() == "NSE")
        & (df["segment"].astype(str).str.upper() == "CASH")
    ].copy()

    cash["trading_symbol"] = (
        cash["trading_symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    if "groww_symbol" in cash.columns:
        cash["groww_symbol"] = (
            cash["groww_symbol"]
            .astype(str)
            .str.strip()
        )

    for symbol in universe:

        matches = cash[
            cash["trading_symbol"] == symbol
        ]

        if matches.empty:
            # Groww stock symbols normally follow NSE-SYMBOL.
            result[symbol] = f"NSE-{symbol}"
            continue

        row = matches.iloc[0]

        groww_symbol = safe_string(
            row.get("groww_symbol")
        )

        if not groww_symbol:
            groww_symbol = f"NSE-{symbol}"

        result[symbol] = groww_symbol

    return result


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_number(value: Any) -> Optional[float]:

    try:

        if pd.isna(value):
            return None

    except Exception:
        pass

    try:
        return float(value)
    except Exception:
        return None


def safe_string(value: Any) -> str:

    try:

        if pd.isna(value):
            return ""

    except Exception:
        pass

    return str(value).strip()


# ============================================================
# HISTORICAL CANDLE PARSER
# ============================================================

def parse_groww_candles(
    data: Dict[str, Any],
) -> pd.DataFrame:

    payload = data.get("payload", {})

    candles = []

    if isinstance(payload, dict):

        candles = payload.get("candles", [])

    elif isinstance(payload, list):

        candles = payload

    if not candles:

        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
            ]
        )

    rows = []

    for candle in candles:

        # Typical Groww response:
        #
        # [
        #   timestamp,
        #   open,
        #   high,
        #   low,
        #   close,
        #   volume
        # ]
        #
        # Some FNO responses can also contain OI.

        if isinstance(candle, dict):

            timestamp = (
                candle.get("timestamp")
                or candle.get("time")
                or candle.get("ts")
            )

            open_price = (
                candle.get("open")
            )

            high_price = (
                candle.get("high")
            )

            low_price = (
                candle.get("low")
            )

            close_price = (
                candle.get("close")
            )

            volume = (
                candle.get("volume", 0)
            )

            oi = (
                candle.get("oi")
                or candle.get("open_interest")
            )

        elif isinstance(candle, (list, tuple)):

            if len(candle) < 5:
                continue

            timestamp = candle[0]
            open_price = candle[1]
            high_price = candle[2]
            low_price = candle[3]
            close_price = candle[4]

            volume = (
                candle[5]
                if len(candle) > 5
                else 0
            )

            oi = (
                candle[6]
                if len(candle) > 6
                else None
            )

        else:
            continue

        rows.append(
            {
                "timestamp": timestamp,
                "open": safe_number(open_price),
                "high": safe_number(high_price),
                "low": safe_number(low_price),
                "close": safe_number(close_price),
                "volume": safe_number(volume) or 0,
                "oi": safe_number(oi),
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        errors="coerce",
    )

    result = result.dropna(
        subset=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
        ]
    )

    result = result.sort_values(
        "timestamp"
    )

    result = result.drop_duplicates(
        subset=["timestamp"],
        keep="last",
    )

    result = result.reset_index(
        drop=True
    )

    return result


# ============================================================
# HISTORY WINDOW
# ============================================================

def history_start_end(
    timeframe: str,
):
    """
    Return start/end strings accepted by Groww.
    """

    days = HISTORY_WINDOWS.get(
        timeframe,
        30,
    )

    end = datetime.now()

    start = end - timedelta(
        days=days
    )

    # Groww accepts:
    # yyyy-MM-dd HH:mm:ss
    start_str = start.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    end_str = end.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return start_str, end_str


# ============================================================
# FETCH HISTORY
# ============================================================

def fetch_history(
    symbol: str,
    timeframe: str,
    force: bool = False,
) -> pd.DataFrame:

    timeframe = normalize_timeframe(
        timeframe
    )

    interval = GROWW_INTERVALS.get(
        timeframe
    )

    if not interval:
        raise RuntimeError(
            f"Unsupported timeframe: {timeframe}"
        )

    cache_key = f"{symbol}:{timeframe}"

    now = time.time()

    if not force:

        last_fetch = HISTORY_FETCH_TIME.get(
            cache_key,
            0,
        )

        # Avoid hammering historical API.
        if now - last_fetch < HISTORY_REFRESH_SECONDS:

            existing = HISTORY.get(
                symbol,
                {}
            ).get(timeframe)

            if existing is not None:
                return existing

    groww_symbol = CASH_SYMBOLS.get(
        symbol,
        f"NSE-{symbol}",
    )

    start_time, end_time = history_start_end(
        timeframe
    )

    params = {
        "exchange": "NSE",
        "segment": HISTORY_SEGMENT,
        "groww_symbol": groww_symbol,
        "start_time": start_time,
        "end_time": end_time,
        "candle_interval": interval,
    }

    logger.info(
        "History request | %s | %s | %s",
        symbol,
        groww_symbol,
        timeframe,
    )

    try:

        data = groww_get(
            GROWW_HISTORICAL_URL,
            params=params,
            timeout=40,
        )

        candles = parse_groww_candles(
            data
        )

        if candles.empty:

            raise RuntimeError(
                "Groww returned zero candles."
            )

        HISTORY.setdefault(
            symbol,
            {}
        )[timeframe] = candles

        HISTORY_FETCH_TIME[
            cache_key
        ] = time.time()

        return candles

    except Exception as exc:

        logger.error(
            "History error | %s | %s | %s | %s",
            symbol,
            groww_symbol,
            timeframe,
            exc,
        )

        with STATE_LOCK:
            STATE["last_error"] = str(exc)

        raise


# ============================================================
# GET LIVE LTP
# ============================================================

def fetch_ltp_batch(
    symbols: List[str],
) -> Dict[str, float]:

    if not symbols:
        return {}

    result: Dict[str, float] = {}

    # Groww allows up to 50 instruments per LTP request.
    for start in range(
        0,
        len(symbols),
        50,
    ):

        batch = symbols[
            start:start + 50
        ]

        exchange_symbols = ",".join(
            f"NSE_{symbol}"
            for symbol in batch
        )

        params = {
            "segment": "CASH",
            "exchange_symbols": exchange_symbols,
        }

        try:

            data = groww_get(
                GROWW_LTP_URL,
                params=params,
                timeout=20,
            )

            payload = data.get(
                "payload",
                {}
            )

            if isinstance(payload, dict):

                for key, value in payload.items():

                    # NSE_RELIANCE -> RELIANCE
                    symbol = key

                    if symbol.startswith(
                        "NSE_"
                    ):
                        symbol = symbol[4:]

                    price = safe_number(
                        value
                    )

                    if price is not None:
                        result[symbol] = price

        except Exception as exc:

            logger.error(
                "LTP batch error: %s",
                exc,
            )

            with STATE_LOCK:
                STATE["last_error"] = str(exc)

        # Small delay between batches.
        time.sleep(0.10)

    return result


# ============================================================
# UPDATE LIVE PRICES
# ============================================================

def update_live_prices():

    symbols = list(
        FNO_STOCKS.keys()
    )

    if not symbols:
        return

    ltp_data = fetch_ltp_batch(
        symbols
    )

    if ltp_data:

        LIVE_LTP.update(
            ltp_data
        )

        with STATE_LOCK:
            STATE["last_ltp_update"] = (
                datetime.utcnow().isoformat()
            )


# ============================================================
# LOAD HISTORY FOR ONE STOCK
# ============================================================

def load_stock_history(
    symbol: str,
    settings: Dict[str, Any],
):

    entry_tf = normalize_timeframe(
        settings.get(
            "entry_timeframe",
            "5m",
        ),
        "5m",
    )

    wave_tf = normalize_timeframe(
        settings.get(
            "wave_timeframe",
            "15m",
        ),
        "15m",
    )

    tide_tf = normalize_timeframe(
        settings.get(
            "tide_timeframe",
            "1h",
        ),
        "1h",
    )

    timeframes = []

    for tf in (
        entry_tf,
        wave_tf,
        tide_tf,
    ):

        if tf not in timeframes:
            timeframes.append(tf)

    success = 0

    for tf in timeframes:

        try:

            df = fetch_history(
                symbol,
                tf,
                force=True,
            )

            if df is not None and not df.empty:
                success += 1

        except Exception:
            continue

    return success, len(timeframes)


# ============================================================
# INITIAL HISTORY LOAD
# ============================================================

def load_all_history(
    settings: Optional[Dict[str, Any]] = None,
):

    if settings is None:
        settings = ENGINE.settings

    symbols = list(
        FNO_STOCKS.keys()
    )

    total_success = 0
    total_failed = 0

    logger.info(
        "Starting historical load for %s F&O stocks...",
        len(symbols),
    )

    for index, symbol in enumerate(
        symbols,
        start=1,
    ):

        try:

            success, total = load_stock_history(
                symbol,
                settings,
            )

            if success > 0:
                total_success += 1
            else:
                total_failed += 1

        except Exception as exc:

            total_failed += 1

            logger.error(
                "Stock history failed | %s | %s",
                symbol,
                exc,
            )

        # Keep API requests controlled.
        time.sleep(0.05)

        if index % 10 == 0:

            logger.info(
                "History progress: %s/%s | loaded=%s failed=%s",
                index,
                len(symbols),
                total_success,
                total_failed,
            )

    with STATE_LOCK:

        STATE["history_loaded"] = total_success
        STATE["history_failed"] = total_failed
        STATE["last_history_update"] = (
            datetime.utcnow().isoformat()
        )

    logger.info(
        "Historical load complete | loaded=%s | failed=%s",
        total_success,
        total_failed,
    )


# ============================================================
# ENGINE HISTORY SYNC
# ============================================================

def sync_engine_history():

    """
    Send all loaded historical candles into strategy engine.
    """

    for symbol in list(
        FNO_STOCKS.keys()
    ):

        frames = HISTORY.get(
            symbol,
            {}
        )

        if not frames:
            continue

        try:

            # ScannerEngine in the current strategy.py
            # supports history storage through set_history().
            if hasattr(
                ENGINE,
                "set_history"
            ):

                ENGINE.set_history(
                    symbol,
                    frames,
                )

            elif hasattr(
                ENGINE,
                "histories"
            ):

                ENGINE.histories[
                    symbol
                ] = frames

        except Exception as exc:

            logger.warning(
                "Engine history sync error | %s | %s",
                symbol,
                exc,
            )


# ============================================================
# SCANNER SNAPSHOT
# ============================================================

def calculate_scanner():

    rows = []

    symbols = list(
        FNO_STOCKS.keys()
    )

    for symbol in symbols:

        meta = FNO_STOCKS.get(
            symbol,
            {}
        )

        price = LIVE_LTP.get(
            symbol
        )

        frames = HISTORY.get(
            symbol,
            {}
        )

        result = None

        try:

            # Preferred ScannerEngine API.
            if hasattr(
                ENGINE,
                "analyze_symbol"
            ):

                result = ENGINE.analyze_symbol(
                    symbol,
                    live_price=price,
                )

            elif hasattr(
                ENGINE,
                "scan_symbol"
            ):

                result = ENGINE.scan_symbol(
                    symbol,
                    live_price=price,
                )

            elif hasattr(
                ENGINE,
                "analyze"
            ):

                result = ENGINE.analyze(
                    symbol,
                    live_price=price,
                )

        except Exception as exc:

            logger.debug(
                "Strategy error | %s | %s",
                symbol,
                exc,
            )

        if not isinstance(
            result,
            dict
        ):

            result = {}

        # ----------------------------------------------------
        # Normalize strategy fields for dashboard.
        # ----------------------------------------------------

        signal = (
            result.get("signal")
            or result.get("Signal")
            or "WAIT"
        )

        score = result.get(
            "score"
        )

        wave = (
            result.get("wave")
            or result.get("wave_signal")
            or result.get("wave_direction")
            or "WAIT"
        )

        tide = (
            result.get("tide")
            or result.get("tide_signal")
            or result.get("tide_direction")
            or "WAIT"
        )

        entry = result.get(
            "entry"
        )

        stop_loss = (
            result.get("stop_loss")
            or result.get("sl")
        )

        target = result.get(
            "target"
        )

        rr = result.get(
            "rr"
        )

        confirmations = result.get(
            "confirmations"
        )

        row = {
            "symbol": symbol,
            "name": meta.get(
                "name",
                symbol,
            ),

            "price": (
                price
                if price is not None
                else result.get("price")
            ),

            "ltp": (
                price
                if price is not None
                else result.get("ltp")
            ),

            "signal": signal,
            "score": score,

            "wave": wave,
            "tide": tide,

            "entry": entry,
            "stop_loss": stop_loss,
            "sl": stop_loss,
            "target": target,
            "rr": rr,

            "confirmations": confirmations,

            "volume": result.get(
                "volume"
            ),

            "volume_sma": result.get(
                "volume_sma"
            ),

            "rsi": result.get(
                "rsi"
            ),

            "macd": result.get(
                "macd"
            ),

            "macd_signal": result.get(
                "macd_signal"
            ),

            "stochastic": result.get(
                "stochastic"
            ),

            "support": result.get(
                "support"
            ),

            "resistance": result.get(
                "resistance"
            ),

            "lot_size": meta.get(
                "lot_size"
            ),

            "exchange": "NSE",
            "segment": "FNO",

            "data_available": bool(
                frames
            ),

            "status": (
                "LIVE"
                if price is not None
                else "HISTORY"
                if frames
                else "NO DATA"
            ),
        }

        rows.append(row)

    # --------------------------------------------------------
    # Sort:
    # BUY first, SELL second, WAIT last.
    # Within same signal, higher score first.
    # --------------------------------------------------------

    signal_priority = {
        "BUY": 0,
        "SELL": 1,
        "WAIT": 2,
    }

    def sort_key(row):

        signal = str(
            row.get("signal", "WAIT")
        ).upper()

        score = safe_number(
            row.get("score")
        )

        if score is None:
            score = 0

        return (
            signal_priority.get(
                signal,
                3,
            ),
            -score,
            row.get(
                "symbol",
                "",
            ),
        )

    rows.sort(
        key=sort_key
    )

    return rows


# ============================================================
# BACKGROUND WORKER
# ============================================================

def scanner_worker():

    logger.info(
        "Scanner background worker starting..."
    )

    while True:

        try:

            # ----------------------------------------------
            # Refresh live prices.
            # ----------------------------------------------

            if FNO_STOCKS:

                update_live_prices()

            # ----------------------------------------------
            # Keep historical data reasonably fresh.
            # ----------------------------------------------

            now = time.time()

            needs_history = False

            if not HISTORY_FETCH_TIME:

                needs_history = True

            else:

                oldest = min(
                    HISTORY_FETCH_TIME.values()
                )

                if (
                    now - oldest
                    >= HISTORY_REFRESH_SECONDS
                ):
                    needs_history = True

            if needs_history:

                # Do not continuously reload all stocks
                # every 5 seconds.
                #
                # Only refresh after the configured interval.
                load_all_history(
                    ENGINE.settings
                )

                sync_engine_history()

            # ----------------------------------------------
            # Market status.
            # ----------------------------------------------

            with STATE_LOCK:

                if LIVE_LTP:
                    STATE[
                        "market_status"
                    ] = "LIVE"

                elif HISTORY:
                    STATE[
                        "market_status"
                    ] = "HISTORY"

                else:
                    STATE[
                        "market_status"
                    ] = "WAITING"

        except Exception as exc:

            logger.exception(
                "Scanner worker error"
            )

            with STATE_LOCK:
                STATE[
                    "last_error"
                ] = str(exc)

        time.sleep(
            LTP_REFRESH_SECONDS
        )


# ============================================================
# STARTUP INITIALIZATION
# ============================================================

def initialize_scanner():

    logger.info(
        "=============================================="
    )

    logger.info(
        "%s starting...",
        APP_NAME,
    )

    logger.info(
        "=============================================="
    )

    try:

        # ----------------------------------------------------
        # 1. Authentication
        # ----------------------------------------------------

        get_access_token()

        # ----------------------------------------------------
        # 2. Instruments
        # ----------------------------------------------------

        df = load_instruments()

        # ----------------------------------------------------
        # 3. F&O universe
        # ----------------------------------------------------

        universe = build_fno_stock_universe(
            df
        )

        cash_map = build_cash_symbol_map(
            df,
            universe,
        )

        FNO_STOCKS.clear()
        FNO_STOCKS.update(
            universe
        )

        CASH_SYMBOLS.clear()
        CASH_SYMBOLS.update(
            cash_map
        )

        with STATE_LOCK:

            STATE[
                "instruments_loaded"
            ] = True

            STATE[
                "fno_stock_count"
            ] = len(FNO_STOCKS)

            STATE[
                "fno_stocks"
            ] = list(
                FNO_STOCKS.keys()
            )

        logger.info(
            "F&O stock universe ready: %s",
            len(FNO_STOCKS),
        )

        # ----------------------------------------------------
        # 4. Load initial history
        # ----------------------------------------------------

        load_all_history(
            ENGINE.settings
        )

        sync_engine_history()

        # ----------------------------------------------------
        # 5. Initial LTP
        # ----------------------------------------------------

        update_live_prices()

        # ----------------------------------------------------
        # 6. Background worker
        # ----------------------------------------------------

        worker = threading.Thread(
            target=scanner_worker,
            daemon=True,
            name="scanner-worker",
        )

        worker.start()

        logger.info(
            "Scanner worker started."
        )

        logger.info(
            "Scanner initialization complete."
        )

    except Exception as exc:

        logger.exception(
            "Scanner initialization failed."
        )

        with STATE_LOCK:

            STATE[
                "authenticated"
            ] = False

            STATE[
                "last_error"
            ] = str(exc)

            STATE[
                "market_status"
            ] = "ERROR"


# ============================================================
# FASTAPI STARTUP
# ============================================================

@app.on_event("startup")
def startup_event():

    thread = threading.Thread(
        target=initialize_scanner,
        daemon=True,
        name="scanner-init",
    )

    thread.start()


# ============================================================
# API: HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": APP_NAME,
    }


# ============================================================
# API: STATUS
# ============================================================

@app.get("/api/status")
def api_status():

    with STATE_LOCK:

        return {
            "app": APP_NAME,

            "authenticated": STATE[
                "authenticated"
            ],

            "instruments_loaded": STATE[
                "instruments_loaded"
            ],

            "fno_stock_count": STATE[
                "fno_stock_count"
            ],

            "history_loaded": STATE[
                "history_loaded"
            ],

            "history_failed": STATE[
                "history_failed"
            ],

            "last_history_update": STATE[
                "last_history_update"
            ],

            "last_ltp_update": STATE[
                "last_ltp_update"
            ],

            "market_status": STATE[
                "market_status"
            ],

            "live_prices": len(
                LIVE_LTP
            ),

            "last_error": STATE[
                "last_error"
            ],

            "settings": dict(
                ENGINE.settings
            ),
        }


# ============================================================
# API: SCANNER
# ============================================================

@app.get("/api/scanner")
def api_scanner():

    try:

        rows = calculate_scanner()

        buy_count = sum(
            1
            for row in rows
            if str(
                row.get(
                    "signal",
                    "",
                )
            ).upper() == "BUY"
        )

        sell_count = sum(
            1
            for row in rows
            if str(
                row.get(
                    "signal",
                    "",
                )
            ).upper() == "SELL"
        )

        wait_count = len(
            rows
        ) - buy_count - sell_count

        return {
            "status": "success",

            "timestamp": datetime.utcnow().isoformat(),

            "count": len(rows),

            "summary": {
                "total": len(rows),
                "buy": buy_count,
                "sell": sell_count,
                "wait": wait_count,
            },

            "stocks": rows,
            "data": rows,
        }

    except Exception as exc:

        logger.exception(
            "Scanner API error"
        )

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(exc),
                "stocks": [],
                "data": [],
            },
        )


# ============================================================
# API: GET SETTINGS
# ============================================================

@app.get("/api/settings")
def get_settings():

    return {
        "status": "success",
        "settings": dict(
            ENGINE.settings
        ),
    }


# ============================================================
# API: UPDATE SETTINGS
# ============================================================

@app.post("/api/settings")
async def update_settings(
    payload: Dict[str, Any],
):

    try:

        incoming = (
            payload.get(
                "settings",
                payload,
            )
        )

        if not isinstance(
            incoming,
            dict,
        ):

            raise ValueError(
                "Settings must be an object."
            )

        # ----------------------------------------------------
        # Normalize timeframe values.
        # ----------------------------------------------------

        if "entry_timeframe" in incoming:

            incoming[
                "entry_timeframe"
            ] = normalize_timeframe(
                incoming[
                    "entry_timeframe"
                ],
                "5m",
            )

        if "wave_timeframe" in incoming:

            incoming[
                "wave_timeframe"
            ] = normalize_timeframe(
                incoming[
                    "wave_timeframe"
                ],
                "15m",
            )

        if "tide_timeframe" in incoming:

            incoming[
                "tide_timeframe"
            ] = normalize_timeframe(
                incoming[
                    "tide_timeframe"
                ],
                "1h",
            )

        # ----------------------------------------------------
        # Let strategy engine validate its settings.
        # ----------------------------------------------------

        if hasattr(
            ENGINE,
            "update_settings"
        ):

            ENGINE.update_settings(
                incoming
            )

        elif hasattr(
            ENGINE,
            "set_settings"
        ):

            ENGINE.set_settings(
                incoming
            )

        else:

            ENGINE.settings.update(
                incoming
            )

        logger.info(
            "Strategy settings updated: %s",
            ENGINE.settings,
        )

        # ----------------------------------------------------
        # Clear old history because timeframe can change.
        # ----------------------------------------------------

        HISTORY.clear()
        HISTORY_FETCH_TIME.clear()

        with STATE_LOCK:

            STATE[
                "history_loaded"
            ] = 0

            STATE[
                "history_failed"
            ] = 0

        # ----------------------------------------------------
        # Reload in background.
        # ----------------------------------------------------

        def reload_after_settings():

            try:

                load_all_history(
                    ENGINE.settings
                )

                sync_engine_history()

            except Exception as exc:

                logger.exception(
                    "History reload failed after settings change"
                )

                with STATE_LOCK:
                    STATE[
                        "last_error"
                    ] = str(exc)

        threading.Thread(
            target=reload_after_settings,
            daemon=True,
        ).start()

        return {
            "status": "success",
            "settings": dict(
                ENGINE.settings
            ),
        }

    except Exception as exc:

        logger.exception(
            "Settings update error"
        )

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(exc),
            },
        )


# ============================================================
# API: RESET / REFRESH
# ============================================================

@app.post("/api/reset")
def reset_scanner():

    try:

        HISTORY.clear()
        HISTORY_FETCH_TIME.clear()

        with STATE_LOCK:

            STATE[
                "history_loaded"
            ] = 0

            STATE[
                "history_failed"
            ] = 0

            STATE[
                "last_error"
            ] = None

        def reload():

            try:

                load_all_history(
                    ENGINE.settings
                )

                sync_engine_history()

                update_live_prices()

            except Exception as exc:

                logger.exception(
                    "Reset reload failed"
                )

                with STATE_LOCK:
                    STATE[
                        "last_error"
                    ] = str(exc)

        threading.Thread(
            target=reload,
            daemon=True,
        ).start()

        return {
            "status": "success",
            "message": "Scanner refresh started.",
        }

    except Exception as exc:

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(exc),
            },
        )


# ============================================================
# API: FORCE AUTH TEST
# ============================================================

@app.get("/api/groww-test")
def groww_test():

    try:

        token = get_access_token()

        return {
            "status": "success",
            "authenticated": bool(token),
            "message": "Groww API authentication is working.",
        }

    except Exception as exc:

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "authenticated": False,
                "message": str(exc),
            },
        )


# ============================================================
# API: F&O UNIVERSE
# ============================================================

@app.get("/api/universe")
def api_universe():

    stocks = []

    for symbol, meta in FNO_STOCKS.items():

        stocks.append(
            {
                "symbol": symbol,
                "name": meta.get(
                    "name",
                    symbol,
                ),
                "exchange": "NSE",
                "segment": "FNO",
                "cash_groww_symbol": CASH_SYMBOLS.get(
                    symbol,
                    f"NSE-{symbol}",
                ),
                "lot_size": meta.get(
                    "lot_size"
                ),
            }
        )

    stocks.sort(
        key=lambda x: x["symbol"]
    )

    return {
        "status": "success",
        "count": len(stocks),
        "stocks": stocks,
    }


# ============================================================
# STATIC FRONTEND
# ============================================================

if os.path.isdir("static"):

    app.mount(
        "/",
        StaticFiles(
            directory="static",
            html=True,
        ),
        name="static",
    )


# ============================================================
# LOCAL RUN SUPPORT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
