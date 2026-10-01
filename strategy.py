import math
import threading
from datetime import datetime, timezone

import pandas as pd
import numpy as np


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SETTINGS = {
    # Timeframes
    "entry_timeframe": "5m",
    "wave_timeframe": "15m",
    "tide_timeframe": "1h",

    # EMA
    "ema_fast": 9,
    "ema_mid": 20,
    "ema_slow": 50,

    # Trend filter
    "trend_fast": 20,
    "trend_slow": 50,

    # RSI
    "rsi_length": 14,

    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # Stochastic
    "stoch_length": 14,
    "stoch_smooth": 3,

    # Volume
    "volume_sma": 20,

    # Support / Resistance
    "sr_lookback": 160,
    "pivot": 3,

    # Signal
    "base_score": 50,
    "buy_score": 70,
    "sell_score": 30,
    "minimum_confirmation": 7,

    # Risk reward
    "risk_reward": 2.0,

    # Minimum candles
    "minimum_candles": 60,
}


# ============================================================
# NUMERIC HELPERS
# ============================================================

def safe_float(value, default=np.nan):

    try:

        if value is None:
            return default

        if isinstance(value, str):

            value = value.strip()

            if not value:
                return default

        result = float(value)

        if math.isfinite(result):
            return result

        return default

    except Exception:

        return default


def clamp(value, low, high):

    return max(
        low,
        min(high, value)
    )


# ============================================================
# TIMESTAMP PARSER
# ============================================================

def parse_timestamp(value):

    """
    Supports Groww candle timestamps such as:

        2025-09-24T10:30:00

    and:

        2025-09-24T10:30:00+05:30

    and Unix timestamps in seconds/milliseconds.
    """

    if value is None:
        return None

    # --------------------------------------------------------
    # Numeric timestamp
    # --------------------------------------------------------

    if isinstance(
        value,
        (int, float, np.integer, np.floating)
    ):

        try:

            number = float(value)

            # Milliseconds
            if number > 100000000000:

                return datetime.fromtimestamp(
                    number / 1000,
                    tz=timezone.utc
                )

            # Seconds
            return datetime.fromtimestamp(
                number,
                tz=timezone.utc
            )

        except Exception:

            return None

    # --------------------------------------------------------
    # String timestamp
    # --------------------------------------------------------

    text = str(value).strip()

    if not text:
        return None

    # Numeric string
    try:

        number = float(text)

        if math.isfinite(number):

            if number > 100000000000:

                return datetime.fromtimestamp(
                    number / 1000,
                    tz=timezone.utc
                )

            if number > 1000000000:

                return datetime.fromtimestamp(
                    number,
                    tz=timezone.utc
                )

    except Exception:
        pass

    # ISO timestamp
    try:

        normalized = text.replace(
            "Z",
            "+00:00"
        )

        dt = datetime.fromisoformat(
            normalized
        )

        if dt.tzinfo is None:

            # Groww/NSE timestamps without an
            # offset are treated as IST.
            from datetime import timedelta

            ist = timezone(
                timedelta(
                    hours=5,
                    minutes=30
                )
            )

            dt = dt.replace(
                tzinfo=ist
            )

        return dt

    except Exception:
        pass

    # Pandas fallback
    try:

        dt = pd.to_datetime(
            text,
            errors="coerce"
        )

        if pd.isna(dt):
            return None

        if dt.tzinfo is None:

            from datetime import timedelta

            ist = timezone(
                timedelta(
                    hours=5,
                    minutes=30
                )
            )

            dt = dt.tz_localize(
                ist
            )

        return dt.to_pydatetime()

    except Exception:

        return None


# ============================================================
# CANDLE NORMALIZATION
# ============================================================

def normalize_candles(candles):

    """
    Converts Groww candle response into:

        timestamp
        open
        high
        low
        close
        volume
        open_interest

    Supports:

        [
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            open_interest
        ]

    and dictionary-style candles.
    """

    if candles is None:
        return pd.DataFrame()

    if not isinstance(
        candles,
        list
    ):
        return pd.DataFrame()

    rows = []

    for row in candles:

        try:

            # ------------------------------------------------
            # Dictionary format
            # ------------------------------------------------

            if isinstance(
                row,
                dict
            ):

                timestamp = (
                    row.get("timestamp")
                    or row.get("time")
                    or row.get("datetime")
                    or row.get("date")
                )

                open_price = (
                    row.get("open")
                    or row.get("open_price")
                )

                high_price = (
                    row.get("high")
                    or row.get("high_price")
                )

                low_price = (
                    row.get("low")
                    or row.get("low_price")
                )

                close_price = (
                    row.get("close")
                    or row.get("close_price")
                )

                volume = (
                    row.get("volume")
                    or 0
                )

                open_interest = (
                    row.get("open_interest")
                    or row.get("oi")
                    or 0
                )

            # ------------------------------------------------
            # List format
            # ------------------------------------------------

            elif isinstance(
                row,
                (list, tuple)
            ):

                if len(row) < 5:
                    continue

                timestamp = row[0]
                open_price = row[1]
                high_price = row[2]
                low_price = row[3]
                close_price = row[4]

                volume = (
                    row[5]
                    if len(row) > 5
                    else 0
                )

                open_interest = (
                    row[6]
                    if len(row) > 6
                    else 0
                )

            else:

                continue

            timestamp = parse_timestamp(
                timestamp
            )

            if timestamp is None:
                continue

            open_price = safe_float(
                open_price
            )

            high_price = safe_float(
                high_price
            )

            low_price = safe_float(
                low_price
            )

            close_price = safe_float(
                close_price
            )

            volume = safe_float(
                volume,
                0
            )

            open_interest = safe_float(
                open_interest,
                0
            )

            if any(
                pd.isna(x)
                for x in [
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                ]
            ):
                continue

            rows.append({
                "timestamp": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
                "open_interest": open_interest,
            })

        except Exception:

            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows
    )

    # Remove duplicate timestamps.
    df = df.drop_duplicates(
        subset=["timestamp"],
        keep="last"
    )

    # Sort oldest → newest.
    df = df.sort_values(
        "timestamp"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# EMA
# ============================================================

def ema(series, length):

    length = max(
        1,
        int(length)
    )

    return series.ewm(
        span=length,
        adjust=False,
        min_periods=length
    ).mean()


# ============================================================
# RSI
# ============================================================

def rsi(series, length=14):

    length = max(
        1,
        int(length)
    )

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    result = 100 - (
        100 / (1 + rs)
    )

    return result.fillna(50)


# ============================================================
# MACD
# ============================================================

def macd(
    series,
    fast=12,
    slow=26,
    signal=9
):

    fast_ema = ema(
        series,
        fast
    )

    slow_ema = ema(
        series,
        slow
    )

    macd_line = (
        fast_ema -
        slow_ema
    )

    signal_line = ema(
        macd_line,
        signal
    )

    histogram = (
        macd_line -
        signal_line
    )

    return (
        macd_line,
        signal_line,
        histogram
    )


# ============================================================
# STOCHASTIC
# ============================================================

def stochastic(
    df,
    length=14,
    smooth=3
):

    length = max(
        1,
        int(length)
    )

    smooth = max(
        1,
        int(smooth)
    )

    lowest = df["low"].rolling(
        length
    ).min()

    highest = df["high"].rolling(
        length
    ).max()

    denominator = (
        highest -
        lowest
    )

    raw_k = (
        (
            df["close"] -
            lowest
        )
        /
        denominator.replace(
            0,
            np.nan
        )
        * 100
    )

    k = raw_k.rolling(
        smooth
    ).mean()

    d = k.rolling(
        smooth
    ).mean()

    return (
        k.fillna(50),
        d.fillna(50)
    )


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def support_resistance(
    df,
    lookback=160,
    pivot=3
):

    if df.empty:
        return (
            np.nan,
            np.nan
        )

    lookback = max(
        10,
        int(lookback)
    )

    pivot = max(
        1,
        int(pivot)
    )

    recent = df.tail(
        lookback
    )

    # --------------------------------------------------------
    # Pivot-based levels
    # --------------------------------------------------------

    highs = recent["high"].values
    lows = recent["low"].values

    resistance_values = []
    support_values = []

    for i in range(
        pivot,
        len(recent) - pivot
    ):

        current_high = highs[i]

        left_highs = highs[
            i - pivot:i
        ]

        right_highs = highs[
            i + 1:i + pivot + 1
        ]

        if (
            current_high >=
            np.max(left_highs)
            and
            current_high >=
            np.max(right_highs)
        ):

            resistance_values.append(
                current_high
            )

        current_low = lows[i]

        left_lows = lows[
            i - pivot:i
        ]

        right_lows = lows[
            i + 1:i + pivot + 1
        ]

        if (
            current_low <=
            np.min(left_lows)
            and
            current_low <=
            np.min(right_lows)
        ):

            support_values.append(
                current_low
            )

    price = float(
        recent["close"].iloc[-1]
    )

    # --------------------------------------------------------
    # Select nearest levels
    # --------------------------------------------------------

    supports = [
        x
        for x in support_values
        if x < price
    ]

    resistances = [
        x
        for x in resistance_values
        if x > price
    ]

    # Fallback to rolling levels.
    if supports:

        support = max(
            supports
        )

    else:

        support = float(
            recent["low"].min()
        )

    if resistances:

        resistance = min(
            resistances
        )

    else:

        resistance = float(
            recent["high"].max()
        )

    return (
        support,
        resistance
    )


# ============================================================
# INDICATOR CALCULATION
# ============================================================

def calculate_indicators(
    candles,
    settings
):

    df = normalize_candles(
        candles
    )

    if df.empty:
        return df

    minimum = int(
        settings.get(
            "minimum_candles",
            60
        )
    )

    # We can calculate with fewer candles,
    # but signal quality improves with enough history.
    if len(df) < max(
        20,
        minimum
    ):

        # Continue calculation anyway.
        pass

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    df["ema_fast"] = ema(
        df["close"],
        settings[
            "ema_fast"
        ]
    )

    df["ema_mid"] = ema(
        df["close"],
        settings[
            "ema_mid"
        ]
    )

    df["ema_slow"] = ema(
        df["close"],
        settings[
            "ema_slow"
        ]
    )

    # Trend filter
    df["trend_fast"] = ema(
        df["close"],
        settings[
            "trend_fast"
        ]
    )

    df["trend_slow"] = ema(
        df["close"],
        settings[
            "trend_slow"
        ]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    df["rsi"] = rsi(
        df["close"],
        settings[
            "rsi_length"
        ]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    (
        df["macd"],
        df["macd_signal"],
        df["macd_hist"]
    ) = macd(
        df["close"],
        settings[
            "macd_fast"
        ],
        settings[
            "macd_slow"
        ],
        settings[
            "macd_signal"
        ]
    )

    # --------------------------------------------------------
    # STOCHASTIC
    # --------------------------------------------------------

    (
        df["stoch_k"],
        df["stoch_d"]
    ) = stochastic(
        df,
        settings[
            "stoch_length"
        ],
        settings[
            "stoch_smooth"
        ]
    )

    # --------------------------------------------------------
    # VOLUME SMA
    # --------------------------------------------------------

    volume_period = max(
        1,
        int(
            settings[
                "volume_sma"
            ]
        )
    )

    df["volume_sma"] = (
        df["volume"]
        .rolling(
            volume_period
        )
        .mean()
    )

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    support, resistance = (
        support_resistance(
            df,
            settings[
                "sr_lookback"
            ],
            settings[
                "pivot"
            ]
        )
    )

    df["support"] = support
    df["resistance"] = resistance

    return df


# ============================================================
# TIMEFRAME TREND
# ============================================================

def timeframe_direction(
    df,
    settings
):

    if df is None:
        return "WAIT"

    if df.empty:
        return "WAIT"

    row = df.iloc[-1]

    close = safe_float(
        row.get("close")
    )

    fast = safe_float(
        row.get("ema_fast")
    )

    mid = safe_float(
        row.get("ema_mid")
    )

    slow = safe_float(
        row.get("ema_slow")
    )

    if any(
        pd.isna(x)
        for x in [
            close,
            fast,
            mid,
            slow,
        ]
    ):
        return "WAIT"

    if (
        close > fast
        and
        fast > mid
        and
        mid > slow
    ):

        return "BUY"

    if (
        close < fast
        and
        fast < mid
        and
        mid < slow
    ):

        return "SELL"

    return "WAIT"


# ============================================================
# SCORE ENGINE
# ============================================================

def score_entry(
    entry_df,
    wave_direction,
    tide_direction,
    settings
):

    if (
        entry_df is None
        or entry_df.empty
    ):

        return {
            "signal": "WAIT",
            "score": 50,
            "confirmation": 0,
            "reasons": [],
        }

    row = entry_df.iloc[-1]

    close = safe_float(
        row.get("close")
    )

    ema_fast_value = safe_float(
        row.get("ema_fast")
    )

    ema_mid_value = safe_float(
        row.get("ema_mid")
    )

    ema_slow_value = safe_float(
        row.get("ema_slow")
    )

    trend_fast_value = safe_float(
        row.get("trend_fast")
    )

    trend_slow_value = safe_float(
        row.get("trend_slow")
    )

    rsi_value = safe_float(
        row.get("rsi"),
        50
    )

    macd_value = safe_float(
        row.get("macd"),
        0
    )

    macd_signal_value = safe_float(
        row.get("macd_signal"),
        0
    )

    macd_hist_value = safe_float(
        row.get("macd_hist"),
        0
    )

    stoch_k = safe_float(
        row.get("stoch_k"),
        50
    )

    stoch_d = safe_float(
        row.get("stoch_d"),
        50
    )

    volume_value = safe_float(
        row.get("volume"),
        0
    )

    volume_sma = safe_float(
        row.get("volume_sma"),
        0
    )

    support = safe_float(
        row.get("support")
    )

    resistance = safe_float(
        row.get("resistance")
    )

    score = int(
        settings.get(
            "base_score",
            50
        )
    )

    buy_confirmations = 0
    sell_confirmations = 0

    buy_reasons = []
    sell_reasons = []

    # --------------------------------------------------------
    # EMA alignment
    # --------------------------------------------------------

    if (
        close > ema_fast_value
        and
        ema_fast_value > ema_mid_value
        and
        ema_mid_value > ema_slow_value
    ):

        score += 8
        buy_confirmations += 1

        buy_reasons.append(
            "EMA bullish alignment"
        )

    elif (
        close < ema_fast_value
        and
        ema_fast_value < ema_mid_value
        and
        ema_mid_value < ema_slow_value
    ):

        score -= 8
        sell_confirmations += 1

        sell_reasons.append(
            "EMA bearish alignment"
        )

    # --------------------------------------------------------
    # 20/50 trend filter
    # --------------------------------------------------------

    if (
        close > trend_fast_value
        and
        trend_fast_value > trend_slow_value
    ):

        score += 7
        buy_confirmations += 1

        buy_reasons.append(
            "20/50 bullish trend"
        )

    elif (
        close < trend_fast_value
        and
        trend_fast_value < trend_slow_value
    ):

        score -= 7
        sell_confirmations += 1

        sell_reasons.append(
            "20/50 bearish trend"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if rsi_value >= 55:

        score += 5
        buy_confirmations += 1

        buy_reasons.append(
            "RSI bullish"
        )

    elif rsi_value <= 45:

        score -= 5
        sell_confirmations += 1

        sell_reasons.append(
            "RSI bearish"
        )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if (
        macd_value > macd_signal_value
        and
        macd_hist_value > 0
    ):

        score += 6
        buy_confirmations += 1

        buy_reasons.append(
            "MACD bullish"
        )

    elif (
        macd_value < macd_signal_value
        and
        macd_hist_value < 0
    ):

        score -= 6
        sell_confirmations += 1

        sell_reasons.append(
            "MACD bearish"
        )

    # --------------------------------------------------------
    # Stochastic
    # --------------------------------------------------------

    if (
        stoch_k > stoch_d
        and
        stoch_k >= 50
    ):

        score += 4
        buy_confirmations += 1

        buy_reasons.append(
            "Stochastic bullish"
        )

    elif (
        stoch_k < stoch_d
        and
        stoch_k <= 50
    ):

        score -= 4
        sell_confirmations += 1

        sell_reasons.append(
            "Stochastic bearish"
        )

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    if (
        volume_sma > 0
        and
        volume_value > volume_sma
    ):

        if close > ema_mid_value:

            score += 5
            buy_confirmations += 1

            buy_reasons.append(
                "Volume above average"
            )

        elif close < ema_mid_value:

            score -= 5
            sell_confirmations += 1

            sell_reasons.append(
                "Volume above average"
            )

    # --------------------------------------------------------
    # Wave
    # --------------------------------------------------------

    if wave_direction == "BUY":

        score += 6
        buy_confirmations += 1

        buy_reasons.append(
            "Wave BUY"
        )

    elif wave_direction == "SELL":

        score -= 6
        sell_confirmations += 1

        sell_reasons.append(
            "Wave SELL"
        )

    # --------------------------------------------------------
    # Tide
    # --------------------------------------------------------

    if tide_direction == "BUY":

        score += 6
        buy_confirmations += 1

        buy_reasons.append(
            "Tide BUY"
        )

    elif tide_direction == "SELL":

        score -= 6
        sell_confirmations += 1

        sell_reasons.append(
            "Tide SELL"
        )

    # --------------------------------------------------------
    # Support / Resistance
    # --------------------------------------------------------

    if not pd.isna(
        support
    ):

        distance_support = (
            close - support
        ) / close * 100

        if (
            0 <= distance_support <= 2
        ):

            score += 3
            buy_confirmations += 1

            buy_reasons.append(
                "Near support"
            )

    if not pd.isna(
        resistance
    ):

        distance_resistance = (
            resistance - close
        ) / close * 100

        if (
            0 <= distance_resistance <= 2
        ):

            score -= 3
            sell_confirmations += 1

            sell_reasons.append(
                "Near resistance"
            )

    score = int(
        clamp(
            score,
            0,
            100
        )
    )

    # --------------------------------------------------------
    # Final signal
    # --------------------------------------------------------

    buy_threshold = int(
        settings.get(
            "buy_score",
            70
        )
    )

    sell_threshold = int(
        settings.get(
            "sell_score",
            30
        )
    )

    minimum_confirmation = int(
        settings.get(
            "minimum_confirmation",
            7
        )
    )

    signal = "WAIT"

    reasons = []

    if (
        score >= buy_threshold
        and
        wave_direction == "BUY"
        and
        tide_direction == "BUY"
        and
        buy_confirmations >=
        minimum_confirmation
    ):

        signal = "BUY"

        reasons = buy_reasons

    elif (
        score <= sell_threshold
        and
        wave_direction == "SELL"
        and
        tide_direction == "SELL"
        and
        sell_confirmations >=
        minimum_confirmation
    ):

        signal = "SELL"

        reasons = sell_reasons

    else:

        if score >= 50:

            reasons = buy_reasons

        else:

            reasons = sell_reasons

    return {
        "signal": signal,
        "score": score,
        "confirmation": max(
            buy_confirmations,
            sell_confirmations
        ),
        "buy_confirmation": buy_confirmations,
        "sell_confirmation": sell_confirmations,
        "reasons": reasons,
    }


# ============================================================
# RISK / REWARD
# ============================================================

def calculate_risk_reward(
    entry,
    signal,
    support,
    resistance,
    settings
):

    entry = safe_float(
        entry
    )

    support = safe_float(
        support
    )

    resistance = safe_float(
        resistance
    )

    rr = safe_float(
        settings.get(
            "risk_reward",
            2.0
        ),
        2.0
    )

    if pd.isna(entry):
        return {
            "stop_loss": None,
            "target": None,
            "risk": None,
        }

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if signal == "BUY":

        if (
            not pd.isna(support)
            and
            support < entry
        ):

            stop = support

        else:

            # fallback: 1% risk
            stop = entry * 0.99

        risk = entry - stop

        if risk <= 0:

            return {
                "stop_loss": None,
                "target": None,
                "risk": None,
            }

        target = (
            entry +
            risk * rr
        )

        return {
            "stop_loss": stop,
            "target": target,
            "risk": risk,
        }

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    if signal == "SELL":

        if (
            not pd.isna(resistance)
            and
            resistance > entry
        ):

            stop = resistance

        else:

            # fallback: 1% risk
            stop = entry * 1.01

        risk = stop - entry

        if risk <= 0:

            return {
                "stop_loss": None,
                "target": None,
                "risk": None,
            }

        target = (
            entry -
            risk * rr
        )

        return {
            "stop_loss": stop,
            "target": target,
            "risk": risk,
        }

    return {
        "stop_loss": None,
        "target": None,
        "risk": None,
    }


# ============================================================
# SCANNER ENGINE
# ============================================================

class ScannerEngine:

    def __init__(
        self,
        settings=None
    ):

        self.settings = (
            DEFAULT_SETTINGS.copy()
            if settings is None
            else settings.copy()
        )

        self.history = {}
        self.results = {}
        self.ticks = {}

        self.lock = threading.RLock()

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    def update_settings(
        self,
        updates
    ):

        if not isinstance(
            updates,
            dict
        ):
            return

        with self.lock:

            for key, value in updates.items():

                if key not in self.settings:
                    continue

                current = self.settings[
                    key
                ]

                try:

                    if isinstance(
                        current,
                        int
                    ):

                        value = int(
                            value
                        )

                    elif isinstance(
                        current,
                        float
                    ):

                        value = float(
                            value
                        )

                    elif isinstance(
                        current,
                        str
                    ):

                        value = str(
                            value
                        )

                except Exception:
                    continue

                self.settings[
                    key
                ] = value

    # --------------------------------------------------------
    # CLEAR HISTORY
    # --------------------------------------------------------

    def clear_history(self):

        with self.lock:

            self.history.clear()
            self.results.clear()

    # --------------------------------------------------------
    # SET HISTORY
    # --------------------------------------------------------

    def set_history(
        self,
        symbol,
        timeframe,
        candles
    ):

        df = calculate_indicators(
            candles,
            self.settings
        )

        if df.empty:
            return False

        with self.lock:

            self.history[
                (
                    symbol,
                    timeframe
                )
            ] = df

        return True

    # --------------------------------------------------------
    # TICK
    # --------------------------------------------------------

    def update_tick(
        self,
        symbol,
        data
    ):

        with self.lock:

            self.ticks[
                symbol
            ] = {
                **self.ticks.get(
                    symbol,
                    {}
                ),
                **data,
            }

            # Update latest close.
            for (
                key
            ), df in list(
                self.history.items()
            ):

                if key[0] != symbol:
                    continue

                if df.empty:
                    continue

                price = safe_float(
                    data.get(
                        "ltp"
                    )
                )

                if pd.isna(price):
                    continue

                self.history[
                    key
                ].iat[
                    -1,
                    self.history[
                        key
                    ].columns.get_loc(
                        "close"
                    )
                ] = price

    # --------------------------------------------------------
    # GET HISTORY
    # --------------------------------------------------------

    def get_history(
        self,
        symbol,
        timeframe
    ):

        return self.history.get(
            (
                symbol,
                timeframe
            )
        )

    # --------------------------------------------------------
    # RECALCULATE ONE
    # --------------------------------------------------------

    def calculate_symbol(
        self,
        symbol
    ):

        entry_tf = self.settings[
            "entry_timeframe"
        ]

        wave_tf = self.settings[
            "wave_timeframe"
        ]

        tide_tf = self.settings[
            "tide_timeframe"
        ]

        entry_df = self.get_history(
            symbol,
            entry_tf
        )

        wave_df = self.get_history(
            symbol,
            wave_tf
        )

        tide_df = self.get_history(
            symbol,
            tide_tf
        )

        if (
            entry_df is None
            or entry_df.empty
        ):

            return None

        # Recalculate indicators if settings
        # changed.
        entry_df = calculate_indicators(
            entry_df[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "open_interest",
                ]
            ].to_dict(
                "records"
            ),
            self.settings
        )

        if (
            wave_df is not None
            and not wave_df.empty
        ):

            wave_df = calculate_indicators(
                wave_df[
                    [
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "open_interest",
                    ]
                ].to_dict(
                    "records"
                ),
                self.settings
            )

        if (
            tide_df is not None
            and not tide_df.empty
        ):

            tide_df = calculate_indicators(
                tide_df[
                    [
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "open_interest",
                    ]
                ].to_dict(
                "records"
                ),
                self.settings
            )

        wave_direction = timeframe_direction(
            wave_df,
            self.settings
        )

        tide_direction = timeframe_direction(
            tide_df,
            self.settings
        )

        scored = score_entry(
            entry_df,
            wave_direction,
            tide_direction,
            self.settings
        )

        row = entry_df.iloc[-1]

        entry_price = safe_float(
            row.get("close")
        )

        support = safe_float(
            row.get("support")
        )

        resistance = safe_float(
            row.get("resistance")
        )

        rr = calculate_risk_reward(
            entry_price,
            scored["signal"],
            support,
            resistance,
            self.settings
        )

        tick = self.ticks.get(
            symbol,
            {}
        )

        ltp = safe_float(
            tick.get(
                "ltp"
            ),
            entry_price
        )

        volume = safe_float(
            row.get(
                "volume"
            ),
            0
        )

        oi = safe_float(
            row.get(
                "open_interest"
            ),
            0
        )

        return {
            "symbol": symbol,

            "ltp": None
            if pd.isna(ltp)
            else round(
                float(ltp),
                2
            ),

            "entry": None
            if pd.isna(entry_price)
            else round(
                float(entry_price),
                2
            ),

            "signal": scored[
                "signal"
            ],

            "score": scored[
                "score"
            ],

            "confirmation": scored[
                "confirmation"
            ],

            "buy_confirmation": scored[
                "buy_confirmation"
            ],

            "sell_confirmation": scored[
                "sell_confirmation"
            ],

            "wave": wave_direction,

            "tide": tide_direction,

            "rsi": round(
                safe_float(
                    row.get(
                        "rsi"
                    ),
                    50
                ),
                2
            ),

            "macd": round(
                safe_float(
                    row.get(
                        "macd"
                    ),
                    0
                ),
                4
            ),

            "macd_signal": round(
                safe_float(
                    row.get(
                        "macd_signal"
                    ),
                    0
                ),
                4
            ),

            "stoch_k": round(
                safe_float(
                    row.get(
                        "stoch_k"
                    ),
                    50
                ),
                2
            ),

            "stoch_d": round(
                safe_float(
                    row.get(
                        "stoch_d"
                    ),
                    50
                ),
                2
            ),

            "volume": volume,

            "open_interest": oi,

            "support": None
            if pd.isna(support)
            else round(
                float(support),
                2
            ),

            "resistance": None
            if pd.isna(resistance)
            else round(
                float(resistance),
                2
            ),

            "stop_loss": rr[
                "stop_loss"
            ],

            "target": rr[
                "target"
            ],

            "risk": rr[
                "risk"
            ],

            "reasons": scored[
                "reasons"
            ],

            "timestamp": str(
                row.get(
                    "timestamp"
                )
            ),
        }

    # --------------------------------------------------------
    # RECALCULATE ALL
    # --------------------------------------------------------

    def recalculate_all(self):

        symbols = set()

        with self.lock:

            for (
                symbol,
                _timeframe
            ) in self.history.keys():

                symbols.add(
                    symbol
                )

        results = {}

        for symbol in symbols:

            try:

                result = self.calculate_symbol(
                    symbol
                )

                if result:

                    results[
                        symbol
                    ] = result

            except Exception as exc:

                print(
                    f"Strategy error "
                    f"{symbol}: "
                    f"{exc}"
                )

        with self.lock:

            self.results = results

    # --------------------------------------------------------
    # SNAPSHOT
    # --------------------------------------------------------

    def snapshot(self):

        self.recalculate_all()

        with self.lock:

            values = list(
                self.results.values()
            )

        # Signal priority first, score second.
        priority = {
            "BUY": 0,
            "SELL": 1,
            "WAIT": 2,
        }

        values.sort(
            key=lambda x: (
                priority.get(
                    x.get(
                        "signal",
                        "WAIT"
                    ),
                    2
                ),
                -float(
                    x.get(
                        "score",
                        0
                    )
                ),
                x.get(
                    "symbol",
                    ""
                )
            )
        )

        return values


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "DEFAULT_SETTINGS",
    "ScannerEngine",
]
