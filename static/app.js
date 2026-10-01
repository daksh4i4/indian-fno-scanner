/* ============================================================
   INDIAN F&O SCANNER
   PROFESSIONAL FRONTEND CONTROLLER

   Wave  : 15m
   Tide  : 1h
   Wave EMA   : 9 / 20 / 50
   Tide EMA   : 9 / 20 / 50
   Filter EMA : 20 / 50
   Heikin Ashi confirmation
   ============================================================ */

"use strict";


/* ============================================================
   CONFIGURATION
============================================================ */

const API = {
    STATUS: "/api/status",
    SCANNER: "/api/scanner",
    SETTINGS: "/api/settings",
    RESET: "/api/reset"
};


const REFRESH_INTERVAL = 5000;
const STATUS_INTERVAL = 5000;


/* ============================================================
   DEFAULT SETTINGS
============================================================ */

const DEFAULT_SETTINGS = {

    wave_timeframe: "15m",
    tide_timeframe: "1h",

    wave_ema_fast: 9,
    wave_ema_medium: 20,
    wave_ema_slow: 50,

    tide_ema_fast: 9,
    tide_ema_medium: 20,
    tide_ema_slow: 50,

    filter_ema_fast: 20,
    filter_ema_slow: 50,

    wave_heikin_ashi: true,
    tide_heikin_ashi: true,

    rsi_period: 14,

    macd_fast: 12,
    macd_slow: 26,
    macd_signal: 9,

    stochastic_period: 14,
    stochastic_smooth: 3,

    volume_sma: 20,

    sr_lookback: 160,
    pivot: 3,

    min_confirmation: 7,

    risk_reward: 2,

    buy_score: 70,
    sell_score: 30,

    minimum_candles: 60
};


/* ============================================================
   APPLICATION STATE
============================================================ */

const state = {

    settings: {
        ...DEFAULT_SETTINGS
    },

    scannerRows: [],

    filteredRows: [],

    connected: false,

    scannerLoaded: false,

    lastStatus: null,

    lastScannerUpdate: null,

    loadingScanner: false,

    loadingSettings: false,

    search: "",

    signalFilter: "ALL"
};


/* ============================================================
   DOM HELPERS
============================================================ */

function $(id) {

    return document.getElementById(id);

}


function setText(id, value) {

    const element = $(id);

    if (!element) {
        return;
    }

    element.textContent =
        value === null ||
        value === undefined
            ? "—"
            : String(value);
}


function showElement(id) {

    const element = $(id);

    if (element) {
        element.classList.remove("hidden");
    }

}


function hideElement(id) {

    const element = $(id);

    if (element) {
        element.classList.add("hidden");
    }

}


/* ============================================================
   SAFE NUMBER
============================================================ */

function numberValue(value, fallback = null) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return fallback;
    }

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return fallback;
    }

    return n;
}


/* ============================================================
   NUMBER FORMAT
============================================================ */

function formatNumber(value, decimals = 2) {

    const n = numberValue(value);

    if (n === null) {
        return "—";
    }

    return n.toLocaleString(
        "en-IN",
        {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }
    );
}


function formatInteger(value) {

    const n = numberValue(value);

    if (n === null) {
        return "0";
    }

    return Math.round(n).toLocaleString("en-IN");
}


function formatPercent(value) {

    const n = numberValue(value);

    if (n === null) {
        return "—";
    }

    return `${n.toFixed(2)}%`;
}


/* ============================================================
   TIMEFRAME LABEL
============================================================ */

function timeframeLabel(value) {

    const map = {

        "1m": "1 Minute",
        "2m": "2 Minutes",
        "3m": "3 Minutes",
        "5m": "5 Minutes",
        "10m": "10 Minutes",
        "15m": "15 Minutes",
        "30m": "30 Minutes",
        "1h": "1 Hour",
        "4h": "4 Hours",
        "1d": "1 Day",
        "1w": "1 Week"

    };

    return map[value] || value || "—";
}


/* ============================================================
   SIGNAL NORMALIZATION
============================================================ */

function normalizeSignal(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "WAIT";
    }

    const signal =
        String(value)
            .trim()
            .toUpperCase();

    if (
        signal.includes("BUY") ||
        signal.includes("LONG")
    ) {
        return "BUY";
    }

    if (
        signal.includes("SELL") ||
        signal.includes("SHORT")
    ) {
        return "SELL";
    }

    return "WAIT";
}


/* ============================================================
   DIRECTION NORMALIZATION
============================================================ */

function normalizeDirection(value) {

    const signal =
        normalizeSignal(value);

    if (signal === "BUY") {
        return "BUY";
    }

    if (signal === "SELL") {
        return "SELL";
    }

    return "WAIT";
}


/* ============================================================
   HTML ESCAPE
============================================================ */

function escapeHTML(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


/* ============================================================
   API REQUEST
============================================================ */

async function apiRequest(
    url,
    options = {}
) {

    const response =
        await fetch(
            url,
            {
                cache: "no-store",
                ...options,
                headers: {
                    "Accept": "application/json",
                    ...(options.headers || {})
                }
            }
        );

    let data = null;

    try {

        data = await response.json();

    } catch (error) {

        data = null;

    }


    if (!response.ok) {

        const message =
            data?.message ||
            data?.detail ||
            `HTTP ${response.status}`;

        throw new Error(message);

    }

    return data;

}


/* ============================================================
   TOAST
============================================================ */

let toastTimer = null;


function showToast(
    message,
    type = "info"
) {

    const toast = $("toast");
    const text = $("toastMessage");

    if (!toast || !text) {
        return;
    }

    text.textContent = message;

    toast.classList.remove(
        "toast-success",
        "toast-error",
        "toast-info",
        "show"
    );

    if (type === "success") {

        toast.classList.add(
            "toast-success"
        );

    } else if (type === "error") {

        toast.classList.add(
            "toast-error"
        );

    } else {

        toast.classList.add(
            "toast-info"
        );

    }

    requestAnimationFrame(() => {

        toast.classList.add("show");

    });


    clearTimeout(toastTimer);

    toastTimer =
        setTimeout(
            () => {

                toast.classList.remove(
                    "show"
                );

            },
            3000
        );

}


/* ============================================================
   CONNECTION STATUS
============================================================ */

function updateConnectionStatus(
    connected,
    status = null
) {

    const pill =
        $("connectionStatus");

    const text =
        $("connectionText");

    if (!pill || !text) {
        return;
    }


    pill.classList.remove(
        "status-connected",
        "status-loading",
        "status-error"
    );


    if (connected) {

        pill.classList.add(
            "status-connected"
        );

        text.textContent =
            "Connected";

        state.connected = true;

    } else {

        const marketStatus =
            String(
                status?.market_status ||
                ""
            ).toUpperCase();


        if (
            marketStatus === "ERROR"
        ) {

            pill.classList.add(
                "status-error"
            );

            text.textContent =
                "Connection Error";

        } else {

            pill.classList.add(
                "status-loading"
            );

            text.textContent =
                "Connecting...";

        }

        state.connected = false;

    }

}


/* ============================================================
   MARKET STATUS
============================================================ */

function updateMarketStatus(status) {

    const element =
        $("marketStatus");

    if (!element) {
        return;
    }


    const market =
        String(
            status?.market_status ||
            "UNKNOWN"
        ).toUpperCase();


    element.classList.remove(
        "market-open",
        "market-closed",
        "market-error"
    );


    if (
        market === "OPEN" ||
        market === "LIVE"
    ) {

        element.classList.add(
            "market-open"
        );

        element.textContent =
            "● Market Live";

    } else if (
        market === "ERROR"
    ) {

        element.classList.add(
            "market-error"
        );

        element.textContent =
            "● Data Error";

    } else {

        element.classList.add(
            "market-closed"
        );

        element.textContent =
            "● Market Data";

    }

}


/* ============================================================
   STATUS
============================================================ */

async function loadStatus() {

    try {

        const data =
            await apiRequest(
                API.STATUS
            );


        state.lastStatus =
            data;


        const authenticated =
            Boolean(
                data.authenticated
            );


        updateConnectionStatus(
            authenticated,
            data
        );


        updateMarketStatus(
            data
        );


        setText(
            "fnoStocks",
            formatInteger(
                data.fno_stock_count ??
                data.fno_stocks ??
                0
            )
        );


        const historyLoaded =
            numberValue(
                data.history_loaded,
                0
            );


        const historyFailed =
            numberValue(
                data.history_failed,
                0
            );


        const total =
            numberValue(
                data.fno_stock_count ??
                data.fno_stocks,
                0
            );


        let progress = 0;


        if (total > 0) {

            progress =
                Math.min(
                    100,
                    (
                        historyLoaded /
                        total
                    ) * 100
                );

        }


        const progressText =
            total > 0
                ? `${formatInteger(historyLoaded)} / ${formatInteger(total)}`
                : "Loading...";


        setText(
            "historyProgress",
            progressText
        );


        const progressBar =
            $("historyProgressBar");


        if (progressBar) {

            progressBar.style.width =
                `${progress}%`;

        }


        if (
            historyFailed > 0
        ) {

            const message =
                `Historical data: ${formatInteger(historyLoaded)} loaded, ${formatInteger(historyFailed)} failed.`;

            setError(
                message
            );

        } else if (
            data.last_error
        ) {

            setError(
                String(
                    data.last_error
                )
            );

        } else {

            clearError();

        }


        const lastUpdate =
            data.last_ltp_update ||
            data.last_history_update;


        if (lastUpdate) {

            setText(
                "lastUpdate",
                `Last update: ${formatDateTime(lastUpdate)}`
            );

        }


        updateStrategyBadges();


    } catch (error) {

        updateConnectionStatus(
            false,
            {
                market_status: "ERROR"
            }
        );


        setError(
            error.message ||
            "Unable to connect to scanner."
        );

    }

}


/* ============================================================
   ERROR
============================================================ */

function setError(message) {

    const element =
        $("errorMessage");

    if (!element) {
        return;
    }


    if (
        !message ||
        message === "null" ||
        message === "undefined"
    ) {

        clearError();

        return;

    }


    element.textContent =
        String(message);

    element.classList.remove(
        "hidden"
    );

}


function clearError() {

    const element =
        $("errorMessage");

    if (!element) {
        return;
    }

    element.textContent = "";

    element.classList.add(
        "hidden"
    );

}


/* ============================================================
   DATE / TIME
============================================================ */

function formatDateTime(value) {

    if (!value) {
        return "—";
    }

    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {

        return String(value);

    }


    return date.toLocaleString(
        "en-IN",
        {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        }
    );

}


/* ============================================================
   SETTINGS INPUT HELPERS
============================================================ */

function getInputValue(
    id,
    fallback
) {

    const element =
        $(id);

    if (!element) {
        return fallback;
    }

    return element.value;

}


function getNumberInput(
    id,
    fallback
) {

    const value =
        getInputValue(
            id,
            fallback
        );


    const number =
        Number(value);


    if (
        !Number.isFinite(
            number
        )
    ) {

        return fallback;

    }


    return number;

}


function getCheckbox(
    id,
    fallback = false
) {

    const element =
        $(id);

    if (!element) {
        return fallback;
    }

    return Boolean(
        element.checked
    );

}


/* ============================================================
   READ SETTINGS FROM UI
============================================================ */

function readSettingsFromUI() {

    return {

        wave_timeframe:
            getInputValue(
                "wave_timeframe",
                DEFAULT_SETTINGS.wave_timeframe
            ),

        tide_timeframe:
            getInputValue(
                "tide_timeframe",
                DEFAULT_SETTINGS.tide_timeframe
            ),


        wave_ema_fast:
            getNumberInput(
                "wave_ema_fast",
                9
            ),

        wave_ema_medium:
            getNumberInput(
                "wave_ema_medium",
                20
            ),

        wave_ema_slow:
            getNumberInput(
                "wave_ema_slow",
                50
            ),


        tide_ema_fast:
            getNumberInput(
                "tide_ema_fast",
                9
            ),

        tide_ema_medium:
            getNumberInput(
                "tide_ema_medium",
                20
            ),

        tide_ema_slow:
            getNumberInput(
                "tide_ema_slow",
                50
            ),


        filter_ema_fast:
            getNumberInput(
                "filter_ema_fast",
                20
            ),

        filter_ema_slow:
            getNumberInput(
                "filter_ema_slow",
                50
            ),


        wave_heikin_ashi:
            getCheckbox(
                "wave_heikin_ashi",
                true
            ),

        tide_heikin_ashi:
            getCheckbox(
                "tide_heikin_ashi",
                true
            ),


        rsi_period:
            getNumberInput(
                "rsi_period",
                14
            ),


        macd_fast:
            getNumberInput(
                "macd_fast",
                12
            ),

        macd_slow:
            getNumberInput(
                "macd_slow",
                26
            ),

        macd_signal:
            getNumberInput(
                "macd_signal",
                9
            ),


        stochastic_period:
            getNumberInput(
                "stochastic_period",
                14
            ),

        stochastic_smooth:
            getNumberInput(
                "stochastic_smooth",
                3
            ),


        volume_sma:
            getNumberInput(
                "volume_sma",
                20
            ),


        sr_lookback:
            getNumberInput(
                "sr_lookback",
                160
            ),

        pivot:
            getNumberInput(
                "pivot",
                3
            ),


        min_confirmation:
            getNumberInput(
                "min_confirmation",
                7
            ),

        risk_reward:
            getNumberInput(
                "risk_reward",
                2
            ),

        buy_score:
            getNumberInput(
                "buy_score",
                70
            ),

        sell_score:
            getNumberInput(
                "sell_score",
                30
            )

    };

}


/* ============================================================
   PUT SETTINGS INTO UI
============================================================ */

function applySettingsToUI(
    settings
) {

    const merged = {

        ...DEFAULT_SETTINGS,

        ...(settings || {})

    };


    state.settings =
        merged;


    const selectIds = [

        "wave_timeframe",
        "tide_timeframe"

    ];


    selectIds.forEach(
        id => {

            const element =
                $(id);

            if (!element) {
                return;
            }

            if (
                merged[id] !==
                undefined
            ) {

                element.value =
                    merged[id];

            }

        }
    );


    const numberIds = [

        "wave_ema_fast",
        "wave_ema_medium",
        "wave_ema_slow",

        "tide_ema_fast",
        "tide_ema_medium",
        "tide_ema_slow",

        "filter_ema_fast",
        "filter_ema_slow",

        "rsi_period",

        "macd_fast",
        "macd_slow",
        "macd_signal",

        "stochastic_period",
        "stochastic_smooth",

        "volume_sma",

        "sr_lookback",
        "pivot",

        "min_confirmation",
        "risk_reward",

        "buy_score",
        "sell_score"

    ];


    numberIds.forEach(
        id => {

            const element =
                $(id);

            if (!element) {
                return;
            }

            if (
                merged[id] !==
                undefined
            ) {

                element.value =
                    merged[id];

            }

        }
    );


    const checkboxIds = [

        "wave_heikin_ashi",
        "tide_heikin_ashi"

    ];


    checkboxIds.forEach(
        id => {

            const element =
                $(id);

            if (!element) {
                return;
            }

            element.checked =
                Boolean(
                    merged[id]
                );

        }
    );


    updateStrategyBadges();

}


/* ============================================================
   LOAD SETTINGS
============================================================ */

async function loadSettings() {

    try {

        const data =
            await apiRequest(
                API.SETTINGS
            );


        let settings =
            data;


        if (
            data &&
            data.settings
        ) {

            settings =
                data.settings;

        }


        applySettingsToUI(
            settings
        );


    } catch (error) {

        console.warn(
            "Settings load failed:",
            error
        );


        applySettingsToUI(
            DEFAULT_SETTINGS
        );

    }

}


/* ============================================================
   APPLY SETTINGS
============================================================ */

async function applySettings() {

    if (
        state.loadingSettings
    ) {

        return;

    }


    state.loadingSettings =
        true;


    const button =
        $("applySettings");


    const originalText =
        button
            ? button.textContent
            : "";


    if (button) {

        button.disabled =
            true;

        button.textContent =
            "Applying...";

    }


    try {

        const settings =
            readSettingsFromUI();


        validateSettings(
            settings
        );


        const data =
            await apiRequest(
                API.SETTINGS,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            settings
                        )
                }
            );


        const returnedSettings =
            data?.settings ||
            settings;


        applySettingsToUI(
            returnedSettings
        );


        showToast(
            "Strategy settings applied successfully.",
            "success"
        );


        await loadStatus();

        await loadScanner();


    } catch (error) {

        showToast(
            error.message ||
            "Unable to apply settings.",
            "error"
        );

    } finally {

        state.loadingSettings =
            false;


        if (button) {

            button.disabled =
                false;

            button.textContent =
                originalText ||
                "✓ Apply Settings";

        }

    }

}


/* ============================================================
   SETTINGS VALIDATION
============================================================ */

function validateSettings(
    settings
) {

    const positiveFields = [

        "wave_ema_fast",
        "wave_ema_medium",
        "wave_ema_slow",

        "tide_ema_fast",
        "tide_ema_medium",
        "tide_ema_slow",

        "filter_ema_fast",
        "filter_ema_slow",

        "rsi_period",

        "macd_fast",
        "macd_slow",
        "macd_signal",

        "stochastic_period",
        "stochastic_smooth",

        "volume_sma",

        "sr_lookback",
        "pivot",

        "min_confirmation",

        "risk_reward"

    ];


    for (
        const field of positiveFields
    ) {

        const value =
            Number(
                settings[field]
            );


        if (
            !Number.isFinite(value) ||
            value <= 0
        ) {

            throw new Error(
                `${field} must be greater than 0.`
            );

        }

    }


    if (
        settings.buy_score < 1 ||
        settings.buy_score > 100
    ) {

        throw new Error(
            "BUY Score must be between 1 and 100."
        );

    }


    if (
        settings.sell_score < 1 ||
        settings.sell_score > 100
    ) {

        throw new Error(
            "SELL Score must be between 1 and 100."
        );

    }


    if (
        settings.risk_reward < 0.5
    ) {

        throw new Error(
            "Risk / Reward must be at least 0.5."
        );

    }

}


/* ============================================================
   RESET SETTINGS
============================================================ */

async function resetSettings() {

    applySettingsToUI(
        DEFAULT_SETTINGS
    );


    try {

        await apiRequest(
            API.SETTINGS,
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(
                        DEFAULT_SETTINGS
                    )
            }
        );


        showToast(
            "Settings reset to default.",
            "success"
        );


        await loadScanner();


    } catch (error) {

        showToast(
            error.message ||
            "Unable to reset settings.",
            "error"
        );

    }

}


/* ============================================================
   STRATEGY BADGES
============================================================ */

function updateStrategyBadges() {

    const settings =
        state.settings ||
        DEFAULT_SETTINGS;


    setText(
        "waveBadge",
        timeframeLabel(
            settings.wave_timeframe
        )
    );


    setText(
        "tideBadge",
        timeframeLabel(
            settings.tide_timeframe
        )
    );


    const badges =
        document.querySelectorAll(
            ".strategy-badge"
        );


    if (!badges.length) {
        return;
    }


    /*
       Keep the visible strategy bar synchronized
       with the actual settings.
    */

    const waveEma =
        document.querySelector(
            ".strategy-badge:nth-child(3) strong"
        );


    if (waveEma) {

        waveEma.textContent =
            `${settings.wave_ema_fast} / ${settings.wave_ema_medium} / ${settings.wave_ema_slow}`;

    }


    const tideEma =
        document.querySelector(
            ".strategy-badge:nth-child(4) strong"
        );


    if (tideEma) {

        tideEma.textContent =
            `${settings.tide_ema_fast} / ${settings.tide_ema_medium} / ${settings.tide_ema_slow}`;

    }


    const filter =
        document.querySelector(
            ".strategy-badge:nth-child(5) strong"
        );


    if (filter) {

        filter.textContent =
            `${settings.filter_ema_fast} / ${settings.filter_ema_slow}`;

    }


    const rr =
        document.querySelector(
            ".strategy-badge:nth-child(6) strong"
        );


    if (rr) {

        rr.textContent =
            `1 : ${settings.risk_reward}`;

    }

}


/* ============================================================
   LOAD SCANNER
============================================================ */

async function loadScanner() {

    if (
        state.loadingScanner
    ) {

        return;

    }


    state.loadingScanner =
        true;


    try {

        const data =
            await apiRequest(
                API.SCANNER
            );


        let rows = [];


        if (
            Array.isArray(data)
        ) {

            rows =
                data;

        } else if (
            Array.isArray(
                data?.results
            )
        ) {

            rows =
                data.results;

        } else if (
            Array.isArray(
                data?.scanner
            )
        ) {

            rows =
                data.scanner;

        } else if (
            Array.isArray(
                data?.data
            )
        ) {

            rows =
                data.data;

        }


        state.scannerRows =
            rows.map(
                normalizeRow
            );


        state.lastScannerUpdate =
            new Date();


        state.scannerLoaded =
            true;


        updateSummaryCards(
            state.scannerRows
        );


        filterAndRender();


        const lastUpdate =
            state.lastStatus?.last_ltp_update ||
            state.lastStatus?.last_history_update;


        if (lastUpdate) {

            setText(
                "lastUpdate",
                `Last update: ${formatDateTime(lastUpdate)}`
            );

        } else {

            setText(
                "lastUpdate",
                `Last update: ${formatDateTime(new Date())}`
            );

        }


    } catch (error) {

        console.warn(
            "Scanner load failed:",
            error
        );


        if (
            !state.scannerLoaded
        ) {

            renderEmptyState(
                "Waiting for scanner data..."
            );

        }

    } finally {

        state.loadingScanner =
            false;

    }

}


/* ============================================================
   NORMALIZE SCANNER ROW
============================================================ */

function normalizeRow(row) {

    if (
        !row ||
        typeof row !== "object"
    ) {

        return {

            symbol: "UNKNOWN",
            signal: "WAIT"

        };

    }


    const signal =
        normalizeSignal(
            row.signal ??
            row.action ??
            row.side ??
            row.direction
        );


    const wave =
        normalizeDirection(
            row.wave ??
            row.wave_signal ??
            row.wave_direction
        );


    const tide =
        normalizeDirection(
            row.tide ??
            row.tide_signal ??
            row.tide_direction
        );


    const filter =
        normalizeDirection(
            row.filter ??
            row.ema_signal ??
            row.filter_signal ??
            row.ema
        );


    return {

        ...row,

        symbol:
            row.symbol ??
            row.stock ??
            row.trading_symbol ??
            row.name ??
            "—",

        price:
            numberValue(
                row.price ??
                row.ltp ??
                row.last_price
            ),

        change:
            numberValue(
                row.change ??
                row.change_percent ??
                row.change_pct
            ),

        change_percent:
            numberValue(
                row.change_percent ??
                row.change_pct ??
                row.change
            ),

        wave,

        tide,

        filter,

        signal,

        score:
            numberValue(
                row.score ??
                row.total_score
            ),

        buy_score:
            numberValue(
                row.buy_score
            ),

        sell_score:
            numberValue(
                row.sell_score
            ),

        rsi:
            numberValue(
                row.rsi
            ),

        macd:
            numberValue(
                row.macd
            ),

        macd_signal:
            numberValue(
                row.macd_signal
            ),

        macd_hist:
            numberValue(
                row.macd_hist
            ),

        stoch_k:
            numberValue(
                row.stoch_k ??
                row.stochastic_k
            ),

        stoch_d:
            numberValue(
                row.stoch_d ??
                row.stochastic_d
            ),

        volume:
            numberValue(
                row.volume
            ),

        volume_sma:
            numberValue(
                row.volume_sma
            ),

        support:
            numberValue(
                row.support
            ),

        resistance:
            numberValue(
                row.resistance
            ),

        sl:
            numberValue(
                row.sl ??
                row.stop_loss
            ),

        target:
            numberValue(
                row.target ??
                row.take_profit
            ),

        rr:
            numberValue(
                row.rr ??
                row.risk_reward
            ),

        confirmation:
            numberValue(
                row.confirmation
            ),

        wave_ha:
            normalizeHA(
                row.wave_heikin_ashi ??
                row.wave_ha
            ),

        tide_ha:
            normalizeHA(
                row.tide_heikin_ashi ??
                row.tide_ha
            )

    };

}


/* ============================================================
   HEIKIN ASHI NORMALIZATION
============================================================ */

function normalizeHA(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return "NEUTRAL";

    }


    const text =
        String(value)
            .trim()
            .toUpperCase();


    if (
        text.includes("BULL")
    ) {

        return "BULLISH";

    }


    if (
        text.includes("BEAR")
    ) {

        return "BEARISH";

    }


    return "NEUTRAL";

}


/* ============================================================
   SUMMARY CARDS
============================================================ */

function updateSummaryCards(
    rows
) {

    let buy = 0;
    let sell = 0;
    let wait = 0;


    rows.forEach(
        row => {

            if (
                row.signal === "BUY"
            ) {

                buy++;

            } else if (
                row.signal === "SELL"
            ) {

                sell++;

            } else {

                wait++;

            }

        }
    );


    setText(
        "buyCount",
        formatInteger(buy)
    );


    setText(
        "sellCount",
        formatInteger(sell)
    );


    setText(
        "waitCount",
        formatInteger(wait)
    );


    if (
        rows.length > 0
    ) {

        setText(
            "fnoStocks",
            formatInteger(
                rows.length
            )
        );

    }

}


/* ============================================================
   FILTER
============================================================ */

function filterAndRender() {

    const search =
        state.search
            .trim()
            .toUpperCase();


    const signal =
        state.signalFilter;


    const rows =
        state.scannerRows.filter(
            row => {

                const symbol =
                    String(
                        row.symbol ||
                        ""
                    ).toUpperCase();


                const signalMatch =
                    signal === "ALL" ||
                    row.signal === signal;


                const searchMatch =
                    !search ||
                    symbol.includes(
                        search
                    );


                return (
                    signalMatch &&
                    searchMatch
                );

            }
        );


    state.filteredRows =
        rows;


    renderScannerTable(
        rows
    );

}


/* ============================================================
   RENDER TABLE
============================================================ */

function renderScannerTable(
    rows
) {

    const body =
        $("scannerBody");


    if (!body) {
        return;
    }


    if (
        !rows ||
        !rows.length
    ) {

        renderEmptyState(
            state.scannerLoaded
                ? "No matching stocks found."
                : "Loading scanner..."
        );

        return;

    }


    const fragment =
        document.createDocumentFragment();


    rows.forEach(
        (row, index) => {

            const tr =
                document.createElement(
                    "tr"
                );


            tr.innerHTML =
                buildRowHTML(
                    row,
                    index + 1
                );


            fragment.appendChild(
                tr
            );

        }
    );


    body.innerHTML = "";

    body.appendChild(
        fragment
    );

}


/* ============================================================
   BUILD TABLE ROW
============================================================ */

function buildRowHTML(
    row,
    index
) {

    const signal =
        row.signal;


    const signalClass =
        signal.toLowerCase();


    const waveClass =
        row.wave.toLowerCase();


    const tideClass =
        row.tide.toLowerCase();


    const filterClass =
        row.filter.toLowerCase();


    const change =
        row.change_percent ??
        row.change;


    const changeClass =
        change > 0
            ? "positive"
            : change < 0
                ? "negative"
                : "neutral";


    const score =
        row.score !== null
            ? formatNumber(
                row.score,
                0
            )
            : "—";


    return `

        <td class="rank-cell">
            ${index}
        </td>


        <td class="symbol-cell">

            <strong>
                ${escapeHTML(
                    row.symbol
                )}
            </strong>

        </td>


        <td class="price-cell">

            ${formatNumber(
                row.price,
                2
            )}

        </td>


        <td class="change-cell ${changeClass}">

            ${
                change !== null
                    ? (
                        change > 0
                            ? "+"
                            : ""
                    ) +
                    formatPercent(change)
                    : "—"
            }

        </td>


        <td>

            ${directionBadge(
                row.wave,
                waveClass
            )}

        </td>


        <td>

            ${directionBadge(
                row.tide,
                tideClass
            )}

        </td>


        <td>

            ${directionBadge(
                row.filter,
                filterClass
            )}

        </td>


        <td>

            ${emaFilterBadge(
                row.filter
            )}

        </td>


        <td>

            ${formatNumber(
                row.rsi,
                1
            )}

        </td>


        <td class="macd-cell">

            ${formatNumber(
                row.macd,
                2
            )}

        </td>


        <td>

            ${formatVolume(
                row.volume
            )}

        </td>


        <td>

            ${formatNumber(
                row.support,
                2
            )}

        </td>


        <td>

            ${formatNumber(
                row.resistance,
                2
            )}

        </td>


        <td>

            <span class="score-badge score-${signalClass}">
                ${score}
            </span>

        </td>


        <td>

            <span class="signal-badge signal-${signalClass}">
                ${signal}
            </span>

        </td>


        <td class="sl-cell">

            ${formatNumber(
                row.sl,
                2
            )}

        </td>


        <td class="target-cell">

            ${formatNumber(
                row.target,
                2
            )}

        </td>


        <td>

            ${
                row.rr !== null
                    ? `1 : ${formatNumber(
                        row.rr,
                        1
                    )}`
                    : "—"
            }

        </td>

    `;

}


/* ============================================================
   DIRECTION BADGE
============================================================ */

function directionBadge(
    value,
    className
) {

    const signal =
        normalizeSignal(
            value
        );


    if (
        signal === "BUY"
    ) {

        return `
            <span class="direction-badge buy">
                ▲ BUY
            </span>
        `;

    }


    if (
        signal === "SELL"
    ) {

        return `
            <span class="direction-badge sell">
                ▼ SELL
            </span>
        `;

    }


    return `
        <span class="direction-badge wait">
            — WAIT
        </span>
    `;

}


/* ============================================================
   EMA FILTER BADGE
============================================================ */

function emaFilterBadge(
    value
) {

    const signal =
        normalizeSignal(
            value
        );


    if (
        signal === "BUY"
    ) {

        return `
            <span class="mini-badge bullish">
                BULLISH
            </span>
        `;

    }


    if (
        signal === "SELL"
    ) {

        return `
            <span class="mini-badge bearish">
                BEARISH
            </span>
        `;

    }


    return `
        <span class="mini-badge neutral">
            NEUTRAL
        </span>
    `;

}


/* ============================================================
   VOLUME FORMAT
============================================================ */

function formatVolume(
    value
) {

    const n =
        numberValue(value);


    if (n === null) {
        return "—";
    }


    if (
        Math.abs(n) >=
        10000000
    ) {

        return (
            n / 10000000
        ).toFixed(2) + " Cr";

    }


    if (
        Math.abs(n) >=
        100000
    ) {

        return (
            n / 100000
        ).toFixed(2) + " L";

    }


    if (
        Math.abs(n) >=
        1000
    ) {

        return (
            n / 1000
        ).toFixed(2) + " K";

    }


    return formatInteger(n);

}


/* ============================================================
   EMPTY TABLE
============================================================ */

function renderEmptyState(
    message
) {

    const body =
        $("scannerBody");


    if (!body) {
        return;
    }


    body.innerHTML = `

        <tr>

            <td
                colspan="18"
                class="empty-state"
            >

                <div class="empty-icon">
                    📡
                </div>

                <strong>
                    ${escapeHTML(
                        message
                    )}
                </strong>

                <span>
                    Waiting for NSE market data
                </span>

            </td>

        </tr>

    `;

}


/* ============================================================
   SEARCH
============================================================ */

function handleSearch(
    event
) {

    state.search =
        event.target.value ||
        "";

    filterAndRender();

}


/* ============================================================
   SIGNAL FILTER
============================================================ */

function handleSignalFilter(
    event
) {

    state.signalFilter =
        event.target.value ||
        "ALL";

    filterAndRender();

}


/* ============================================================
   BUTTON LOADING
============================================================ */

function setButtonLoading(
    button,
    loading,
    loadingText
) {

    if (!button) {
        return;
    }


    if (loading) {

        button.dataset.originalText =
            button.textContent;

        button.disabled =
            true;

        button.textContent =
            loadingText;

    } else {

        button.disabled =
            false;

        button.textContent =
            button.dataset.originalText ||
            button.textContent;

    }

}


/* ============================================================
   RESET API
============================================================ */

async function resetBackend() {

    try {

        await apiRequest(
            API.RESET,
            {
                method: "POST"
            }
        );

        return true;

    } catch (error) {

        console.warn(
            "Backend reset unavailable:",
            error
        );

        return false;

    }

}


/* ============================================================
   EVENT LISTENERS
============================================================ */

function setupEventListeners() {

    const applyButton =
        $("applySettings");


    if (applyButton) {

        applyButton.addEventListener(
            "click",
            applySettings
        );

    }


    const resetButton =
        $("resetSettings");


    if (resetButton) {

        resetButton.addEventListener(
            "click",
            async () => {

                setButtonLoading(
                    resetButton,
                    true,
                    "Resetting..."
                );


                try {

                    await resetBackend();

                    await resetSettings();

                } finally {

                    setButtonLoading(
                        resetButton,
                        false
                    );

                }

            }
        );

    }


    const search =
        $("stockSearch");


    if (search) {

        search.addEventListener(
            "input",
            handleSearch
        );

    }


    const filter =
        $("signalFilter");


    if (filter) {

        filter.addEventListener(
            "change",
            handleSignalFilter
        );

    }


    /*
       Allow Enter key from search field
       without submitting/reloading page.
    */

    if (search) {

        search.addEventListener(
            "keydown",
            event => {

                if (
                    event.key === "Enter"
                ) {

                    event.preventDefault();

                }

            }
        );

    }

}


/* ============================================================
   INITIALIZATION
============================================================ */

async function initialize() {

    console.log(
        "Indian F&O Scanner initializing..."
    );


    setupEventListeners();


    applySettingsToUI(
        DEFAULT_SETTINGS
    );


    renderEmptyState(
        "Connecting to scanner..."
    );


    /*
       Load settings first so the dashboard
       displays the backend configuration.
    */

    await loadSettings();


    /*
       Then load backend status.
    */

    await loadStatus();


    /*
       Then load scanner.
    */

    await loadScanner();


    /*
       Start background refresh.
    */

    setInterval(
        async () => {

            await loadStatus();

        },
        STATUS_INTERVAL
    );


    setInterval(
        async () => {

            await loadScanner();

        },
        REFRESH_INTERVAL
    );


    console.log(
        "Indian F&O Scanner ready."
    );

}


/* ============================================================
   START
============================================================ */

if (
    document.readyState ===
    "loading"
) {

    document.addEventListener(
        "DOMContentLoaded",
        initialize
    );

} else {

    initialize();

}
