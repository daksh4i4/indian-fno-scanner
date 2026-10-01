import os
import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

try:
    from growwapi import GrowwAPI, GrowwFeed
except Exception:
    GrowwAPI = None
    GrowwFeed = None

from strategy import DEFAULT_SETTINGS, ScannerEngine

load_dotenv()

app = FastAPI(
    title="Indian F&O Intraday Scanner",
    version="4.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# ============================================================
# SCANNER ENGINE
# ============================================================

engine = ScannerEngine(DEFAULT_SETTINGS.copy())

state = {
    "status": "starting",
    "message": "Starting scanner...",
    "last_update": None,

    "history_loaded": 0,
    "history_total": 0,

    "stocks": [],
    "feed_connected": False,
    "fno_count": 0,

    "auth_connected": False,
    "last_error": None,
    "last_history_error": None,

    "entry_loaded": 0,
    "wave_loaded": 0,
    "tide_loaded": 0,
}

stocks = []

feed_thread = None
history_thread = None

feed_obj = None
groww = None
access_token = None

history_call_lock = threading.Lock()
last_history_call = 0.0


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_error(exc):
    """
    Convert Groww/Python exceptions to a useful short log message.
    """
    try:
        text = str(exc).strip()
    except Exception:
        text = repr(exc)

    if not text:
        text = repr(exc)

    return text[:1000]


def response_payload(resp):
    """
    Groww normally returns:
        {
            "status": "SUCCESS",
            "payload": {...}
        }

    Some SDK helpers may return payload directly.
    """
    if not isinstance(resp, dict):
        return resp or {}

    payload = resp.get("payload")

    if isinstance(payload, dict):
        return payload

    return resp


# ============================================================
# GROWW API KEY + SECRET AUTHENTICATION
# ============================================================

def generate_checksum(secret: str, timestamp: str) -> str:
    """
    Groww API checksum:
        SHA256(secret + timestamp)
    """
    raw = secret + timestamp
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_groww_access_token(api_key: str, api_secret: str) -> str:
    """
    Generate a Groww access token using:
        API Key + API Secret
        key_type = approval

    The approval must be active in Groww Cloud API Keys.
    """

    timestamp = str(int(time.time()))

    checksum = generate_checksum(
        api_secret,
        timestamp
    )

    url = "https://api.groww.in/v1/token/api/access"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-VERSION": "1.0",
    }

    body = {
        "key_type": "approval",
        "checksum": checksum,
        "timestamp": timestamp,
    }

    response = requests.post(
        url,
        headers=headers,
        json=body,
        timeout=20,
    )

    try:
        data = response.json()
    except Exception:
        data = {
            "raw": response.text
        }

    if response.status_code != 200:
        raise RuntimeError(
            f"Groww authentication HTTP {response.status_code}: {data}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Unexpected Groww authentication response: {data}"
        )

    token = data.get("token")

    if not token:
        raise RuntimeError(
            f"Groww authentication failed: {data}"
        )

    return str(token)


# ============================================================
# GROWW REST HELPER
# ============================================================

def groww_request(
    method: str,
    url: str,
    params=None,
    json_body=None,
    timeout=30,
):
    """
    Direct Groww REST request.

    This avoids hiding errors inside SDK compatibility layers.
    """

    if not access_token:
        raise RuntimeError(
            "Groww access token is not available."
        )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "X-API-VERSION": "1.0",
    }

    if json_body is not None:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=timeout,
    )

    try:
        data = response.json()
    except Exception:
        data = {
            "raw": response.text
        }

    if response.status_code >= 400:
        raise RuntimeError(
            f"Groww HTTP {response.status_code}: {data}"
        )

    if isinstance(data, dict):
        if data.get("status") == "FAILURE":
            error = data.get("error", {})
            raise RuntimeError(
                f"Groww API failure: {error}"
            )

    return data


# ============================================================
# LOAD F&O UNIVERSE
# ============================================================

def load_universe():
    global groww
    global stocks
    global access_token

    api_key = os.getenv(
        "GROWW_API_KEY",
        ""
    ).strip()

    api_secret = os.getenv(
        "GROWW_API_SECRET",
        ""
    ).strip()

    legacy_token = os.getenv(
        "GROWW_ACCESS_TOKEN",
        ""
    ).strip()

    if not api_key or not api_secret:

        if legacy_token:
            state["status"] = "error"
            state["message"] = (
                "GROWW_ACCESS_TOKEN found, but this version uses "
                "GROWW_API_KEY + GROWW_API_SECRET."
            )
        else:
            state["status"] = "error"
            state["message"] = (
                "Missing GROWW_API_KEY or GROWW_API_SECRET."
            )

        state["auth_connected"] = False
        return []

    try:

        print("==================================================")
        print("GROWW AUTHENTICATION START")
        print("==================================================")

        # ----------------------------------------------------
        # Generate access token
        # ----------------------------------------------------

        access_token = generate_groww_access_token(
            api_key,
            api_secret
        )

        print("Groww access token generated successfully.")

        state["auth_connected"] = True

        # ----------------------------------------------------
        # Initialize SDK only for feed
        # ----------------------------------------------------

        if GrowwAPI is not None:
            try:
                groww = GrowwAPI(access_token)
                print("Groww SDK initialized.")
            except Exception as exc:
                print(
                    "Groww SDK initialization warning:",
                    safe_error(exc)
                )
                groww = None

        # ----------------------------------------------------
        # Download instrument master
        # ----------------------------------------------------

        instrument_url = (
            "https://growwapi-assets.groww.in/"
            "instruments/instrument.csv"
        )

        print(
            "Downloading Groww instrument CSV..."
        )

        df = pd.read_csv(
            instrument_url,
            low_memory=False
        )

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        print(
            f"Instrument rows loaded: {len(df)}"
        )

        required_columns = {
            "exchange",
            "segment",
            "trading_symbol",
            "underlying_symbol",
            "exchange_token",
            "groww_symbol",
        }

        missing = (
            required_columns -
            set(df.columns)
        )

        if missing:
            raise RuntimeError(
                "Instrument CSV missing columns: "
                + str(sorted(missing))
            )

        # ----------------------------------------------------
        # Find NSE F&O underlying stocks
        # ----------------------------------------------------

        fno = df[
            (
                df["exchange"]
                .astype(str)
                .str.upper()
                .str.strip()
                == "NSE"
            )
            &
            (
                df["segment"]
                .astype(str)
                .str.upper()
                .str.strip()
                == "FNO"
            )
        ].copy()

        print(
            f"NSE F&O instrument rows: {len(fno)}"
        )

        fno["underlying_symbol"] = (
            fno["underlying_symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        underlyings = set(
            x
            for x in fno["underlying_symbol"].dropna()
            if x and x != "NAN"
        )

        # Remove indices.
        index_names = {
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
            "NIFTYNXT50",
        }

        underlyings -= index_names

        print(
            f"F&O underlying stock symbols: "
            f"{len(underlyings)}"
        )

        # ----------------------------------------------------
        # Find corresponding NSE CASH instruments
        # ----------------------------------------------------

        cash = df[
            (
                df["exchange"]
                .astype(str)
                .str.upper()
                .str.strip()
                == "NSE"
            )
            &
            (
                df["segment"]
                .astype(str)
                .str.upper()
                .str.strip()
                == "CASH"
            )
        ].copy()

        cash["trading_symbol"] = (
            cash["trading_symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        rows = []

        for _, row in cash.iterrows():

            symbol = str(
                row["trading_symbol"]
            ).upper().strip()

            if symbol not in underlyings:
                continue

            groww_symbol = str(
                row.get("groww_symbol", "")
            ).strip()

            if (
                not groww_symbol
                or groww_symbol.lower() == "nan"
            ):
                groww_symbol = (
                    f"NSE-{symbol}"
                )

            rows.append({
                "symbol": symbol,
                "exchange": "NSE",
                "segment": "CASH",
                "exchange_token": str(
                    row["exchange_token"]
                ),
                "groww_symbol": groww_symbol,
            })

        # Remove duplicates.
        unique = {}

        for item in rows:
            unique[item["symbol"]] = item

        stocks = list(
            unique.values()
        )

        stocks.sort(
            key=lambda x: x["symbol"]
        )

        state["stocks"] = stocks
        state["fno_count"] = len(stocks)
        state["history_total"] = len(stocks)

        print(
            "=================================================="
        )
        print(
            f"FINAL F&O STOCK COUNT: {len(stocks)}"
        )
        print(
            "=================================================="
        )

        if stocks:
            print(
                "Sample instruments:"
            )

            for sample in stocks[:5]:
                print(
                    sample
                )

        state["status"] = "ready"
        state["message"] = (
            f"{len(stocks)} NSE F&O stocks loaded. "
            "Loading historical candles..."
        )

        return stocks

    except Exception as exc:

        message = safe_error(exc)

        print(
            "=================================================="
        )
        print(
            "GROWW UNIVERSE ERROR"
        )
        print(
            message
        )
        print(
            "=================================================="
        )

        state["status"] = "error"
        state["auth_connected"] = False
        state["last_error"] = message
        state["message"] = (
            f"Groww connection error: {message}"
        )

        return []


# ============================================================
# INITIAL LTP
# ============================================================

def fetch_initial_ltp(items):

    if not access_token or not items:
        return

    symbols = [
        f"NSE_{x['symbol']}"
        for x in items
    ]

    for i in range(
        0,
        len(symbols),
        50
    ):

        batch = symbols[
            i:i + 50
        ]

        try:

            data = groww_request(
                "GET",
                "https://api.groww.in/v1/live-data/ltp",
                params={
                    "segment": "CASH",
                    "exchange_symbols": ",".join(
                        batch
                    ),
                },
                timeout=20,
            )

            payload = response_payload(
                data
            )

            if not isinstance(
                payload,
                dict
            ):
                continue

            for key, value in payload.items():

                try:
                    price = float(value)
                except Exception:
                    continue

                symbol = str(key).replace(
                    "NSE_",
                    ""
                )

                engine.update_tick(
                    symbol,
                    {
                        "ltp": price,
                        "ts": now_iso(),
                    }
                )

        except Exception as exc:

            message = (
                "Initial LTP warning: "
                + safe_error(exc)
            )

            print(message)

            state["last_error"] = message


# ============================================================
# TIMEFRAME HELPERS
# ============================================================

def parse_timeframe(value):
    """
    Convert:
        1m  -> 1
        5m  -> 5
        15m -> 15
        30m -> 30
        1h  -> 60
        4h  -> 240
    """

    text = str(
        value
    ).strip().lower()

    if text.endswith("m"):
        return int(
            text[:-1]
        )

    if text.endswith("h"):
        return (
            int(text[:-1]) * 60
        )

    if text.endswith("d"):
        return (
            int(text[:-1]) * 1440
        )

    return int(text)


def groww_candle_interval(minutes):
    """
    Groww REST candle interval names.
    """

    mapping = {
        1: "1minute",
        2: "2minute",
        3: "3minute",
        5: "5minute",
        10: "10minute",
        15: "15minute",
        30: "30minute",
        60: "1hour",
        240: "4hour",
        1440: "1day",
        10080: "1week",
    }

    minutes = int(minutes)

    if minutes not in mapping:
        raise ValueError(
            f"Unsupported Groww timeframe: "
            f"{minutes} minutes"
        )

    return mapping[minutes]


def history_window(minutes):
    """
    Keep every request inside Groww's documented
    historical-data duration limits.
    """

    minutes = int(minutes)

    if minutes <= 5:
        days = 15

    elif minutes <= 30:
        days = 60

    elif minutes <= 240:
        days = 150

    else:
        days = 180

    # Use IST because NSE market data is Indian-market data.
    end = datetime.now(
        timezone.utc
    ) + timedelta(
        hours=5,
        minutes=30
    )

    start = (
        end -
        timedelta(days=days)
    )

    return (
        start.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        end.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )


# ============================================================
# HISTORY RATE LIMIT
# ============================================================

def history_rate_limit():

    global last_history_call

    with history_call_lock:

        now = time.monotonic()

        # Conservative throttle.
        minimum_gap = 0.30

        wait = (
            minimum_gap -
            (now - last_history_call)
        )

        if wait > 0:
            time.sleep(wait)

        last_history_call = (
            time.monotonic()
        )


# ============================================================
# EXTRACT CANDLES
# ============================================================

def extract_candles(resp):

    payload = response_payload(
        resp
    )

    if not isinstance(
        payload,
        dict
    ):
        return []

    candles = payload.get(
        "candles",
        []
    )

    if not isinstance(
        candles,
        list
    ):
        return []

    return candles


# ============================================================
# FETCH HISTORICAL CANDLES
# ============================================================

def fetch_history(
    item,
    timeframe
):

    minutes = parse_timeframe(
        timeframe
    )

    start, end = history_window(
        minutes
    )

    interval = groww_candle_interval(
        minutes
    )

    history_rate_limit()

    params = {
        "exchange": "NSE",
        "segment": "CASH",
        "groww_symbol": item[
            "groww_symbol"
        ],
        "start_time": start,
        "end_time": end,
        "candle_interval": interval,
    }

    try:

        response = groww_request(
            "GET",
            "https://api.groww.in/v1/historical/candles",
            params=params,
            timeout=45,
        )

        candles = extract_candles(
            response
        )

        if not candles:
            raise RuntimeError(
                f"No candles returned for "
                f"{item['symbol']} "
                f"({item['groww_symbol']}) "
                f"{timeframe}. "
                f"Request={params}"
            )

        return candles

    except Exception as exc:

        message = (
            f"History error | "
            f"{item['symbol']} | "
            f"{item['groww_symbol']} | "
            f"{timeframe} | "
            f"{safe_error(exc)}"
        )

        print(message)

        state["last_history_error"] = (
            message
        )

        raise


# ============================================================
# LOAD ONE STOCK
# ============================================================

def load_stock_history(item):

    symbol = item[
        "symbol"
    ]

    entry_tf = engine.settings[
        "entry_timeframe"
    ]

    wave_tf = engine.settings[
        "wave_timeframe"
    ]

    tide_tf = engine.settings[
        "tide_timeframe"
    ]

    result = {
        "entry": False,
        "wave": False,
        "tide": False,
    }

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    try:

        candles = fetch_history(
            item,
            entry_tf
        )

        if candles:

            engine.set_history(
                symbol,
                entry_tf,
                candles
            )

            result["entry"] = True

    except Exception:
        pass

    # --------------------------------------------------------
    # WAVE
    # --------------------------------------------------------

    if wave_tf == entry_tf:

        result["wave"] = result[
            "entry"
        ]

    else:

        try:

            candles = fetch_history(
                item,
                wave_tf
            )

            if candles:

                engine.set_history(
                    symbol,
                    wave_tf,
                    candles
                )

                result["wave"] = True

        except Exception:
            pass

    # --------------------------------------------------------
    # TIDE
    # --------------------------------------------------------

    if tide_tf == entry_tf:

        result["tide"] = result[
            "entry"
        ]

    elif tide_tf == wave_tf:

        result["tide"] = result[
            "wave"
        ]

    else:

        try:

            candles = fetch_history(
                item,
                tide_tf
            )

            if candles:

                engine.set_history(
                    symbol,
                    tide_tf,
                    candles
                )

                result["tide"] = True

        except Exception:
            pass

    return result


# ============================================================
# LOAD ALL HISTORY
# ============================================================

def load_history_all():

    if not access_token or not stocks:
        return

    state["status"] = "loading"

    state["message"] = (
        "Loading Groww historical candles "
        "for NSE F&O stocks..."
    )

    state["history_loaded"] = 0
    state["entry_loaded"] = 0
    state["wave_loaded"] = 0
    state["tide_loaded"] = 0

    total = len(stocks)

    loaded = 0

    print(
        "=================================================="
    )

    print(
        f"STARTING HISTORY LOAD: {total} STOCKS"
    )

    print(
        "=================================================="
    )

    # Use a small number of workers because
    # Groww API limits/rate behaviour should be respected.
    with ThreadPoolExecutor(
        max_workers=3
    ) as pool:

        futures = [
            pool.submit(
                load_stock_history,
                item
            )
            for item in stocks
        ]

        for future in as_completed(
            futures
        ):

            try:

                result = future.result()

                if result["entry"]:
                    state["entry_loaded"] += 1

                if result["wave"]:
                    state["wave_loaded"] += 1

                if result["tide"]:
                    state["tide_loaded"] += 1

                if (
                    result["entry"]
                    and result["wave"]
                    and result["tide"]
                ):
                    loaded += 1

            except Exception as exc:

                print(
                    "History worker error:",
                    safe_error(exc)
                )

            state[
                "history_loaded"
            ] = loaded

            state[
                "last_update"
            ] = now_iso()

    # Recalculate after history loading.
    try:
        engine.recalculate_all()
    except Exception as exc:
        print(
            "Recalculate error:",
            safe_error(exc)
        )

    if loaded > 0:

        state["status"] = (
            "live"
            if state["feed_connected"]
            else "ready"
        )

        state["message"] = (
            "Live scanner ready. "
            f"Historical candles loaded for "
            f"{loaded}/{total} stocks. "
            f"Entry={state['entry_loaded']}, "
            f"Wave={state['wave_loaded']}, "
            f"Tide={state['tide_loaded']}."
        )

    else:

        state["status"] = "error"

        state["message"] = (
            "Groww connection exists, but "
            "no historical candles were loaded. "
            "Check last_history_error."
        )

    print(
        "=================================================="
    )

    print(
        f"HISTORY COMPLETE: {loaded}/{total}"
    )

    print(
        f"Entry: {state['entry_loaded']}"
    )

    print(
        f"Wave: {state['wave_loaded']}"
    )

    print(
        f"Tide: {state['tide_loaded']}"
    )

    print(
        "Last error:",
        state["last_history_error"]
    )

    print(
        "=================================================="
    )


# ============================================================
# GROWW LIVE FEED
# ============================================================

def feed_worker(items):

    global feed_obj

    if (
        not groww
        or GrowwFeed is None
        or not items
    ):
        print(
            "Live feed unavailable."
        )
        return

    try:

        print(
            "Starting Groww live feed..."
        )

        feed_obj = GrowwFeed(
            groww
        )

        instruments = [
            {
                "exchange": "NSE",
                "segment": "CASH",
                "exchange_token": x[
                    "exchange_token"
                ],
            }
            for x in items[:1000]
        ]

        token_to_symbol = {
            x["exchange_token"]:
            x["symbol"]
            for x in items
        }

        def on_data(_meta):

            try:

                data = (
                    feed_obj.get_ltp()
                    or {}
                )

                ltp_root = data.get(
                    "ltp",
                    data
                )

                nse = ltp_root.get(
                    "NSE",
                    {}
                )

                cash = nse.get(
                    "CASH",
                    {}
                )

                for token, payload in cash.items():

                    symbol = token_to_symbol.get(
                        str(token)
                    )

                    if not symbol:
                        continue

                    if not isinstance(
                        payload,
                        dict
                    ):
                        continue

                    price = payload.get(
                        "ltp"
                    )

                    if price is None:
                        continue

                    try:
                        price = float(
                            price
                        )
                    except Exception:
                        continue

                    ts_ms = float(
                        payload.get(
                            "tsInMillis",
                            time.time() * 1000
                        )
                    )

                    timestamp = (
                        datetime.fromtimestamp(
                            ts_ms / 1000,
                            tz=timezone.utc
                        ).isoformat()
                    )

                    engine.update_tick(
                        symbol,
                        {
                            "ltp": price,
                            "ts": timestamp,
                        }
                    )

                state[
                    "last_update"
                ] = now_iso()

            except Exception as exc:

                print(
                    "Feed callback error:",
                    safe_error(exc)
                )

        feed_obj.subscribe_ltp(
            instruments,
            on_data_received=on_data
        )

        state[
            "feed_connected"
        ] = True

        state["status"] = (
            "live"
            if state["history_loaded"] > 0
            else "loading"
        )

        state["message"] = (
            "Groww live feed connected."
        )

        print(
            "Groww live feed connected."
        )

        # Blocking call.
        feed_obj.consume()

    except Exception as exc:

        message = (
            "Feed error: "
            + safe_error(exc)
        )

        print(message)

        state[
            "feed_connected"
        ] = False

        state[
            "last_error"
        ] = message

        if state["history_loaded"] > 0:
            state["status"] = "ready"
        else:
            state["status"] = "error"

        state[
            "message"
        ] = message


# ============================================================
# START SERVICES
# ============================================================

def start_services():

    items = load_universe()

    if not items:
        return

    # Initial prices.
    fetch_initial_ltp(
        items
    )

    global feed_thread
    global history_thread

    # Live feed.
    feed_thread = threading.Thread(
        target=feed_worker,
        args=(items,),
        daemon=True,
    )

    feed_thread.start()

    # Historical candles.
    history_thread = threading.Thread(
        target=load_history_all,
        daemon=True,
    )

    history_thread.start()


# ============================================================
# FASTAPI STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    print(
        "Indian F&O Scanner starting..."
    )

    threading.Thread(
        target=start_services,
        daemon=True,
    ).start()


# ============================================================
# WEB
# ============================================================

@app.get("/")
def index():

    return FileResponse(
        "static/index.html"
    )


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
def api_status():

    return {
        **state,
        "settings": engine.settings,
        "timestamp": now_iso(),
    }


# ============================================================
# SCANNER
# ============================================================

@app.get("/api/scanner")
def api_scanner():

    return {
        "status": state["status"],
        "stocks": engine.snapshot(),
        "timestamp": now_iso(),
    }


# ============================================================
# SETTINGS
# ============================================================

@app.get("/api/settings")
def get_settings():

    return engine.settings


@app.post("/api/settings")
async def set_settings(
    payload: dict[str, Any]
):

    try:

        old = engine.settings.copy()

        engine.update_settings(
            payload
        )

        timeframe_keys = (
            "wave_timeframe",
            "tide_timeframe",
            "entry_timeframe",
        )

        changed_tf = any(
            engine.settings[k] != old[k]
            for k in timeframe_keys
        )

        if (
            changed_tf
            and stocks
            and access_token
        ):

            # Clear old candle data before
            # loading the new timeframe.
            engine.clear_history()

            threading.Thread(
                target=load_history_all,
                daemon=True,
            ).start()

        return {
            "ok": True,
            "settings": engine.settings,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=safe_error(exc)
        )


# ============================================================
# RESET SETTINGS
# ============================================================

@app.post("/api/reset")
def reset_settings():

    old = engine.settings.copy()

    engine.update_settings(
        DEFAULT_SETTINGS.copy()
    )

    timeframe_keys = (
        "wave_timeframe",
        "tide_timeframe",
        "entry_timeframe",
    )

    changed_tf = any(
        engine.settings[k] != old[k]
        for k in timeframe_keys
    )

    if (
        changed_tf
        and stocks
        and access_token
    ):

        engine.clear_history()

        threading.Thread(
            target=load_history_all,
            daemon=True,
        ).start()

    return {
        "ok": True,
        "settings": engine.settings,
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "status": state["status"],
        "feed_connected": state[
            "feed_connected"
        ],
        "auth_connected": state[
            "auth_connected"
        ],
        "fno_count": state[
            "fno_count"
        ],
        "history_loaded": state[
            "history_loaded"
        ],
        "entry_loaded": state[
            "entry_loaded"
        ],
        "wave_loaded": state[
            "wave_loaded"
        ],
        "tide_loaded": state[
            "tide_loaded"
        ],
        "last_error": state[
            "last_error"
        ],
        "last_history_error": state[
            "last_history_error"
        ],
    }


# ============================================================
# LOCAL START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "10000"
            )
        )
    )
