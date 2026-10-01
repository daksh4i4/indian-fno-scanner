import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd
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

app = FastAPI(title="Indian F&O Intraday Scanner", version="2.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

engine = ScannerEngine(DEFAULT_SETTINGS.copy())
state = {
    "status": "starting",
    "message": "Starting scanner...",
    "last_update": None,
    "history_loaded": 0,
    "stocks": [],
    "feed_connected": False,
    "fno_count": 0,
}

stocks = []
feed_thread = None
history_thread = None
feed_obj = None
groww = None
history_call_lock = threading.Lock()
last_history_call = 0.0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def response_payload(resp):
    if not isinstance(resp, dict):
        return resp or {}
    if isinstance(resp.get("payload"), dict):
        return resp["payload"]
    return resp


def load_universe():
    global groww, stocks
    if GrowwAPI is None:
        state["status"] = "error"
        state["message"] = "growwapi package is not installed."
        return []

    token = os.getenv("GROWW_ACCESS_TOKEN", "").strip()
    if not token:
        state["status"] = "demo"
        state["message"] = "Add GROWW_ACCESS_TOKEN in Render Environment Variables."
        return []

    try:
        groww = GrowwAPI(token)
        url = getattr(groww, "INSTRUMENT_CSV_URL", None) or "https://growwapi-assets.groww.in/instruments/instrument.csv"
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]

        required = {"exchange", "segment", "trading_symbol", "underlying_symbol", "exchange_token", "groww_symbol"}
        missing = required - set(df.columns)
        if missing:
            raise RuntimeError(f"Instrument CSV missing columns: {sorted(missing)}")

        fno = df[(df["exchange"].astype(str).str.upper() == "NSE") &
                 (df["segment"].astype(str).str.upper() == "FNO")].copy()
        underlyings = set(fno["underlying_symbol"].dropna().astype(str).str.upper().str.strip())
        index_names = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
        underlyings -= index_names

        cash = df[(df["exchange"].astype(str).str.upper() == "NSE") &
                  (df["segment"].astype(str).str.upper() == "CASH")].copy()
        cash["trading_symbol"] = cash["trading_symbol"].astype(str).str.upper().str.strip()

        rows = []
        for _, r in cash.iterrows():
            sym = r["trading_symbol"]
            if sym in underlyings:
                rows.append({
                    "symbol": sym,
                    "exchange": "NSE",
                    "segment": "CASH",
                    "exchange_token": str(r["exchange_token"]),
                    "groww_symbol": str(r.get("groww_symbol") or f"NSE-{sym}"),
                })

        stocks = list({x["symbol"]: x for x in rows}.values())
        stocks.sort(key=lambda x: x["symbol"])
        state["stocks"] = stocks
        state["fno_count"] = len(stocks)
        state["status"] = "ready"
        state["message"] = f"{len(stocks)} NSE F&O stocks loaded. Loading candles..."
        return stocks
    except Exception as exc:
        state["status"] = "error"
        state["message"] = f"Universe error: {exc}"
        return []


def fetch_initial_ltp(items):
    if not groww or not items:
        return
    symbols = [f"NSE_{x['symbol']}" for x in items]
    for i in range(0, len(symbols), 50):
        batch = symbols[i:i + 50]
        try:
            resp = response_payload(groww.get_ltp(
                segment=getattr(groww, "SEGMENT_CASH", "CASH"),
                exchange_trading_symbols=tuple(batch),
            ))
            for key, value in (resp or {}).items():
                if isinstance(value, (dict, list)):
                    continue
                sym = key.replace("NSE_", "")
                engine.update_tick(sym, {"ltp": float(value), "ts": now_iso()})
        except Exception as exc:
            state["message"] = f"Initial LTP warning: {exc}"


def interval_constant(minutes):
    mapping = {
        1: "CANDLE_INTERVAL_MIN_1", 2: "CANDLE_INTERVAL_MIN_2", 3: "CANDLE_INTERVAL_MIN_3",
        5: "CANDLE_INTERVAL_MIN_5", 10: "CANDLE_INTERVAL_MIN_10", 15: "CANDLE_INTERVAL_MIN_15",
        30: "CANDLE_INTERVAL_MIN_30", 60: "CANDLE_INTERVAL_HOUR_1", 240: "CANDLE_INTERVAL_HOUR_4",
        1440: "CANDLE_INTERVAL_DAY", 10080: "CANDLE_INTERVAL_WEEK",
    }
    name = mapping.get(int(minutes))
    if not name:
        raise ValueError(f"Unsupported Groww candle timeframe: {minutes} minutes")
    value = getattr(groww, name, None)
    if value is None:
        raise ValueError(f"Groww SDK does not expose {name}")
    return value


def history_window(minutes):
    # Enough data for EMA/SR while respecting documented per-request limits.
    if minutes <= 5:
        days = 15
    elif minutes <= 30:
        days = 30
    elif minutes <= 240:
        days = 60
    else:
        days = 180
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def extract_candles(resp):
    payload = response_payload(resp)
    if isinstance(payload, dict):
        return payload.get("candles", []) or []
    return []


def _history_rate_limit():
    global last_history_call
    with history_call_lock:
        now = time.monotonic()
        wait = 0.13 - (now - last_history_call)
        if wait > 0:
            time.sleep(wait)
        last_history_call = time.monotonic()


def fetch_history(item, timeframe):
    minutes = int(str(timeframe).lower().replace("m", "")) if str(timeframe).lower().endswith("m") else int(float(str(timeframe).lower().replace("h", "")) * 60)
    start, end = history_window(minutes)
    try:
        _history_rate_limit()
        resp = groww.get_historical_candles(
            exchange=getattr(groww, "EXCHANGE_NSE", "NSE"),
            segment=getattr(groww, "SEGMENT_CASH", "CASH"),
            groww_symbol=item["groww_symbol"],
            start_time=start,
            end_time=end,
            candle_interval=interval_constant(minutes),
        )
        return extract_candles(resp)
    except Exception:
        # Compatibility fallback for older SDK releases.
        _history_rate_limit()
        resp = groww.get_historical_candle_data(
            trading_symbol=item["symbol"],
            exchange=getattr(groww, "EXCHANGE_NSE", "NSE"),
            segment=getattr(groww, "SEGMENT_CASH", "CASH"),
            start_time=start,
            end_time=end,
            interval_in_minutes=minutes,
        )
        return extract_candles(resp)


def load_stock_history(item):
    try:
        entry_tf = engine.settings["entry_timeframe"]
        tide_tf = engine.settings["tide_timeframe"]
        entry_candles = fetch_history(item, entry_tf)
        tide_candles = fetch_history(item, tide_tf)
        if entry_candles:
            engine.set_history(item["symbol"], entry_tf, entry_candles)
        if tide_candles:
            engine.set_history(item["symbol"], tide_tf, tide_candles)

        # Wave timeframe is fetched directly when it differs from entry/tide.
        wave_tf = engine.settings["wave_timeframe"]
        if wave_tf not in {entry_tf, tide_tf}:
            wave_candles = fetch_history(item, wave_tf)
            if wave_candles:
                engine.set_history(item["symbol"], wave_tf, wave_candles)
        return bool(entry_candles)
    except Exception as exc:
        return False


def load_history_all():
    if not groww or not stocks:
        return
    state["status"] = "loading"
    state["message"] = "Loading historical candles for the F&O universe..."
    loaded = 0
    # Five concurrent requests keeps the workload comfortably below Groww's live-data rate limit.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(load_stock_history, item) for item in stocks]
        for future in as_completed(futures):
            try:
                if future.result():
                    loaded += 1
            except Exception:
                pass
            state["history_loaded"] = loaded
            state["last_update"] = now_iso()
    state["status"] = "live" if state["feed_connected"] else "ready"
    state["message"] = f"Live scanner ready. Historical candles loaded for {loaded}/{len(stocks)} stocks."


def feed_worker(items):
    global feed_obj
    if not groww or GrowwFeed is None or not items:
        return
    try:
        feed_obj = GrowwFeed(groww)
        instruments = [{
            "exchange": "NSE",
            "segment": "CASH",
            "exchange_token": x["exchange_token"]
        } for x in items[:1000]]
        token_to_symbol = {x["exchange_token"]: x["symbol"] for x in items}

        def on_data(_meta):
            try:
                data = feed_obj.get_ltp() or {}
                nse = data.get("ltp", data).get("NSE", {})
                cash = nse.get("CASH", {})
                for token, payload in cash.items():
                    sym = token_to_symbol.get(str(token))
                    if not sym or not isinstance(payload, dict):
                        continue
                    price = payload.get("ltp")
                    if price is None:
                        continue
                    ts_ms = float(payload.get("tsInMillis", time.time() * 1000))
                    engine.update_tick(sym, {
                        "ltp": float(price),
                        "ts": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
                    })
                state["last_update"] = now_iso()
            except Exception:
                pass

        feed_obj.subscribe_ltp(instruments, on_data_received=on_data)
        state["feed_connected"] = True
        state["status"] = "live"
        feed_obj.consume()
    except Exception as exc:
        state["feed_connected"] = False
        state["status"] = "error"
        state["message"] = f"Feed error: {exc}"


def start_services():
    items = load_universe()
    if not items:
        return
    fetch_initial_ltp(items)
    global feed_thread, history_thread
    feed_thread = threading.Thread(target=feed_worker, args=(items,), daemon=True)
    feed_thread.start()
    # History loads independently so the live feed can connect immediately.
    history_thread = threading.Thread(target=load_history_all, daemon=True)
    history_thread.start()


@app.on_event("startup")
def startup():
    threading.Thread(target=start_services, daemon=True).start()


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/status")
def api_status():
    return {**state, "settings": engine.settings, "timestamp": now_iso()}


@app.get("/api/scanner")
def api_scanner():
    return {"status": state["status"], "stocks": engine.snapshot(), "timestamp": now_iso()}


@app.get("/api/settings")
def get_settings():
    return engine.settings


@app.post("/api/settings")
async def set_settings(payload: dict[str, Any]):
    try:
        old = engine.settings.copy()
        engine.update_settings(payload)
        changed_tf = any(engine.settings[k] != old[k] for k in ("wave_timeframe", "tide_timeframe", "entry_timeframe"))
        if changed_tf and stocks and groww:
            threading.Thread(target=load_history_all, daemon=True).start()
        return {"ok": True, "settings": engine.settings}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/reset")
def reset_settings():
    old = engine.settings.copy()
    engine.update_settings(DEFAULT_SETTINGS.copy())
    if stocks and groww and any(engine.settings[k] != old[k] for k in ("wave_timeframe", "tide_timeframe", "entry_timeframe")):
        threading.Thread(target=load_history_all, daemon=True).start()
    return {"ok": True, "settings": engine.settings}


@app.get("/health")
def health():
    return {"ok": True, "status": state["status"], "feed_connected": state["feed_connected"], "history_loaded": state["history_loaded"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
