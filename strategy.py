from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import math
import threading
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_SETTINGS = {
    "wave_timeframe": "15m",
    "tide_timeframe": "1h",
    "entry_timeframe": "5m",
    "ema_fast": 9,
    "ema_mid": 20,
    "ema_slow": 50,
    "rsi_length": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "stoch_k": 14,
    "stoch_d": 3,
    "stoch_smooth": 3,
    "volume_sma": 20,
    "sr_lookback": 160,
    "pivot": 3,
    "buy_threshold": 70,
    "sell_threshold": 30,
    "min_confirmation": 7,
    "minimum_rr": 2.0,
}


def _safe_float(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _timeframe_minutes(tf: str) -> int:
    value = str(tf).strip().lower()
    if value.endswith("m"):
        return max(1, int(value[:-1]))
    if value.endswith("h"):
        return max(1, int(value[:-1])) * 60
    if value.endswith("d"):
        return max(1, int(value[:-1])) * 1440
    return 5


class ScannerEngine:
    """Candle-based Indian F&O scanner using the strategy used by the prior scanner."""

    def __init__(self, settings=None):
        self.settings = DEFAULT_SETTINGS.copy()
        self.settings.update(settings or {})
        self.candles = defaultdict(lambda: defaultdict(lambda: deque(maxlen=2500)))
        self.live_bars = defaultdict(dict)
        self.ticks = {}
        self.signals = {}
        self.lock = threading.RLock()

    def update_settings(self, payload):
        numeric_int = {
            "ema_fast", "ema_mid", "ema_slow", "rsi_length", "rsi_overbought",
            "rsi_oversold", "macd_fast", "macd_slow", "macd_signal",
            "stoch_k", "stoch_d", "stoch_smooth", "volume_sma", "sr_lookback",
            "pivot", "buy_threshold", "sell_threshold", "min_confirmation"
        }
        for k, v in payload.items():
            if k not in self.settings:
                continue
            if k in numeric_int:
                v = int(v)
                if v <= 0:
                    raise ValueError(f"{k} must be positive")
            elif k == "minimum_rr":
                v = float(v)
                if v <= 0:
                    raise ValueError("minimum_rr must be positive")
            else:
                v = str(v).strip().lower()
            self.settings[k] = v
        self.recalculate_all()
        return self.settings

    def clear_history(self):
        with self.lock:
            self.candles.clear()
            self.live_bars.clear()
            self.signals.clear()

    def set_history(self, symbol: str, timeframe: str, candles):
        """Load Groww historical candles: [timestamp, open, high, low, close, volume]."""
        tf = str(timeframe).lower()
        parsed = []
        for row in candles or []:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                continue
            try:
                ts = int(float(row[0]))
                if ts > 10_000_000_000:
                    ts //= 1000
                parsed.append({
                    "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                    "open": _safe_float(row[1]),
                    "high": _safe_float(row[2]),
                    "low": _safe_float(row[3]),
                    "close": _safe_float(row[4]),
                    "volume": _safe_float(row[5] if len(row) > 5 else 0),
                })
            except Exception:
                continue
        parsed.sort(key=lambda x: x["timestamp"])
        with self.lock:
            self.candles[symbol][tf].clear()
            for item in parsed[-2400:]:
                self.candles[symbol][tf].append(item)
        self._recalculate(symbol)

    def set_aggregated_history(self, symbol: str, timeframe: str, frame: pd.DataFrame):
        rows = []
        if frame is None or frame.empty:
            return
        for idx, r in frame.iterrows():
            rows.append({
                "timestamp": pd.Timestamp(idx),
                "open": _safe_float(r.get("open")),
                "high": _safe_float(r.get("high")),
                "low": _safe_float(r.get("low")),
                "close": _safe_float(r.get("close")),
                "volume": _safe_float(r.get("volume")),
            })
        self.set_history(symbol, timeframe, [
            [x["timestamp"].timestamp(), x["open"], x["high"], x["low"], x["close"], x["volume"]]
            for x in rows
        ])

    def update_tick(self, symbol, tick):
        with self.lock:
            old = self.ticks.get(symbol, {}).copy()
            old.update(tick)
            self.ticks[symbol] = old
            self._append_live_tick(symbol, old)
            self._recalculate(symbol)

    def _append_live_tick(self, symbol, tick):
        price = _safe_float(tick.get("ltp"))
        if price <= 0:
            return
        ts = pd.Timestamp(tick.get("ts") or datetime.utcnow(), tz="UTC") if not isinstance(tick.get("ts"), pd.Timestamp) else tick["ts"]
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("UTC")
        base_minute = ts.floor("min")
        volume = _safe_float(tick.get("volume"))

        # Build 1-minute bars from the live LTP stream, then resample to configured TFs.
        key = "1m"
        bar = self.live_bars[symbol].get(key)
        if bar is None or bar["timestamp"] != base_minute:
            if bar is not None:
                self._append_bar(symbol, key, bar)
            self.live_bars[symbol][key] = {
                "timestamp": base_minute, "open": price, "high": price,
                "low": price, "close": price, "volume": volume
            }
        else:
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            if volume:
                bar["volume"] = volume

    def _append_bar(self, symbol, timeframe, bar):
        existing = self.candles[symbol][timeframe]
        if existing and existing[-1]["timestamp"] == bar["timestamp"]:
            existing[-1] = bar
        else:
            existing.append(bar.copy())

    def _frame(self, symbol, timeframe):
        rows = list(self.candles[symbol].get(timeframe, []))
        historical = pd.DataFrame(rows).set_index("timestamp").sort_index() if rows else pd.DataFrame()

        # Merge newly formed 1-minute live bars into the historical series so the
        # dashboard continues updating between historical-data refreshes.
        live_rows = list(self.candles[symbol].get("1m", []))
        if live_rows and timeframe != "1m":
            live = pd.DataFrame(live_rows).set_index("timestamp").sort_index()
            mins = _timeframe_minutes(timeframe)
            agg = live.resample(f"{mins}min", origin="start_day").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna()
            if historical.empty:
                return agg
            # Only replace/append periods at or after the first live bar.
            cutoff = agg.index.min()
            historical = historical[historical.index < cutoff]
            return pd.concat([historical, agg]).sort_index()
        if not historical.empty:
            return historical
        return pd.DataFrame()

    @staticmethod
    def _ema(s, length):
        return s.ewm(span=max(1, int(length)), adjust=False).mean()

    @staticmethod
    def _rsi(s, length):
        delta = s.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / max(1, length), adjust=False, min_periods=length).mean()
        avg_loss = loss.ewm(alpha=1 / max(1, length), adjust=False, min_periods=length).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def _indicators(self, df):
        s = self.settings
        if df.empty:
            return df
        out = df.copy()
        out["ema_fast"] = self._ema(out.close, s["ema_fast"])
        out["ema_mid"] = self._ema(out.close, s["ema_mid"])
        out["ema_slow"] = self._ema(out.close, s["ema_slow"])
        out["rsi"] = self._rsi(out.close, s["rsi_length"])
        macd_fast = self._ema(out.close, s["macd_fast"])
        macd_slow = self._ema(out.close, s["macd_slow"])
        out["macd"] = macd_fast - macd_slow
        out["macd_signal"] = self._ema(out.macd, s["macd_signal"])
        low_n = out.low.rolling(s["stoch_k"]).min()
        high_n = out.high.rolling(s["stoch_k"]).max()
        denom = (high_n - low_n).replace(0, np.nan)
        raw_k = 100 * (out.close - low_n) / denom
        out["stoch_k"] = raw_k.rolling(s["stoch_smooth"]).mean().fillna(50)
        out["stoch_d"] = out.stoch_k.rolling(s["stoch_d"]).mean().fillna(50)
        out["volume_sma"] = out.volume.rolling(s["volume_sma"]).mean()
        return out

    @staticmethod
    def _pivots(df, n):
        if df.empty:
            return []
        n = max(1, int(n))
        highs = []
        lows = []
        h = df.high.to_numpy()
        l = df.low.to_numpy()
        for i in range(n, len(df) - n):
            if h[i] >= np.max(h[i-n:i+n+1]):
                highs.append(float(h[i]))
            if l[i] <= np.min(l[i-n:i+n+1]):
                lows.append(float(l[i]))
        return highs, lows

    def _levels(self, df):
        look = max(20, int(self.settings["sr_lookback"]))
        recent = df.tail(look)
        if recent.empty:
            return 0.0, 0.0
        highs, lows = self._pivots(recent, self.settings["pivot"])
        price = float(recent.close.iloc[-1])
        supports = [x for x in lows if x < price]
        resistances = [x for x in highs if x > price]
        support = max(supports) if supports else float(recent.low.min())
        resistance = min(resistances) if resistances else float(recent.high.max())
        return support, resistance

    def _tf_signal(self, symbol, timeframe):
        df = self._indicators(self._frame(symbol, timeframe))
        if len(df) < max(self.settings["ema_slow"], self.settings["macd_slow"], self.settings["rsi_length"]) + 5:
            return "WAIT", {}
        r = df.iloc[-1]
        bullish = r.close > r.ema_fast > r.ema_mid > r.ema_slow and r.ema_mid > r.ema_slow
        bearish = r.close < r.ema_fast < r.ema_mid < r.ema_slow and r.ema_mid < r.ema_slow
        return ("BUY" if bullish else "SELL" if bearish else "WAIT"), r.to_dict()

    def _recalculate(self, symbol):
        entry_tf = self.settings["entry_timeframe"]
        wave_tf = self.settings["wave_timeframe"]
        tide_tf = self.settings["tide_timeframe"]
        entry = self._indicators(self._frame(symbol, entry_tf))
        if len(entry) < max(60, self.settings["ema_slow"] + 5):
            return
        r = entry.iloc[-1]
        price = _safe_float(r.close)
        if price <= 0:
            return

        score = 50.0
        confirmations = 0
        buy_reasons, sell_reasons = [], []

        def check(condition, weight, buy_text, sell_text):
            nonlocal score, confirmations
            if condition is True:
                score += weight
                confirmations += 1
                buy_reasons.append(buy_text)
            elif condition is False:
                score -= weight
                confirmations += 1
                sell_reasons.append(sell_text)

        # 1. Entry EMA structure
        check(bool(r.close > r.ema_fast > r.ema_mid > r.ema_slow), 8, "Entry EMA bullish", "Entry EMA bearish")
        # 2. 20/50 trend filter
        check(bool(r.ema_mid > r.ema_slow), 7, "20/50 bullish filter", "20/50 bearish filter")
        # 3. RSI direction
        check(bool(r.rsi >= 50), 6, f"RSI {r.rsi:.1f} bullish", f"RSI {r.rsi:.1f} bearish")
        # 4. MACD
        check(bool(r.macd > r.macd_signal), 7, "MACD bullish", "MACD bearish")
        # 5. Stochastic
        check(bool(r.stoch_k > r.stoch_d), 5, "Stochastic bullish", "Stochastic bearish")
        # 6. Volume confirmation
        volume_ok = bool(r.volume_sma and r.volume >= r.volume_sma)
        if volume_ok:
            confirmations += 1
            buy_reasons.append("Volume above SMA")
            sell_reasons.append("Volume above SMA")
        # 7. Price vs previous close
        prev_close = _safe_float(entry.close.iloc[-2])
        check(bool(price >= prev_close), 4, "Price momentum positive", "Price momentum negative")

        wave, _ = self._tf_signal(symbol, wave_tf)
        tide, _ = self._tf_signal(symbol, tide_tf)
        if wave == "BUY":
            score += 7; confirmations += 1; buy_reasons.append(f"Wave {wave_tf} BUY")
        elif wave == "SELL":
            score -= 7; confirmations += 1; sell_reasons.append(f"Wave {wave_tf} SELL")
        if tide == "BUY":
            score += 7; confirmations += 1; buy_reasons.append(f"Tide {tide_tf} BUY")
        elif tide == "SELL":
            score -= 7; confirmations += 1; sell_reasons.append(f"Tide {tide_tf} SELL")

        support, resistance = self._levels(entry)
        room_long = resistance - price if resistance else 0
        room_short = price - support if support else 0
        risk_long = price - support if support and support < price else 0
        risk_short = resistance - price if resistance and resistance > price else 0
        long_rr = room_long / risk_long if risk_long > 0 else 0
        short_rr = room_short / risk_short if risk_short > 0 else 0

        # S/R is both a confirmation and the actual 1:R target calculation.
        if support and price > support:
            confirmations += 1
            buy_reasons.append("Price above support")
        if resistance and price < resistance:
            confirmations += 1
            sell_reasons.append("Price below resistance")

        score = max(0, min(100, score))
        min_conf = int(self.settings["min_confirmation"])
        min_rr = float(self.settings["minimum_rr"])
        buy_ok = score >= float(self.settings["buy_threshold"]) and confirmations >= min_conf and wave == "BUY" and tide == "BUY" and long_rr >= min_rr
        sell_ok = score <= float(self.settings["sell_threshold"]) and confirmations >= min_conf and wave == "SELL" and tide == "SELL" and short_rr >= min_rr
        if buy_ok:
            signal, trend, rr = "BUY", "BULLISH", long_rr
            reasons = buy_reasons
            sl, target = support, price + max(0, risk_long * min_rr)
        elif sell_ok:
            signal, trend, rr = "SELL", "BEARISH", short_rr
            reasons = sell_reasons
            sl, target = resistance, price - max(0, risk_short * min_rr)
        else:
            signal, trend = "WAIT", "BULLISH" if score > 50 else "BEARISH" if score < 50 else "NEUTRAL"
            rr = max(long_rr, short_rr)
            reasons = buy_reasons if score >= 50 else sell_reasons
            sl, target = support if score >= 50 else resistance, 0.0

        tick = self.ticks.get(symbol, {})
        self.signals[symbol] = {
            "symbol": symbol,
            "ltp": price,
            "change_pct": _safe_float(tick.get("change_pct")),
            "volume": _safe_float(r.volume),
            "oi": _safe_float(tick.get("oi")),
            "wave": wave,
            "tide": tide,
            "entry": entry_tf,
            "score": round(score, 2),
            "confirmation": confirmations,
            "signal": signal,
            "trend": trend,
            "rr": round(rr, 2),
            "support": round(support, 2) if support else 0,
            "resistance": round(resistance, 2) if resistance else 0,
            "sl": round(sl, 2) if sl else 0,
            "target": round(target, 2) if target else 0,
            "rsi": round(float(r.rsi), 2),
            "macd": round(float(r.macd), 4),
            "macd_signal": round(float(r.macd_signal), 4),
            "stoch_k": round(float(r.stoch_k), 2),
            "stoch_d": round(float(r.stoch_d), 2),
            "volume_sma": round(_safe_float(r.volume_sma), 2),
            "reasons": reasons[:8],
            "updated": tick.get("ts"),
        }

    def recalculate_all(self):
        with self.lock:
            for symbol in set(self.ticks.keys()) | set(self.candles.keys()):
                self._recalculate(symbol)

    def snapshot(self):
        with self.lock:
            rows = list(self.signals.values())
        rows.sort(key=lambda x: (-float(x.get("score", 0)), x["symbol"]))
        return rows
