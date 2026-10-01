import os
import asyncio
import threading
import time
from datetime import datetime, timezone
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

app = FastAPI(title="Indian F&O Intraday Scanner", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

engine = ScannerEngine(DEFAULT_SETTINGS.copy())
state = {
    "status": "starting",
    "message": "Starting scanner...",
    "last_update": None,
    "stocks": [],
    "feed_connected": False,
    "fno_count": 0,
}

feed_thread = None
feed_obj = None
groww = None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def load_universe():
    global groww
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
        url = getattr(groww, "INSTRUMENT_CSV_URL", None)
        if url:
            df = pd.read_csv(url)
        else:
            df = pd.read_csv("https://growwapi-assets.groww.in/instruments/instrument.csv")

        df.columns = [str(c).strip() for c in df.columns]
        # F&O underlyings, excluding index-only underlyings.
        fno = df[(df["exchange"].astype(str).str.upper() == "NSE") &
                 (df["segment"].astype(str).str.upper() == "FNO")].copy()

        underlyings = set(
            fno["underlying_symbol"].dropna().astype(str).str.upper().str.strip()
        )
        index_names = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
        underlyings -= index_names

        cash = df[(df["exchange"].astype(str).str.upper() == "NSE") &
                  (df["segment"].astype(str).str.upper() == "CASH")].copy()
        cash["trading_symbol"] = cash["trading_symbol"].astype(str).str.upper()

        rows = []
        for _, r in cash.iterrows():
            sym = r["trading_symbol"]
            if sym in underlyings:
                rows.append({
                    "symbol": sym,
                    "exchange": "NSE",
                    "segment": "CASH",
                    "exchange_token": str(r["exchange_token"]),
                    "groww_symbol": str(r.get("groww_symbol", f"NSE-{sym}")),
                })

        # Deduplicate by symbol.
        out = {x["symbol"]: x for x in rows}
        stocks = list(out.values())
        stocks.sort(key=lambda x: x["symbol"])
        state["fno_count"] = len(stocks)
        state["status"] = "ready"
        state["message"] = f"{len(stocks)} NSE F&O stocks loaded."
        return stocks
    except Exception as exc:
        state["status"] = "error"
        state["message"] = f"Universe error: {exc}"
        return []

def fetch_initial_ltp(stocks):
    if not groww or not stocks:
        return
    symbols = [f"NSE_{x['symbol']}" for x in stocks]
    # Groww REST LTP accepts up to 50 instruments per call.
    for i in range(0, len(symbols), 50):
        batch = symbols[i:i+50]
        try:
            resp = groww.get_ltp(
                segment=getattr(groww, "SEGMENT_CASH", "CASH"),
                exchange_trading_symbols=tuple(batch),
            )
            for key, value in (resp or {}).items():
                sym = key.replace("NSE_", "")
                engine.update_tick(sym, {"ltp": float(value), "ts": now_iso()})
        except Exception as exc:
            state["message"] = f"Initial LTP warning: {exc}"

def feed_worker(stocks):
    global feed_obj
    if not groww or GrowwFeed is None or not stocks:
        return
    try:
        feed_obj = GrowwFeed(groww)
        instruments = [{
            "exchange": "NSE",
            "segment": "CASH",
            "exchange_token": x["exchange_token"]
        } for x in stocks[:1000]]

        def on_data(_meta):
            try:
                data = feed_obj.get_ltp() or {}
                nse = data.get("NSE", {}).get("CASH", {})
                for token, payload in nse.items():
                    # map token to symbol
                    sym = next((x["symbol"] for x in stocks if x["exchange_token"] == str(token)), None)
                    if sym and isinstance(payload, dict) and payload.get("ltp") is not None:
                        engine.update_tick(sym, {
                            "ltp": float(payload["ltp"]),
                            "ts": datetime.fromtimestamp(
                                float(payload.get("tsInMillis", time.time()*1000))/1000,
                                tz=timezone.utc
                            ).isoformat()
                        })
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
    stocks = load_universe()
    if stocks:
        fetch_initial_ltp(stocks)
        global feed_thread
        feed_thread = threading.Thread(target=feed_worker, args=(stocks,), daemon=True)
        feed_thread.start()
    state["last_update"] = now_iso()

@app.on_event("startup")
def startup():
    threading.Thread(target=start_services, daemon=True).start()

@app.get("/")
def index():
    return FileResponse("static/index.html")

@app.get("/api/status")
def api_status():
    return {
        **state,
        "settings": engine.settings,
        "timestamp": now_iso(),
    }

@app.get("/api/scanner")
def api_scanner():
    return {
        "status": state["status"],
        "stocks": engine.snapshot(),
        "timestamp": now_iso(),
    }

@app.get("/api/settings")
def get_settings():
    return engine.settings

@app.post("/api/settings")
async def set_settings(payload: dict[str, Any]):
    try:
        engine.update_settings(payload)
        return {"ok": True, "settings": engine.settings}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/reset")
def reset_settings():
    engine.update_settings(DEFAULT_SETTINGS.copy())
    return {"ok": True, "settings": engine.settings}

@app.get("/health")
def health():
    return {"ok": True, "status": state["status"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
