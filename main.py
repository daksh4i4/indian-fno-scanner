import os
import time
import hashlib
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

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

GROWW_API_KEY = os.getenv("GROWW_API_KEY", "").strip()
GROWW_API_SECRET = os.getenv("GROWW_API_SECRET", "").strip()

GROWW_BASE_URL = "https://api.groww.in"

TOKEN_URL = f"{GROWW_BASE_URL}/v1/token/api/access"
HISTORICAL_URL = f"{GROWW_BASE_URL}/v1/historical/candles"
LTP_URL = f"{GROWW_BASE_URL}/v1/live-data/ltp"
USER_DETAIL_URL = f"{GROWW_BASE_URL}/v1/user/detail"

INSTRUMENT_URL = (
    "https://growwapi-assets.groww.in/instruments/instrument.csv"
)

HISTORY_SEGMENT = "CASH"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("IndianFNOScanner")


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Indian F&O Scanner",
    version="2.0.0"
)


# ============================================================
# GLOBAL STATE
# ============================================================

STATE = {
    "app": "Indian F&O Scanner",

    "authenticated": False,
    "instruments_loaded": False,

    "fno_stock_count": 0,

    "history_loaded": 0,
    "history_failed": 0,

    "last_history_update": None,
    "last_ltp_update": None,

    "market_status": "STARTING",

    "live_prices": 0,

    "last_error": None,

    "token_expiry": None,
    "session_name": None,

    "fno_stocks": [],

    "scanner_running": False,
}


INSTRUMENTS_DF = pd.DataFrame()

FNO_STOCKS = []

CASH_SYMBOLS = {}

HISTORY = {}

LIVE_LTP = {}

HISTORY_FETCH_TIME = {}

STATE_LOCK = threading.Lock()


# ============================================================
# SETTINGS
# ============================================================

SETTINGS = dict(DEFAULT_SETTINGS)


# ============================================================
# TIMEFRAME MAP
# ============================================================

TIMEFRAME_MAP = {
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


# ============================================================
# HISTORY WINDOWS
# ============================================================

HISTORY_DAYS = {
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
# TOKEN GENERATION
# ============================================================

def generate_access_token() -> bool:

    global GROWW_API_KEY
    global GROWW_API_SECRET

    if not GROWW_API_KEY:
        raise RuntimeError("GROWW_API_KEY is missing.")

    if not GROWW_API_SECRET:
        raise RuntimeError("GROWW_API_SECRET is missing.")

    timestamp = str(int(time.time()))

    checksum_string = GROWW_API_SECRET + timestamp

    checksum = hashlib.sha256(
        checksum_string.encode("utf-8")
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

    logger.info("Requesting Groww access token...")

    response = requests.post(
        TOKEN_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    logger.info(
        "Groww token HTTP status: %s",
        response.status_code
    )

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code != 200:
        raise RuntimeError(
            f"Groww token HTTP {response.status_code}: "
            f"{str(data)[:500]}"
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # Groww returns token directly at top level.
    # --------------------------------------------------------

    token = data.get("token")

    # Compatibility fallback
    if not token:
        nested = data.get("payload")

        if isinstance(nested, dict):
            token = nested.get("token")

    if not token:
        raise RuntimeError(
            "Groww authentication response did not contain a token."
        )

    with STATE_LOCK:

        STATE["authenticated"] = True

        # NEVER expose token in dashboard/API
        STATE["token_expiry"] = data.get("expiry")

        STATE["session_name"] = data.get("sessionName")

        STATE["last_error"] = None

    # Store token internally only
    STATE["_access_token"] = token

    logger.info(
        "Groww authentication successful. Session=%s Expiry=%s",
        data.get("sessionName"),
        data.get("expiry"),
    )

    return True


# ============================================================
# AUTH HEADERS
# ============================================================

def groww_headers():

    token = STATE.get("_access_token")

    if not token:
        raise RuntimeError(
            "Groww access token is not available."
        )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-API-VERSION": "1.0",
    }


# ============================================================
# GROWw GET
# ============================================================

def groww_get(
    url: str,
    params: Optional[dict] = None,
    retry_auth: bool = True
):

    response = requests.get(
        url,
        headers=groww_headers(),
        params=params,
        timeout=30,
    )

    # Token may have expired
    if response.status_code in (401, 403):

        logger.warning(
            "Groww returned %s. Refreshing token...",
            response.status_code
        )

        if retry_auth:

            generate_access_token()

            response = requests.get(
                url,
                headers=groww_headers(),
                params=params,
                timeout=30,
            )

    return response


# ============================================================
# TEST AUTHENTICATION + USER DETAIL
# ============================================================

def test_groww_connection():

    generate_access_token()

    response = groww_get(
        USER_DETAIL_URL,
        retry_auth=False
    )

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code != 200:

        raise RuntimeError(
            f"Groww token generated but API test failed. "
            f"HTTP {response.status_code}: {str(data)[:500]}"
        )

    logger.info(
        "Groww user API test successful."
    )

    return data


# ============================================================
# LOAD GROWw INSTRUMENTS
# ============================================================

def load_instruments():

    global INSTRUMENTS_DF

    logger.info(
        "Downloading Groww instrument file..."
    )

    response = requests.get(
        INSTRUMENT_URL,
        timeout=60,
    )

    response.raise_for_status()

    from io import StringIO

    df = pd.read_csv(
        StringIO(response.text)
    )

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    INSTRUMENTS_DF = df

    STATE["instruments_loaded"] = True

    logger.info(
        "Instrument file loaded: %s rows",
        len(df)
    )

    return df


# ============================================================
# FIND COLUMN
# ============================================================

def find_column(df, names):

    for name in names:

        if name in df.columns:
            return name

    return None


# ============================================================
# BUILD F&O STOCK UNIVERSE
# ============================================================

def build_fno_stock_universe():

    global FNO_STOCKS

    df = INSTRUMENTS_DF.copy()

    if df.empty:
        raise RuntimeError(
            "Instrument file is empty."
        )

    exchange_col = find_column(
        df,
        [
            "exchange",
            "exchange_name",
        ]
    )

    segment_col = find_column(
        df,
        [
            "segment",
            "segment_name",
        ]
    )

    symbol_col = find_column(
        df,
        [
            "trading_symbol",
            "symbol",
            "tradingsymbol",
        ]
    )

    underlying_col = find_column(
        df,
        [
            "underlying_symbol",
            "underlying",
            "underlying_asset",
        ]
    )

    if not exchange_col:
        raise RuntimeError(
            "Exchange column not found in Groww instrument file."
        )

    if not segment_col:
        raise RuntimeError(
            "Segment column not found in Groww instrument file."
        )

    if not symbol_col:
        raise RuntimeError(
            "Trading symbol column not found."
        )

    temp = df.copy()

    temp[exchange_col] = (
        temp[exchange_col]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    temp[segment_col] = (
        temp[segment_col]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    fno = temp[
        (temp[exchange_col] == "NSE") &
        (
            temp[segment_col].str.contains(
                "FNO|NFO",
                regex=True,
                na=False
            )
        )
    ].copy()

    if fno.empty:

        # Compatibility if segment is simply "FNO"
        fno = temp[
            temp[segment_col] == "FNO"
        ].copy()

    stocks = set()

    for _, row in fno.iterrows():

        symbol = str(
            row.get(symbol_col, "")
        ).strip().upper()

        if not symbol:
            continue

        # Ignore obvious index contracts
        index_names = {
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
            "SENSEX",
        }

        if symbol in index_names:
            continue

        underlying = ""

        if underlying_col:
            underlying = str(
                row.get(
                    underlying_col,
                    ""
                )
            ).strip().upper()

        if underlying:

            # Ignore index underlyings
            if underlying in index_names:
                continue

            stocks.add(underlying)

        else:

            # Try to remove FUT suffix
            clean = symbol

            for suffix in [
                "FUT",
                "-FUT",
            ]:

                if clean.endswith(suffix):

                    clean = clean[:-len(suffix)]

            if clean:
                stocks.add(clean)

    FNO_STOCKS = sorted(stocks)

    STATE["fno_stock_count"] = len(FNO_STOCKS)

    STATE["fno_stocks"] = FNO_STOCKS

    logger.info(
        "F&O stock universe created: %s stocks",
        len(FNO_STOCKS)
    )

    return FNO_STOCKS


# ============================================================
# BUILD CASH SYMBOL MAP
# ============================================================

def build_cash_symbol_map():

    global CASH_SYMBOLS

    CASH_SYMBOLS = {}

    for symbol in FNO_STOCKS:

        CASH_SYMBOLS[symbol] = f"NSE-{symbol}"

    logger.info(
        "Cash symbol map created: %s",
        len(CASH_SYMBOLS)
    )


# ============================================================
# FETCH HISTORICAL CANDLES
# ============================================================

def fetch_history(
    symbol: str,
    timeframe: str
):

    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}"
        )

    candle_interval = TIMEFRAME_MAP[
        timeframe
    ]

    days = HISTORY_DAYS.get(
        timeframe,
        30
    )

    end_dt = datetime.utcnow()

    start_dt = (
        end_dt -
        timedelta(days=days)
    )

    groww_symbol = CASH_SYMBOLS.get(
        symbol,
        f"NSE-{symbol}"
    )

    params = {
        "exchange": "NSE",
        "segment": HISTORY_SEGMENT,
        "groww_symbol": groww_symbol,
        "start_time": start_dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "end_time": end_dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "candle_interval": candle_interval,
    }

    response = groww_get(
        HISTORICAL_URL,
        params=params
    )

    if response.status_code != 200:

        raise RuntimeError(
            f"History HTTP {response.status_code} "
            f"for {symbol} {timeframe}: "
            f"{response.text[:300]}"
        )

    data = response.json()

    # --------------------------------------------------------
    # Groww historical response compatibility
    # --------------------------------------------------------

    candles = None

    if isinstance(data, list):
        candles = data

    elif isinstance(data, dict):

        if isinstance(
            data.get("payload"),
            list
        ):
            candles = data["payload"]

        elif isinstance(
            data.get("candles"),
            list
        ):
            candles = data["candles"]

        elif isinstance(
            data.get("data"),
            list
        ):
            candles = data["data"]

        elif isinstance(
            data.get("payload"),
            dict
        ):

            payload = data["payload"]

            if isinstance(
                payload.get("candles"),
                list
            ):
                candles = payload["candles"]

    if not candles:

        raise RuntimeError(
            f"No candles returned for "
            f"{symbol} {timeframe}"
        )

    rows = []

    for candle in candles:

        if not isinstance(
            candle,
            (list, tuple)
        ):
            continue

        if len(candle) < 5:
            continue

        # Standard Groww candle:
        # timestamp, open, high, low, close, volume

        try:

            timestamp = candle[0]
            open_price = float(candle[1])
            high_price = float(candle[2])
            low_price = float(candle[3])
            close_price = float(candle[4])

            volume = (
                float(candle[5])
                if len(candle) > 5
                else 0
            )

            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        except Exception:
            continue

    if not rows:

        raise RuntimeError(
            f"Could not parse candles for "
            f"{symbol} {timeframe}"
        )

    df = pd.DataFrame(rows)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    )

    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# LOAD ALL HISTORY
# ============================================================

def load_all_history():

    global HISTORY

    HISTORY = {}

    entry_tf = SETTINGS.get(
        "entry_timeframe",
        "5m"
    )

    wave_tf = SETTINGS.get(
        "wave_timeframe",
        "15m"
    )

    tide_tf = SETTINGS.get(
        "tide_timeframe",
        "1h"
    )

    timeframes = list(
        dict.fromkeys(
            [
                entry_tf,
                wave_tf,
                tide_tf,
            ]
        )
    )

    total = len(FNO_STOCKS)

    loaded = 0
    failed = 0

    logger.info(
        "Starting historical loading: "
        "%s stocks x %s timeframes",
        total,
        len(timeframes)
    )

    for index, symbol in enumerate(
        FNO_STOCKS,
        start=1
    ):

        HISTORY[symbol] = {}

        stock_success = True

        for timeframe in timeframes:

            try:

                df = fetch_history(
                    symbol,
                    timeframe
                )

                HISTORY[symbol][
                    timeframe
                ] = df

                logger.info(
                    "[%s/%s] %s %s candles=%s",
                    index,
                    total,
                    symbol,
                    timeframe,
                    len(df)
                )

            except Exception as exc:

                stock_success = False

                logger.warning(
                    "[%s/%s] %s %s FAILED: %s",
                    index,
                    total,
                    symbol,
                    timeframe,
                    exc
                )

            # Small throttle
            time.sleep(0.12)

        if stock_success:
            loaded += 1
        else:
            failed += 1

        with STATE_LOCK:

            STATE["history_loaded"] = loaded
            STATE["history_failed"] = failed

        # Do not overload Render / Groww
        time.sleep(0.05)

    STATE["last_history_update"] = (
        datetime.utcnow().isoformat()
    )

    logger.info(
        "History loading completed. "
        "Success=%s Failed=%s",
        loaded,
        failed
    )


# ============================================================
# LTP BATCH
# ============================================================

def fetch_ltp_batch(
    symbols
):

    if not symbols:
        return {}

    exchange_symbols = []

    symbol_map = {}

    for symbol in symbols:

        exchange_symbol = symbol

        exchange_symbols.append(
            exchange_symbol
        )

        symbol_map[
            exchange_symbol
        ] = symbol

    params = {
        "segment": "CASH",
        "exchange_symbols": ",".join(
            exchange_symbols
        ),
    }

    response = groww_get(
        LTP_URL,
        params=params
    )

    if response.status_code != 200:

        raise RuntimeError(
            f"LTP HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    data = response.json()

    result = {}

    payload = data

    if isinstance(data, dict):

        if isinstance(
            data.get("payload"),
            dict
        ):
            payload = data["payload"]

        elif isinstance(
            data.get("data"),
            dict
        ):
            payload = data["data"]

    if isinstance(payload, dict):

        for exchange_symbol, value in payload.items():

            symbol = symbol_map.get(
                exchange_symbol
            )

            if symbol is None:
                continue

            try:

                if isinstance(
                    value,
                    dict
                ):

                    price = (
                        value.get("ltp")
                        or
                        value.get("last_price")
                        or
                        value.get("price")
                    )

                else:

                    price = value

                if price is not None:

                    result[symbol] = float(
                        price
                    )

            except Exception:
                continue

    return result


# ============================================================
# UPDATE LIVE PRICES
# ============================================================

def update_live_prices():

    global LIVE_LTP

    if not FNO_STOCKS:
        return

    all_prices = {}

    # Groww allows max 50 instruments
    batch_size = 50

    for i in range(
        0,
        len(FNO_STOCKS),
        batch_size
    ):

        batch_symbols = FNO_STOCKS[
            i:i + batch_size
        ]

        exchange_symbols = [
            f"NSE_{symbol}"
            for symbol in batch_symbols
        ]

        # ----------------------------------------------------
        # Important:
        # Groww LTP API expects NSE_RELIANCE format.
        # ----------------------------------------------------

        try:

            params = {
                "segment": "CASH",
                "exchange_symbols": ",".join(
                    exchange_symbols
                ),
            }

            response = groww_get(
                LTP_URL,
                params=params
            )

            if response.status_code != 200:

                logger.warning(
                    "LTP batch failed: HTTP %s",
                    response.status_code
                )

                continue

            data = response.json()

            payload = data

            if isinstance(data, dict):

                if isinstance(
                    data.get("payload"),
                    dict
                ):
                    payload = data["payload"]

                elif isinstance(
                    data.get("data"),
                    dict
                ):
                    payload = data["data"]

            if isinstance(payload, dict):

                for exchange_symbol, value in payload.items():

                    if not isinstance(
                        value,
                        dict
                    ):
                        price = value

                    else:

                        price = (
                            value.get("ltp")
                            or
                            value.get("last_price")
                            or
                            value.get("price")
                        )

                    if price is None:
                        continue

                    exchange_symbol = str(
                        exchange_symbol
                    ).upper()

                    if exchange_symbol.startswith(
                        "NSE_"
                    ):

                        symbol = exchange_symbol[
                            4:
                        ]

                        try:

                            all_prices[
                                symbol
                            ] = float(price)

                        except Exception:
                            pass

        except Exception as exc:

            logger.warning(
                "LTP batch exception: %s",
                exc
            )

        time.sleep(0.12)

    LIVE_LTP = all_prices

    STATE["live_prices"] = len(
        LIVE_LTP
    )

    STATE["last_ltp_update"] = (
        datetime.utcnow().isoformat()
    )


# ============================================================
# SCANNER CALCULATION
# ============================================================

def calculate_scanner():

    results = []

    if not HISTORY:

        return results

    engine = ScannerEngine(
        SETTINGS
    )

    for symbol in FNO_STOCKS:

        try:

            symbol_history = HISTORY.get(
                symbol,
                {}
            )

            if not symbol_history:
                continue

            result = None

            # ------------------------------------------------
            # Support multiple strategy.py versions
            # ------------------------------------------------

            if hasattr(
                engine,
                "analyze_symbol"
            ):

                result = engine.analyze_symbol(
                    symbol,
                    symbol_history,
                    LIVE_LTP.get(symbol)
                )

            elif hasattr(
                engine,
                "scan_symbol"
            ):

                result = engine.scan_symbol(
                    symbol,
                    symbol_history,
                    LIVE_LTP.get(symbol)
                )

            elif hasattr(
                engine,
                "analyze"
            ):

                result = engine.analyze(
                    symbol,
                    symbol_history,
                    LIVE_LTP.get(symbol)
                )

            if result is None:
                continue

            if not isinstance(
                result,
                dict
            ):
                continue

            result.setdefault(
                "symbol",
                symbol
            )

            result.setdefault(
                "ltp",
                LIVE_LTP.get(symbol)
            )

            results.append(result)

        except Exception as exc:

            logger.debug(
                "Scanner error %s: %s",
                symbol,
                exc
            )

    # Sort:
    # BUY first
    # SELL second
    # WAIT last
    def sort_key(item):

        signal = str(
            item.get(
                "signal",
                "WAIT"
            )
        ).upper()

        score = float(
            item.get(
                "score",
                0
            ) or 0
        )

        if signal == "BUY":
            group = 0

        elif signal == "SELL":
            group = 1

        else:
            group = 2

        return (
            group,
            -score
        )

    results.sort(
        key=sort_key
    )

    return results


# ============================================================
# BACKGROUND SCANNER WORKER
# ============================================================

SCANNER_RESULTS = []

SCANNER_LOCK = threading.Lock()


def scanner_worker():

    global SCANNER_RESULTS

    while True:

        try:

            if STATE.get(
                "authenticated"
            ) and STATE.get(
                "instruments_loaded"
            ):

                # Update LTP
                try:

                    update_live_prices()

                except Exception as exc:

                    logger.warning(
                        "Live price update failed: %s",
                        exc
                    )

                # Calculate scanner
                try:

                    results = calculate_scanner()

                    with SCANNER_LOCK:

                        SCANNER_RESULTS = results

                except Exception as exc:

                    logger.warning(
                        "Scanner calculation failed: %s",
                        exc
                    )

            time.sleep(10)

        except Exception as exc:

            logger.exception(
                "Scanner worker error: %s",
                exc
            )

            time.sleep(15)


# ============================================================
# INITIALIZATION
# ============================================================

def initialize_app():

    try:

        logger.info(
            "=================================================="
        )

        logger.info(
            "INDIAN F&O SCANNER STARTING"
        )

        logger.info(
            "=================================================="
        )

        STATE["market_status"] = (
            "AUTHENTICATING"
        )

        # ----------------------------------------------------
        # 1. AUTHENTICATION
        # ----------------------------------------------------

        test_groww_connection()

        STATE["market_status"] = (
            "AUTHENTICATED"
        )

        # ----------------------------------------------------
        # 2. INSTRUMENTS
        # ----------------------------------------------------

        load_instruments()

        # ----------------------------------------------------
        # 3. F&O UNIVERSE
        # ----------------------------------------------------

        build_fno_stock_universe()

        build_cash_symbol_map()

        # ----------------------------------------------------
        # 4. HISTORICAL DATA
        # ----------------------------------------------------

        STATE["market_status"] = (
            "LOADING_HISTORY"
        )

        load_all_history()

        # ----------------------------------------------------
        # 5. LTP
        # ----------------------------------------------------

        try:

            update_live_prices()

        except Exception as exc:

            logger.warning(
                "Initial LTP update failed: %s",
                exc
            )

        STATE["market_status"] = (
            "LIVE"
        )

        STATE["scanner_running"] = True

        logger.info(
            "Scanner initialization completed."
        )

    except Exception as exc:

        STATE["authenticated"] = False

        STATE["market_status"] = "ERROR"

        STATE["last_error"] = str(
            exc
        )

        logger.exception(
            "INITIALIZATION FAILED"
        )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "app": STATE["app"],
        "market_status": STATE[
            "market_status"
        ],
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
def api_status():

    return {
        "app": STATE["app"],

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

        "live_prices": STATE[
            "live_prices"
        ],

        "last_error": STATE[
            "last_error"
        ],

        "token_expiry": STATE[
            "token_expiry"
        ],

        "session_name": STATE[
            "session_name"
        ],

        "scanner_running": STATE[
            "scanner_running"
        ],
    }


# ============================================================
# GROWw TEST
# ============================================================

@app.get("/api/groww-test")
def groww_test():

    try:

        user_data = test_groww_connection()

        return {
            "status": "success",
            "authenticated": True,
            "token_received": True,
            "session_name": STATE[
                "session_name"
            ],
            "expiry": STATE[
                "token_expiry"
            ],
            "user_detail": user_data,
        }

    except Exception as exc:

        STATE["authenticated"] = False

        STATE["market_status"] = "ERROR"

        STATE["last_error"] = str(
            exc
        )

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "authenticated": False,
                "token_received": False,
                "message": str(exc),
            }
        )


# ============================================================
# SCANNER API
# ============================================================

@app.get("/api/scanner")
def api_scanner():

    with SCANNER_LOCK:

        results = list(
            SCANNER_RESULTS
        )

    return {
        "status": "success",
        "count": len(results),
        "results": results,
    }


# ============================================================
# UNIVERSE API
# ============================================================

@app.get("/api/universe")
def api_universe():

    return {
        "count": len(FNO_STOCKS),
        "stocks": FNO_STOCKS,
    }


# ============================================================
# SETTINGS GET
# ============================================================

@app.get("/api/settings")
def get_settings():

    return {
        "settings": SETTINGS
    }


# ============================================================
# SETTINGS UPDATE
# ============================================================

@app.post("/api/settings")
def update_settings(
    payload: Dict[str, Any]
):

    global SETTINGS

    if not isinstance(
        payload,
        dict
    ):

        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid settings."
            }
        )

    # Only known strategy settings
    for key, value in payload.items():

        if key in DEFAULT_SETTINGS:

            SETTINGS[key] = value

    logger.info(
        "Settings updated: %s",
        SETTINGS
    )

    return {
        "status": "success",
        "settings": SETTINGS,
    }


# ============================================================
# RESET
# ============================================================

@app.post("/api/reset")
def reset_scanner():

    global HISTORY
    global LIVE_LTP
    global SCANNER_RESULTS

    HISTORY = {}

    LIVE_LTP = {}

    with SCANNER_LOCK:

        SCANNER_RESULTS = []

    STATE["history_loaded"] = 0
    STATE["history_failed"] = 0
    STATE["live_prices"] = 0

    STATE["last_history_update"] = None
    STATE["last_ltp_update"] = None

    STATE["market_status"] = (
        "RESET"
    )

    return {
        "status": "success",
        "message": "Scanner data reset."
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_event():

    logger.info(
        "FastAPI startup."
    )

    # Run initialization in background
    thread = threading.Thread(
        target=initialize_app,
        daemon=True
    )

    thread.start()

    # Scanner worker
    scanner_thread = threading.Thread(
        target=scanner_worker,
        daemon=True
    )

    scanner_thread.start()


# ============================================================
# STATIC FRONTEND
# ============================================================

if os.path.isdir("static"):

    app.mount(
        "/",
        StaticFiles(
            directory="static",
            html=True
        ),
        name="static"
    )
