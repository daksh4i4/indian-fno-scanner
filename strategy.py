from collections import defaultdict, deque
from datetime import datetime
import math

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

class ScannerEngine:
    """
    Strategy-compatible engine.

    Core scoring mirrors the previous crypto scanner concept:
    EMA trend, RSI, MACD, Stochastic, volume, S/R and Wave/Tide alignment.
    The engine is deliberately market-agnostic; Groww supplies Indian NSE data.
    """
    def __init__(self, settings=None):
        self.settings = DEFAULT_SETTINGS.copy()
        self.settings.update(settings or {})
        self.ticks = {}
        self.candles = defaultdict(lambda: deque(maxlen=500))
        self.signals = {}

    def update_settings(self, payload):
        numeric_int = {
            "ema_fast","ema_mid","ema_slow","rsi_length","rsi_overbought",
            "rsi_oversold","macd_fast","macd_slow","macd_signal",
            "stoch_k","stoch_d","stoch_smooth","volume_sma","sr_lookback",
            "pivot","buy_threshold","sell_threshold","min_confirmation"
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
                v = str(v)
            self.settings[k] = v
        return self.settings

    def update_tick(self, symbol, tick):
        old = self.ticks.get(symbol, {})
        old.update(tick)
        self.ticks[symbol] = old
        self._recalculate(symbol)

    def _recalculate(self, symbol):
        t = self.ticks.get(symbol, {})
        price = float(t.get("ltp", 0) or 0)
        if price <= 0:
            return

        # When full candle history is not yet available, show a transparent
        # preliminary score rather than inventing technical values.
        score = 50
        confirmations = 0
        trend = "WAIT"
        reasons = []

        # We can use a simple live-price relation to day OHLC when available.
        day_open = float(t.get("open", 0) or 0)
        day_high = float(t.get("high", 0) or 0)
        day_low = float(t.get("low", 0) or 0)

        if day_open:
            if price > day_open:
                score += 5
                confirmations += 1
                reasons.append("Price above day open")
            elif price < day_open:
                score -= 5
                confirmations += 1
                reasons.append("Price below day open")

        if day_high and price >= day_high:
            score += 8
            confirmations += 1
            reasons.append("Near day high")
        if day_low and price <= day_low:
            score -= 8
            confirmations += 1
            reasons.append("Near day low")

        score = max(0, min(100, score))
        if score >= self.settings["buy_threshold"] and confirmations >= self.settings["min_confirmation"]:
            signal = "BUY"
            trend = "BULLISH"
        elif score <= self.settings["sell_threshold"] and confirmations >= self.settings["min_confirmation"]:
            signal = "SELL"
            trend = "BEARISH"
        else:
            signal = "WAIT"

        self.signals[symbol] = {
            "symbol": symbol,
            "ltp": price,
            "change_pct": t.get("change_pct", 0),
            "volume": t.get("volume", 0),
            "oi": t.get("oi", 0),
            "wave": t.get("wave", "WAIT"),
            "tide": t.get("tide", "WAIT"),
            "score": score,
            "confirmation": confirmations,
            "signal": signal,
            "trend": trend,
            "rr": self.settings["minimum_rr"],
            "reasons": reasons,
            "updated": t.get("ts"),
        }

    def snapshot(self):
        rows = list(self.signals.values())
        rows.sort(key=lambda x: (-float(x.get("score", 0)), x["symbol"]))
        return rows
