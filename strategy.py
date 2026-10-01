# ============================================================
# INDIAN F&O SCANNER
# STRATEGY ENGINE
#
# Wave  : 15m EMA 9/20/50 + indicators + Heikin Ashi
# Tide  : 1h  EMA 9/20/50 + Heikin Ashi
# Filter : EMA 20/50
#
# No automatic order placement.
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SETTINGS = {

    # --------------------------------------------------------
    # TWO TIMEFRAMES ONLY
    # --------------------------------------------------------

    "wave_timeframe": "15m",
    "tide_timeframe": "1h",

    # --------------------------------------------------------
    # WAVE EMA
    # --------------------------------------------------------

    "wave_ema_fast": 9,
    "wave_ema_medium": 20,
    "wave_ema_slow": 50,

    # --------------------------------------------------------
    # TIDE EMA
    # --------------------------------------------------------

    "tide_ema_fast": 9,
    "tide_ema_medium": 20,
    "tide_ema_slow": 50,

    # --------------------------------------------------------
    # FILTER EMA
    # --------------------------------------------------------

    "filter_ema_fast": 20,
    "filter_ema_slow": 50,

    # --------------------------------------------------------
    # HEIKIN ASHI
    # --------------------------------------------------------

    "wave_heikin_ashi": True,
    "tide_heikin_ashi": True,

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    "rsi_period": 14,

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # --------------------------------------------------------
    # STOCHASTIC
    # --------------------------------------------------------

    "stochastic_period": 14,
    "stochastic_smooth": 3,

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    "volume_sma": 20,

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    "sr_lookback": 160,
    "pivot": 3,

    # --------------------------------------------------------
    # SIGNAL CONFIRMATION
    # --------------------------------------------------------

    "min_confirmation": 7,

    # --------------------------------------------------------
    # RISK / REWARD
    # --------------------------------------------------------

    "risk_reward": 2.0,

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    "buy_score": 70,
    "sell_score": 30,

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    "minimum_candles": 60,
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_float(value, default=np.nan):
    try:
        value = float(value)

        if np.isfinite(value):
            return value

        return default

    except Exception:
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


# ============================================================
# HEIKIN ASHI
# ============================================================

def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:

    if df is None or df.empty:
        return pd.DataFrame()

    required = ["open", "high", "low", "close"]

    for column in required:
        if column not in df.columns:
            return pd.DataFrame()

    ha = pd.DataFrame(index=df.index)

    ha["ha_close"] = (
        df["open"]
        + df["high"]
        + df["low"]
        + df["close"]
    ) / 4.0

    ha_open = np.zeros(len(df))

    for i in range(len(df)):

        if i == 0:
            ha_open[i] = (
                df["open"].iloc[i]
                + df["close"].iloc[i]
            ) / 2.0

        else:
            ha_open[i] = (
                ha_open[i - 1]
                + ha["ha_close"].iloc[i - 1]
            ) / 2.0

    ha["ha_open"] = ha_open

    ha["ha_high"] = pd.concat(
        [
            df["high"],
            ha["ha_open"],
            ha["ha_close"],
        ],
        axis=1
    ).max(axis=1)

    ha["ha_low"] = pd.concat(
        [
            df["low"],
            ha["ha_open"],
            ha["ha_close"],
        ],
        axis=1
    ).min(axis=1)

    ha["ha_bullish"] = (
        ha["ha_close"] > ha["ha_open"]
    )

    ha["ha_bearish"] = (
        ha["ha_close"] < ha["ha_open"]
    )

    return ha


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    series: pd.Series,
    period: int
) -> pd.Series:

    return series.ewm(
        span=int(period),
        adjust=False
    ).mean()


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    close: pd.Series,
    period: int = 14
) -> pd.Series:

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    average_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = average_gain / average_loss.replace(
        0,
        np.nan
    )

    rsi = 100 - (
        100 / (1 + rs)
    )

    return rsi.fillna(50)


# ============================================================
# MACD
# ============================================================

def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
):

    ema_fast = calculate_ema(
        close,
        fast
    )

    ema_slow = calculate_ema(
        close,
        slow
    )

    macd = (
        ema_fast
        - ema_slow
    )

    signal_line = calculate_ema(
        macd,
        signal
    )

    histogram = (
        macd
        - signal_line
    )

    return (
        macd,
        signal_line,
        histogram
    )


# ============================================================
# STOCHASTIC
# ============================================================

def calculate_stochastic(
    df: pd.DataFrame,
    period: int = 14,
    smooth: int = 3
):

    lowest_low = (
        df["low"]
        .rolling(period)
        .min()
    )

    highest_high = (
        df["high"]
        .rolling(period)
        .max()
    )

    denominator = (
        highest_high
        - lowest_low
    ).replace(0, np.nan)

    k = (
        (
            df["close"]
            - lowest_low
        )
        / denominator
    ) * 100

    d = (
        k.rolling(smooth)
        .mean()
    )

    return k.fillna(50), d.fillna(50)


# ============================================================
# INDICATOR PREPARATION
# ============================================================

def prepare_dataframe(
    df: pd.DataFrame,
    settings: Dict[str, Any]
) -> pd.DataFrame:

    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()

    data.columns = [
        str(column).lower()
        for column in data.columns
    ]

    required = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in required:

        if column not in data.columns:

            if column == "volume":

                data["volume"] = 0

            else:

                return pd.DataFrame()

    for column in required:

        data[column] = pd.to_numeric(
            data[column],
            errors="coerce"
        )

    data = data.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close"
        ]
    )

    if data.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # WAVE / GENERAL EMA
    # --------------------------------------------------------

    data["ema_9"] = calculate_ema(
        data["close"],
        settings["wave_ema_fast"]
    )

    data["ema_20"] = calculate_ema(
        data["close"],
        settings["wave_ema_medium"]
    )

    data["ema_50"] = calculate_ema(
        data["close"],
        settings["wave_ema_slow"]
    )

    # --------------------------------------------------------
    # FILTER EMA
    # --------------------------------------------------------

    data["filter_ema_fast"] = calculate_ema(
        data["close"],
        settings["filter_ema_fast"]
    )

    data["filter_ema_slow"] = calculate_ema(
        data["close"],
        settings["filter_ema_slow"]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    data["rsi"] = calculate_rsi(
        data["close"],
        settings["rsi_period"]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    (
        data["macd"],
        data["macd_signal"],
        data["macd_hist"]
    ) = calculate_macd(
        data["close"],
        settings["macd_fast"],
        settings["macd_slow"],
        settings["macd_signal"]
    )

    # --------------------------------------------------------
    # STOCHASTIC
    # --------------------------------------------------------

    (
        data["stoch_k"],
        data["stoch_d"]
    ) = calculate_stochastic(
        data,
        settings["stochastic_period"],
        settings["stochastic_smooth"]
    )

    # --------------------------------------------------------
    # VOLUME SMA
    # --------------------------------------------------------

    data["volume_sma"] = (
        data["volume"]
        .rolling(
            settings["volume_sma"]
        )
        .mean()
    )

    # --------------------------------------------------------
    # HEIKIN ASHI
    # --------------------------------------------------------

    ha = heikin_ashi(data)

    if not ha.empty:

        for column in ha.columns:

            data[column] = ha[column]

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    lookback = int(
        settings["sr_lookback"]
    )

    data["support"] = (
        data["low"]
        .rolling(lookback)
        .min()
    )

    data["resistance"] = (
        data["high"]
        .rolling(lookback)
        .max()
    )

    # --------------------------------------------------------
    # PIVOT
    # --------------------------------------------------------

    pivot_period = int(
        settings["pivot"]
    )

    data["pivot_high"] = (
        data["high"]
        == data["high"]
        .rolling(
            pivot_period * 2 + 1,
            center=True
        )
        .max()
    )

    data["pivot_low"] = (
        data["low"]
        == data["low"]
        .rolling(
            pivot_period * 2 + 1,
            center=True
        )
        .min()
    )

    return data


# ============================================================
# WAVE ANALYSIS
# ============================================================

def analyze_wave(
    df: pd.DataFrame,
    settings: Dict[str, Any]
) -> Dict[str, Any]:

    if df is None or len(df) < 5:
        return {
            "direction": "WAIT",
            "score": 0,
            "confirmation": 0,
        }

    data = prepare_dataframe(
        df,
        settings
    )

    if data.empty:
        return {
            "direction": "WAIT",
            "score": 0,
            "confirmation": 0,
        }

    last = data.iloc[-1]

    close = safe_float(
        last["close"]
    )

    ema_fast = safe_float(
        last["ema_9"]
    )

    ema_medium = safe_float(
        last["ema_20"]
    )

    ema_slow = safe_float(
        last["ema_50"]
    )

    rsi = safe_float(
        last["rsi"],
        50
    )

    macd = safe_float(
        last["macd"]
    )

    macd_signal = safe_float(
        last["macd_signal"]
    )

    macd_hist = safe_float(
        last["macd_hist"]
    )

    stoch_k = safe_float(
        last["stoch_k"],
        50
    )

    stoch_d = safe_float(
        last["stoch_d"],
        50
    )

    volume = safe_float(
        last["volume"],
        0
    )

    volume_sma = safe_float(
        last["volume_sma"],
        0
    )

    # --------------------------------------------------------
    # BUY / SELL CONFIRMATIONS
    # --------------------------------------------------------

    buy = 0
    sell = 0

    # EMA structure
    if (
        close > ema_fast
        and ema_fast > ema_medium
        and ema_medium > ema_slow
    ):
        buy += 1

    if (
        close < ema_fast
        and ema_fast < ema_medium
        and ema_medium < ema_slow
    ):
        sell += 1

    # Price vs EMA
    if close > ema_medium:
        buy += 1

    if close < ema_medium:
        sell += 1

    # RSI
    if rsi >= 50:
        buy += 1

    if rsi < 50:
        sell += 1

    # MACD
    if (
        macd > macd_signal
        and macd_hist >= 0
    ):
        buy += 1

    if (
        macd < macd_signal
        and macd_hist <= 0
    ):
        sell += 1

    # Stochastic
    if stoch_k > stoch_d:
        buy += 1

    if stoch_k < stoch_d:
        sell += 1

    # Volume
    if (
        volume_sma > 0
        and volume >= volume_sma
    ):

        if close > ema_medium:
            buy += 1

        elif close < ema_medium:
            sell += 1

    # Heikin Ashi
    ha_bullish = bool(
        last.get(
            "ha_bullish",
            False
        )
    )

    ha_bearish = bool(
        last.get(
            "ha_bearish",
            False
        )
    )

    if settings.get(
        "wave_heikin_ashi",
        True
    ):

        if ha_bullish:
            buy += 1

        if ha_bearish:
            sell += 1

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    if buy > sell:
        direction = "BUY"

    elif sell > buy:
        direction = "SELL"

    else:
        direction = "WAIT"

    return {
        "direction": direction,
        "buy_confirmation": buy,
        "sell_confirmation": sell,
        "confirmation": max(
            buy,
            sell
        ),

        "ema_fast": ema_fast,
        "ema_medium": ema_medium,
        "ema_slow": ema_slow,

        "rsi": rsi,

        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,

        "stoch_k": stoch_k,
        "stoch_d": stoch_d,

        "volume": volume,
        "volume_sma": volume_sma,

        "ha_bullish": ha_bullish,
        "ha_bearish": ha_bearish,

        "score_buy": buy,
        "score_sell": sell,
    }


# ============================================================
# TIDE ANALYSIS
# ============================================================

def analyze_tide(
    df: pd.DataFrame,
    settings: Dict[str, Any]
) -> Dict[str, Any]:

    if df is None or len(df) < 5:
        return {
            "direction": "WAIT",
            "confirmation": 0,
        }

    data = prepare_dataframe(
        df,
        settings
    )

    if data.empty:
        return {
            "direction": "WAIT",
            "confirmation": 0,
        }

    last = data.iloc[-1]

    close = safe_float(
        last["close"]
    )

    ema_fast = safe_float(
        last["ema_9"]
    )

    ema_medium = safe_float(
        last["ema_20"]
    )

    ema_slow = safe_float(
        last["ema_50"]
    )

    buy = 0
    sell = 0

    # 3 EMA structure
    if (
        close > ema_fast
        and ema_fast > ema_medium
        and ema_medium > ema_slow
    ):
        buy += 2

    if (
        close < ema_fast
        and ema_fast < ema_medium
        and ema_medium < ema_slow
    ):
        sell += 2

    # Price position
    if close > ema_medium:
        buy += 1

    if close < ema_medium:
        sell += 1

    # Heikin Ashi
    ha_bullish = bool(
        last.get(
            "ha_bullish",
            False
        )
    )

    ha_bearish = bool(
        last.get(
            "ha_bearish",
            False
        )
    )

    if settings.get(
        "tide_heikin_ashi",
        True
    ):

        if ha_bullish:
            buy += 1

        if ha_bearish:
            sell += 1

    if buy > sell:
        direction = "BUY"

    elif sell > buy:
        direction = "SELL"

    else:
        direction = "WAIT"

    return {
        "direction": direction,

        "buy_confirmation": buy,
        "sell_confirmation": sell,

        "confirmation": max(
            buy,
            sell
        ),

        "ema_fast": ema_fast,
        "ema_medium": ema_medium,
        "ema_slow": ema_slow,

        "ha_bullish": ha_bullish,
        "ha_bearish": ha_bearish,

        "score_buy": buy,
        "score_sell": sell,
    }


# ============================================================
# FILTER ANALYSIS
# ============================================================

def analyze_filter(
    df: pd.DataFrame,
    settings: Dict[str, Any]
) -> Dict[str, Any]:

    if df is None or df.empty:
        return {
            "direction": "WAIT"
        }

    data = df.copy()

    data.columns = [
        str(column).lower()
        for column in data.columns
    ]

    if "close" not in data.columns:
        return {
            "direction": "WAIT"
        }

    data["close"] = pd.to_numeric(
        data["close"],
        errors="coerce"
    )

    data = data.dropna(
        subset=["close"]
    )

    if data.empty:
        return {
            "direction": "WAIT"
        }

    fast = calculate_ema(
        data["close"],
        settings["filter_ema_fast"]
    )

    slow = calculate_ema(
        data["close"],
        settings["filter_ema_slow"]
    )

    close = safe_float(
        data["close"].iloc[-1]
    )

    fast_value = safe_float(
        fast.iloc[-1]
    )

    slow_value = safe_float(
        slow.iloc[-1]
    )

    if (
        close > fast_value
        and fast_value > slow_value
    ):

        direction = "BUY"

    elif (
        close < fast_value
        and fast_value < slow_value
    ):

        direction = "SELL"

    else:

        direction = "WAIT"

    return {
        "direction": direction,
        "ema_fast": fast_value,
        "ema_slow": slow_value,
    }


# ============================================================
# SCORE CALCULATION
# ============================================================

def calculate_score(
    wave: Dict[str, Any],
    tide: Dict[str, Any],
    filter_data: Dict[str, Any],
    settings: Dict[str, Any]
):

    buy_score = 50
    sell_score = 50

    # --------------------------------------------------------
    # WAVE
    # --------------------------------------------------------

    if wave["direction"] == "BUY":
        buy_score += 15

    elif wave["direction"] == "SELL":
        sell_score -= 15

    if wave["direction"] == "SELL":
        sell_score += 15

    elif wave["direction"] == "BUY":
        buy_score += 0

    # --------------------------------------------------------
    # TIDE
    # --------------------------------------------------------

    if tide["direction"] == "BUY":
        buy_score += 15

    elif tide["direction"] == "SELL":
        sell_score += 15

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    if filter_data["direction"] == "BUY":
        buy_score += 10

    elif filter_data["direction"] == "SELL":
        sell_score += 10

    # --------------------------------------------------------
    # CLAMP
    # --------------------------------------------------------

    buy_score = int(
        clamp(
            buy_score,
            0,
            100
        )
    )

    sell_score = int(
        clamp(
            sell_score,
            0,
            100
        )
    )

    return (
        buy_score,
        sell_score
    )


# ============================================================
# FINAL SIGNAL
# ============================================================

def final_signal(
    wave: Dict[str, Any],
    tide: Dict[str, Any],
    filter_data: Dict[str, Any],
    settings: Dict[str, Any],
    buy_score: int,
    sell_score: int
):

    min_confirmation = int(
        settings["min_confirmation"]
    )

    buy_confirmations = (
        wave.get(
            "buy_confirmation",
            0
        )
        +
        tide.get(
            "buy_confirmation",
            0
        )
    )

    sell_confirmations = (
        wave.get(
            "sell_confirmation",
            0
        )
        +
        tide.get(
            "sell_confirmation",
            0
        )
    )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if (
        buy_score >=
        int(settings["buy_score"])

        and
        wave["direction"] == "BUY"

        and
        tide["direction"] == "BUY"

        and
        filter_data["direction"] == "BUY"

        and
        buy_confirmations >=
        min_confirmation
    ):

        return "BUY"

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    if (
        sell_score >=
        int(
            100 -
            settings["sell_score"]
        )

        and
        wave["direction"] == "SELL"

        and
        tide["direction"] == "SELL"

        and
        filter_data["direction"] == "SELL"

        and
        sell_confirmations >=
        min_confirmation
    ):

        return "SELL"

    return "WAIT"


# ============================================================
# RISK / REWARD
# ============================================================

def calculate_levels(
    price: float,
    signal: str,
    support: float,
    resistance: float,
    settings: Dict[str, Any]
):

    price = safe_float(
        price,
        np.nan
    )

    if not np.isfinite(price):
        return {
            "sl": np.nan,
            "target": np.nan,
            "rr": settings["risk_reward"]
        }

    rr = float(
        settings["risk_reward"]
    )

    if signal == "BUY":

        sl = support

        if (
            not np.isfinite(sl)
            or sl >= price
        ):

            sl = price * 0.99

        risk = price - sl

        target = (
            price
            + risk * rr
        )

        return {
            "sl": sl,
            "target": target,
            "rr": rr
        }

    if signal == "SELL":

        sl = resistance

        if (
            not np.isfinite(sl)
            or sl <= price
        ):

            sl = price * 1.01

        risk = sl - price

        target = (
            price
            - risk * rr
        )

        return {
            "sl": sl,
            "target": target,
            "rr": rr
        }

    return {
        "sl": np.nan,
        "target": np.nan,
        "rr": rr
    }


# ============================================================
# SCANNER ENGINE
# ============================================================

class ScannerEngine:

    def __init__(
        self,
        settings: Optional[
            Dict[str, Any]
        ] = None
    ):

        self.settings = (
            DEFAULT_SETTINGS.copy()
        )

        if settings:

            self.update_settings(
                settings
            )


    # --------------------------------------------------------
    # UPDATE SETTINGS
    # --------------------------------------------------------

    def update_settings(
        self,
        settings: Dict[str, Any]
    ):

        for key, value in settings.items():

            if key not in self.settings:
                continue

            if value is None:
                continue

            try:

                if key in [
                    "wave_heikin_ashi",
                    "tide_heikin_ashi"
                ]:

                    if isinstance(
                        value,
                        str
                    ):

                        value = (
                            value.lower()
                            in [
                                "true",
                                "1",
                                "yes",
                                "on"
                            ]
                        )

                    else:

                        value = bool(value)

                elif key in [
                    "wave_timeframe",
                    "tide_timeframe"
                ]:

                    value = str(value)

                elif key in [
                    "risk_reward"
                ]:

                    value = float(value)

                else:

                    value = int(
                        float(value)
                    )

                self.settings[key] = value

            except Exception:

                continue


    # --------------------------------------------------------
    # GET SETTINGS
    # --------------------------------------------------------

    def get_settings(self):

        return self.settings.copy()


    # --------------------------------------------------------
    # MAIN ANALYSIS
    # --------------------------------------------------------

    def analyze_symbol(
        self,
        symbol: str,
        entry_df: Optional[pd.DataFrame] = None,
        wave_df: Optional[pd.DataFrame] = None,
        tide_df: Optional[pd.DataFrame] = None,
        **kwargs
    ):

        # ----------------------------------------------------
        # Compatibility:
        # If old main.py sends only wave/tide data,
        # use those datasets.
        # ----------------------------------------------------

        if wave_df is None:
            wave_df = entry_df

        if tide_df is None:
            tide_df = wave_df


        # ----------------------------------------------------
        # MINIMUM DATA
        # ----------------------------------------------------

        if (
            wave_df is None
            or len(wave_df)
            < self.settings["minimum_candles"]
        ):

            return self.wait_result(
                symbol,
                "Not enough Wave candles"
            )


        if (
            tide_df is None
            or len(tide_df)
            < self.settings["minimum_candles"]
        ):

            return self.wait_result(
                symbol,
                "Not enough Tide candles"
            )


        # ----------------------------------------------------
        # ANALYZE WAVE
        # ----------------------------------------------------

        wave = analyze_wave(
            wave_df,
            self.settings
        )


        # ----------------------------------------------------
        # ANALYZE TIDE
        # ----------------------------------------------------

        tide = analyze_tide(
            tide_df,
            self.settings
        )


        # ----------------------------------------------------
        # FILTER
        #
        # Use Wave data for the 20/50 filter.
        # ----------------------------------------------------

        filter_data = analyze_filter(
            wave_df,
            self.settings
        )


        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------

        buy_score, sell_score = (
            calculate_score(
                wave,
                tide,
                filter_data,
                self.settings
            )
        )


        # ----------------------------------------------------
        # FINAL SIGNAL
        # ----------------------------------------------------

        signal = final_signal(
            wave,
            tide,
            filter_data,
            self.settings,
            buy_score,
            sell_score
        )


        # ----------------------------------------------------
        # CURRENT PRICE
        # ----------------------------------------------------

        prepared_wave = prepare_dataframe(
            wave_df,
            self.settings
        )

        if prepared_wave.empty:

            return self.wait_result(
                symbol,
                "Invalid Wave data"
            )

        last = prepared_wave.iloc[-1]

        price = safe_float(
            last["close"]
        )

        support = safe_float(
            last.get("support")
        )

        resistance = safe_float(
            last.get("resistance")
        )


        # ----------------------------------------------------
        # LEVELS
        # ----------------------------------------------------

        levels = calculate_levels(
            price,
            signal,
            support,
            resistance,
            self.settings
        )


        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        return {

            "symbol": symbol,

            "price": price,
            "ltp": price,

            "signal": signal,

            "score": (
                buy_score
                if signal == "BUY"
                else
                100 - sell_score
                if signal == "SELL"
                else
                max(
                    buy_score,
                    100 - sell_score
                )
            ),

            "buy_score": buy_score,
            "sell_score": sell_score,

            "wave": wave["direction"],
            "wave_signal": wave["direction"],

            "tide": tide["direction"],
            "tide_signal": tide["direction"],

            "ema": filter_data["direction"],
            "ema_signal": filter_data["direction"],

            "filter": filter_data["direction"],

            "rsi": wave.get(
                "rsi",
                np.nan
            ),

            "macd": wave.get(
                "macd",
                np.nan
            ),

            "macd_signal": wave.get(
                "macd_signal",
                np.nan
            ),

            "macd_hist": wave.get(
                "macd_hist",
                np.nan
            ),

            "stoch_k": wave.get(
                "stoch_k",
                np.nan
            ),

            "stoch_d": wave.get(
                "stoch_d",
                np.nan
            ),

            "volume": wave.get(
                "volume",
                np.nan
            ),

            "volume_sma": wave.get(
                "volume_sma",
                np.nan
            ),

            "support": support,
            "resistance": resistance,

            "sl": levels["sl"],
            "stop_loss": levels["sl"],

            "target": levels["target"],
            "take_profit": levels["target"],

            "rr": levels["rr"],

            "wave_ema_fast":
                wave.get(
                    "ema_fast"
                ),

            "wave_ema_medium":
                wave.get(
                    "ema_medium"
                ),

            "wave_ema_slow":
                wave.get(
                    "ema_slow"
                ),

            "tide_ema_fast":
                tide.get(
                    "ema_fast"
                ),

            "tide_ema_medium":
                tide.get(
                    "ema_medium"
                ),

            "tide_ema_slow":
                tide.get(
                    "ema_slow"
                ),

            "filter_ema_fast":
                filter_data.get(
                    "ema_fast"
                ),

            "filter_ema_slow":
                filter_data.get(
                    "ema_slow"
                ),

            "wave_heikin_ashi":
                (
                    "BULLISH"
                    if wave.get(
                        "ha_bullish"
                    )
                    else
                    "BEARISH"
                    if wave.get(
                        "ha_bearish"
                    )
                    else
                    "NEUTRAL"
                ),

            "tide_heikin_ashi":
                (
                    "BULLISH"
                    if tide.get(
                        "ha_bullish"
                    )
                    else
                    "BEARISH"
                    if tide.get(
                        "ha_bearish"
                    )
                    else
                    "NEUTRAL"
                ),

            "confirmation":
                max(
                    wave.get(
                        "confirmation",
                        0
                    ),
                    tide.get(
                        "confirmation",
                        0
                    )
                ),

            "reason":
                build_reason(
                    signal,
                    wave,
                    tide,
                    filter_data
                )
        }


    # --------------------------------------------------------
    # COMPATIBILITY ALIAS
    # --------------------------------------------------------

    def scan_symbol(
        self,
        symbol: str,
        *args,
        **kwargs
    ):

        return self.analyze_symbol(
            symbol,
            *args,
            **kwargs
        )


    # --------------------------------------------------------
    # COMPATIBILITY ALIAS
    # --------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        *args,
        **kwargs
    ):

        return self.analyze_symbol(
            symbol,
            *args,
            **kwargs
        )


    # --------------------------------------------------------
    # WAIT RESULT
    # --------------------------------------------------------

    def wait_result(
        self,
        symbol: str,
        reason: str = ""
    ):

        return {

            "symbol": symbol,

            "price": np.nan,
            "ltp": np.nan,

            "signal": "WAIT",

            "score": 50,

            "buy_score": 50,
            "sell_score": 50,

            "wave": "WAIT",
            "wave_signal": "WAIT",

            "tide": "WAIT",
            "tide_signal": "WAIT",

            "ema": "WAIT",
            "ema_signal": "WAIT",

            "filter": "WAIT",

            "rsi": np.nan,

            "macd": np.nan,
            "macd_signal": np.nan,
            "macd_hist": np.nan,

            "stoch_k": np.nan,
            "stoch_d": np.nan,

            "volume": np.nan,
            "volume_sma": np.nan,

            "support": np.nan,
            "resistance": np.nan,

            "sl": np.nan,
            "stop_loss": np.nan,

            "target": np.nan,
            "take_profit": np.nan,

            "rr":
                self.settings[
                    "risk_reward"
                ],

            "confirmation": 0,

            "reason": reason
        }


# ============================================================
# REASON
# ============================================================

def build_reason(
    signal,
    wave,
    tide,
    filter_data
):

    if signal == "BUY":

        return (
            "Wave bullish + Tide bullish + "
            "20/50 filter bullish + "
            "indicator confirmation"
        )

    if signal == "SELL":

        return (
            "Wave bearish + Tide bearish + "
            "20/50 filter bearish + "
            "indicator confirmation"
        )

    return (
        "Wave/Tide/Filter confirmation "
        "not aligned"
    )


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    "DEFAULT_SETTINGS",
    "ScannerEngine",
    "prepare_dataframe",
    "heikin_ashi",
]
