/* =========================================================
   INDIAN F&O SCANNER
   PROFESSIONAL DASHBOARD JAVASCRIPT
   ========================================================= */

"use strict";


/* =========================================================
   CONFIGURATION
   ========================================================= */

const API = {
    status: "/api/status",
    scanner: "/api/scanner",
    settings: "/api/settings",
    reset: "/api/reset"
};


/*
   IMPORTANT
   We deliberately DO NOT call /api/groww-test automatically.

   Groww authentication has a rate limit.
   The dashboard should only read the existing backend status.
*/


const POLL_INTERVAL = 10000;
const SCANNER_INTERVAL = 15000;


/* =========================================================
   APPLICATION STATE
   ========================================================= */

const state = {
    status: null,
    scanner: [],
    filteredScanner: [],

    signalFilter: "ALL",
    searchText: "",

    settings: {},

    statusTimer: null,
    scannerTimer: null,

    loadingStatus: false,
    loadingScanner: false
};


/* =========================================================
   DOM HELPERS
   ========================================================= */

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
        value === undefined ||
        value === ""
            ? "--"
            : String(value);
}


function showElement(id) {
    const element = $(id);

    if (element) {
        element.style.display = "";
    }
}


function hideElement(id) {
    const element = $(id);

    if (element) {
        element.style.display = "none";
    }
}


/* =========================================================
   NUMBER HELPERS
   ========================================================= */

function numberValue(value, fallback = 0) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return fallback;
    }

    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : fallback;
}


function formatNumber(value, decimals = 2) {
    const number = numberValue(value, NaN);

    if (!Number.isFinite(number)) {
        return "--";
    }

    return number.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}


function formatInteger(value) {
    const number = numberValue(value, NaN);

    if (!Number.isFinite(number)) {
        return "--";
    }

    return Math.round(number).toLocaleString("en-IN");
}


function formatPrice(value) {
    const number = numberValue(value, NaN);

    if (!Number.isFinite(number)) {
        return "--";
    }

    if (Math.abs(number) >= 1000) {
        return number.toLocaleString("en-IN", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    if (Math.abs(number) >= 100) {
        return number.toFixed(2);
    }

    if (Math.abs(number) >= 10) {
        return number.toFixed(2);
    }

    return number.toFixed(2);
}


/* =========================================================
   HTML SAFETY
   ========================================================= */

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


/* =========================================================
   API REQUEST
   ========================================================= */

async function apiRequest(
    url,
    options = {}
) {

    const response = await fetch(
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

    const text = await response.text();

    let data = {};

    try {
        data = text
            ? JSON.parse(text)
            : {};
    } catch (error) {

        data = {
            raw: text
        };
    }

    if (!response.ok) {

        const message =
            data.message ||
            data.error ||
            data.detail ||
            `HTTP ${response.status}`;

        throw new Error(message);
    }

    return data;
}


/* =========================================================
   CONNECTION STATUS
   ========================================================= */

function updateConnection(
    connected,
    error = false
) {

    const dot = $("connectionDot");
    const text = $("connectionText");

    if (!dot || !text) {
        return;
    }

    dot.classList.remove(
        "live",
        "error"
    );

    if (error) {

        dot.classList.add("error");

        text.textContent =
            "Connection Error";

        return;
    }

    if (connected) {

        dot.classList.add("live");

        text.textContent =
            "Connected";

        return;
    }

    text.textContent =
        "Connecting...";
}


/* =========================================================
   STATUS ERROR
   ========================================================= */

function showError(message) {

    const element = $("errorMessage");

    if (!element) {
        return;
    }

    if (!message) {

        element.textContent = "";

        element.style.display = "none";

        return;
    }

    element.textContent =
        String(message);

    element.style.display =
        "block";
}


/* =========================================================
   STATUS UPDATE
   ========================================================= */

async function loadStatus() {

    if (state.loadingStatus) {
        return;
    }

    state.loadingStatus = true;

    try {

        const data =
            await apiRequest(API.status);

        state.status = data;

        updateConnection(
            true,
            false
        );

        updateStatusUI(data);

    } catch (error) {

        console.error(
            "Status error:",
            error
        );

        updateConnection(
            false,
            true
        );

        setText(
            "marketStatus",
            "Connection Error"
        );

        showError(
            error.message ||
            "Unable to connect to scanner backend."
        );

    } finally {

        state.loadingStatus = false;
    }
}


/* =========================================================
   STATUS UI
   ========================================================= */

function updateStatusUI(data) {

    if (!data) {
        return;
    }


    /* -----------------------------------------------------
       F&O STOCK COUNT
       ----------------------------------------------------- */

    const fnoCount =
        data.fno_stock_count ??
        data.fnoStocks ??
        data.fno_stocks ??
        data.universe_count ??
        0;

    setText(
        "fnoStocks",
        formatInteger(fnoCount)
    );


    setText(
        "universeStatus",
        `${formatInteger(fnoCount)} stocks`
    );


    /* -----------------------------------------------------
       LIVE PRICE COUNT
       ----------------------------------------------------- */

    const livePrices =
        data.live_prices ??
        data.livePrices ??
        data.ltp_count ??
        0;

    setText(
        "livePrices",
        formatInteger(livePrices)
    );


    /* -----------------------------------------------------
       MARKET STATUS
       ----------------------------------------------------- */

    let marketStatus =
        data.market_status ??
        data.marketStatus ??
        data.status ??
        "UNKNOWN";

    marketStatus =
        String(marketStatus);

    setText(
        "marketStatus",
        marketStatus
    );


    /* -----------------------------------------------------
       HISTORY
       ----------------------------------------------------- */

    const historyLoaded =
        data.history_loaded ??
        data.historyLoaded ??
        0;

    const historyFailed =
        data.history_failed ??
        data.historyFailed ??
        0;

    let historyText =
        `${formatInteger(historyLoaded)} loaded`;

    if (
        numberValue(historyFailed) > 0
    ) {

        historyText +=
            ` • ${formatInteger(historyFailed)} failed`;
    }

    setText(
        "historyStatus",
        historyText
    );


    /* -----------------------------------------------------
       LAST UPDATE
       ----------------------------------------------------- */

    const lastUpdate =
        data.last_history_update ??
        data.lastHistoryUpdate ??
        data.last_ltp_update ??
        data.lastLtpUpdate ??
        null;

    setText(
        "lastUpdate",
        formatDateTime(lastUpdate)
    );


    /* -----------------------------------------------------
       AUTHENTICATION ERROR
       ----------------------------------------------------- */

    const authenticated =
        data.authenticated;

    const lastError =
        data.last_error ??
        data.lastError ??
        data.message ??
        null;


    if (
        authenticated === false &&
        lastError
    ) {

        showError(
            String(lastError)
        );

    } else if (
        marketStatus === "ERROR" &&
        lastError
    ) {

        showError(
            String(lastError)
        );

    } else {

        showError(null);
    }
}


/* =========================================================
   DATE/TIME
   ========================================================= */

function formatDateTime(value) {

    if (
        !value ||
        value === "--"
    ) {
        return "--";
    }

    try {

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

    } catch (error) {

        return String(value);
    }
}


/* =========================================================
   SCANNER DATA
   ========================================================= */

async function loadScanner() {

    if (state.loadingScanner) {
        return;
    }

    state.loadingScanner = true;

    try {

        const data =
            await apiRequest(API.scanner);

        const rows =
            extractScannerRows(data);

        state.scanner =
            rows.map(
                normalizeScannerRow
            );

        applyFilters();

        updateSignalCounters();

    } catch (error) {

        console.error(
            "Scanner error:",
            error
        );

        /*
           Don't overwrite the existing scanner
           with an empty result when backend is
           temporarily unavailable.
        */

    } finally {

        state.loadingScanner = false;
    }
}


/* =========================================================
   EXTRACT SCANNER ROWS
   ========================================================= */

function extractScannerRows(data) {

    if (Array.isArray(data)) {
        return data;
    }

    if (!data) {
        return [];
    }

    const possibleKeys = [
        "results",
        "scanner",
        "data",
        "rows",
        "stocks",
        "signals",
        "items"
    ];

    for (
        const key of possibleKeys
    ) {

        if (
            Array.isArray(data[key])
        ) {
            return data[key];
        }
    }

    return [];
}


/* =========================================================
   NORMALIZE SCANNER ROW
   ========================================================= */

function normalizeScannerRow(row) {

    if (!row) {
        return {};
    }

    const signal =
        row.signal ??
        row.Signal ??
        row.action ??
        row.side ??
        row.recommendation ??
        "WAIT";

    return {
        symbol:
            row.symbol ??
            row.stock ??
            row.ticker ??
            row.name ??
            "--",

        ltp:
            row.ltp ??
            row.price ??
            row.close ??
            row.last_price ??
            0,

        change:
            row.change ??
            row.change_percent ??
            row.change_pct ??
            row.pct_change ??
            0,

        wave:
            row.wave ??
            row.wave_signal ??
            row.waveSignal ??
            "--",

        tide:
            row.tide ??
            row.tide_signal ??
            row.tideSignal ??
            "--",

        ema:
            row.ema ??
            row.ema_signal ??
            row.emaSignal ??
            "--",

        rsi:
            row.rsi ??
            row.RSI ??
            0,

        macd:
            row.macd ??
            row.MACD ??
            "--",

        volume:
            row.volume ??
            row.volume_status ??
            row.volume_signal ??
            "--",

        support:
            row.support ??
            row.support_level ??
            row.supportLevel ??
            0,

        resistance:
            row.resistance ??
            row.resistance_level ??
            row.resistanceLevel ??
            0,

        score:
            row.score ??
            row.total_score ??
            row.totalScore ??
            0,

        signal:
            normalizeSignal(signal),

        sl:
            row.sl ??
            row.stop_loss ??
            row.stopLoss ??
            row.stoploss ??
            0,

        target:
            row.target ??
            row.take_profit ??
            row.takeProfit ??
            0,

        rr:
            row.rr ??
            row.risk_reward ??
            row.riskReward ??
            0
    };
}


/* =========================================================
   SIGNAL NORMALIZATION
   ========================================================= */

function normalizeSignal(value) {

    const signal =
        String(value || "")
            .trim()
            .toUpperCase();

    if (
        signal.includes("BUY") ||
        signal === "LONG"
    ) {
        return "BUY";
    }

    if (
        signal.includes("SELL") ||
        signal === "SHORT"
    ) {
        return "SELL";
    }

    return "WAIT";
}


/* =========================================================
   FILTERS
   ========================================================= */

function applyFilters() {

    const filter =
        state.signalFilter;

    const search =
        state.searchText
            .trim()
            .toUpperCase();


    state.filteredScanner =
        state.scanner.filter(
            row => {

                const signalMatch =
                    filter === "ALL" ||
                    row.signal === filter;

                const symbol =
                    String(
                        row.symbol || ""
                    ).toUpperCase();

                const searchMatch =
                    !search ||
                    symbol.includes(search);

                return (
                    signalMatch &&
                    searchMatch
                );
            }
        );


    renderScanner();
}


/* =========================================================
   SCANNER TABLE
   ========================================================= */

function renderScanner() {

    const body =
        $("scannerBody");

    if (!body) {
        return;
    }


    if (
        state.filteredScanner.length === 0
    ) {

        body.innerHTML = `
            <tr>
                <td
                    colspan="17"
                    class="empty-state"
                >
                    <div class="empty-icon">
                        📊
                    </div>

                    <div>
                        ${
                            state.scanner.length === 0
                                ? "Waiting for scanner data..."
                                : "No stocks match the selected filter."
                        }
                    </div>
                </td>
            </tr>
        `;

        return;
    }


    body.innerHTML =
        state.filteredScanner
            .map(
                (row, index) =>
                    createScannerRow(
                        row,
                        index + 1
                    )
            )
            .join("");
}


/* =========================================================
   TABLE ROW
   ========================================================= */

function createScannerRow(
    row,
    index
) {

    const signalClass =
        getSignalClass(
            row.signal
        );


    const change =
        numberValue(
            row.change,
            NaN
        );


    const changeClass =
        Number.isFinite(change)
            ? (
                change > 0
                    ? "positive"
                    : change < 0
                        ? "negative"
                        : ""
            )
            : "";


    return `
        <tr>

            <td>
                ${index}
            </td>

            <td>
                <span class="symbol">
                    ${escapeHTML(row.symbol)}
                </span>
            </td>

            <td>
                ${formatPrice(row.ltp)}
            </td>

            <td class="${changeClass}">
                ${
                    Number.isFinite(change)
                        ? `${change > 0 ? "+" : ""}${formatNumber(change, 2)}%`
                        : "--"
                }
            </td>

            <td>
                ${signalText(row.wave)}
            </td>

            <td>
                ${signalText(row.tide)}
            </td>

            <td>
                ${signalText(row.ema)}
            </td>

            <td>
                ${formatNumber(row.rsi, 1)}
            </td>

            <td>
                ${formatIndicator(row.macd)}
            </td>

            <td>
                ${formatIndicator(row.volume)}
            </td>

            <td>
                ${formatPrice(row.support)}
            </td>

            <td>
                ${formatPrice(row.resistance)}
            </td>

            <td>
                <span class="score">
                    ${formatNumber(row.score, 0)}
                </span>
            </td>

            <td>
                <span class="signal-badge ${signalClass}">
                    ${escapeHTML(row.signal)}
                </span>
            </td>

            <td>
                ${formatPrice(row.sl)}
            </td>

            <td>
                ${formatPrice(row.target)}
            </td>

            <td>
                ${
                    numberValue(row.rr, NaN) !==
                    NaN
                        ? formatNumber(row.rr, 2)
                        : "--"
                }
            </td>

        </tr>
    `;
}


/* =========================================================
   SIGNAL CLASS
   ========================================================= */

function getSignalClass(signal) {

    if (signal === "BUY") {
        return "signal-buy";
    }

    if (signal === "SELL") {
        return "signal-sell";
    }

    return "signal-wait";
}


/* =========================================================
   SIGNAL TEXT
   ========================================================= */

function signalText(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "--";
    }

    const text =
        String(value)
            .toUpperCase();

    if (
        text === "BUY" ||
        text === "BULLISH"
    ) {

        return `
            <span class="positive">
                ${escapeHTML(text)}
            </span>
        `;
    }

    if (
        text === "SELL" ||
        text === "BEARISH"
    ) {

        return `
            <span class="negative">
                ${escapeHTML(text)}
            </span>
        `;
    }

    return escapeHTML(
        String(value)
    );
}


/* =========================================================
   INDICATOR TEXT
   ========================================================= */

function formatIndicator(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "--";
    }

    if (
        typeof value === "number"
    ) {
        return formatNumber(
            value,
            2
        );
    }

    return escapeHTML(
        String(value)
    );
}


/* =========================================================
   SIGNAL COUNTERS
   ========================================================= */

function updateSignalCounters() {

    let buy = 0;
    let sell = 0;
    let wait = 0;


    for (
        const row of state.scanner
    ) {

        if (row.signal === "BUY") {
            buy++;
        } else if (
            row.signal === "SELL"
        ) {
            sell++;
        } else {
            wait++;
        }
    }


    setText(
        "buySignals",
        formatInteger(buy)
    );

    setText(
        "sellSignals",
        formatInteger(sell)
    );

    setText(
        "waitSignals",
        formatInteger(wait)
    );
}


/* =========================================================
   SETTINGS
   ========================================================= */

const SETTING_FIELDS = {

    entryTimeframe: [
        "entry_timeframe",
        "entryTimeframe"
    ],

    waveTimeframe: [
        "wave_timeframe",
        "waveTimeframe"
    ],

    tideTimeframe: [
        "tide_timeframe",
        "tideTimeframe"
    ],

    emaFast: [
        "ema_fast",
        "emaFast"
    ],

    emaMedium: [
        "ema_medium",
        "emaMedium"
    ],

    emaSlow: [
        "ema_slow",
        "emaSlow"
    ],

    rsiPeriod: [
        "rsi_period",
        "rsiPeriod"
    ],

    macdFast: [
        "macd_fast",
        "macdFast"
    ],

    macdSlow: [
        "macd_slow",
        "macdSlow"
    ],

    macdSignal: [
        "macd_signal",
        "macdSignal"
    ],

    stochasticPeriod: [
        "stochastic_period",
        "stochasticPeriod"
    ],

    stochasticSmooth: [
        "stochastic_smooth",
        "stochasticSmooth"
    ],

    volumeSma: [
        "volume_sma",
        "volumeSma"
    ],

    srLookback: [
        "sr_lookback",
        "srLookback"
    ],

    pivot: [
        "pivot",
        "pivot_points"
    ],

    minConfirmation: [
        "min_confirmation",
        "minConfirmation"
    ],

    riskReward: [
        "risk_reward",
        "riskReward"
    ],

    buyScore: [
        "buy_score",
        "buyScore"
    ],

    sellScore: [
        "sell_score",
        "sellScore"
    ]
};


/* =========================================================
   FIND SETTING VALUE
   ========================================================= */

function findSetting(
    data,
    keys
) {

    if (!data) {
        return undefined;
    }

    for (
        const key of keys
    ) {

        if (
            data[key] !== undefined &&
            data[key] !== null
        ) {
            return data[key];
        }
    }

    return undefined;
}


/* =========================================================
   LOAD SETTINGS
   ========================================================= */

async function loadSettings() {

    try {

        const data =
            await apiRequest(
                API.settings
            );

        const settings =
            data.settings ??
            data.data ??
            data;

        state.settings =
            settings || {};

        populateSettings(
            state.settings
        );

    } catch (error) {

        console.warn(
            "Settings could not be loaded:",
            error
        );

        /*
           Keep the HTML defaults if backend
           settings aren't available.
        */
    }
}


/* =========================================================
   POPULATE SETTINGS
   ========================================================= */

function populateSettings(
    settings
) {

    for (
        const [
            elementId,
            keys
        ] of Object.entries(
            SETTING_FIELDS
        )
    ) {

        const value =
            findSetting(
                settings,
                keys
            );

        if (
            value === undefined
        ) {
            continue;
        }

        const element =
            $(elementId);

        if (!element) {
            continue;
        }

        element.value =
            value;
    }
}


/* =========================================================
   COLLECT SETTINGS
   ========================================================= */

function collectSettings() {

    const settings = {};

    for (
        const [
            elementId,
            keys
        ] of Object.entries(
            SETTING_FIELDS
        )
    ) {

        const element =
            $(elementId);

        if (!element) {
            continue;
        }

        let value =
            element.value;


        if (
            element.type === "number"
        ) {

            value =
                Number(value);
        }


        /*
           Send the first backend-style
           snake_case name.
        */

        settings[keys[0]] =
            value;
    }

    return settings;
}


/* =========================================================
   APPLY SETTINGS
   ========================================================= */

async function applySettings() {

    const button =
        $("applySettings");

    const message =
        $("settingsMessage");


    const settings =
        collectSettings();


    if (button) {

        button.disabled = true;

        button.textContent =
            "Saving...";
    }


    if (message) {

        message.textContent =
            "Applying settings...";
    }


    try {

        await apiRequest(
            API.settings,
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


        state.settings =
            settings;


        if (message) {

            message.textContent =
                "✓ Settings applied";
        }


        /*
           Give backend a moment to recalculate.
        */

        setTimeout(
            loadScanner,
            500
        );


        setTimeout(
            () => {

                if (message) {
                    message.textContent = "";
                }

            },
            3000
        );


    } catch (error) {

        console.error(
            "Settings save error:",
            error
        );


        if (message) {

            message.textContent =
                `Error: ${error.message}`;
        }

    } finally {

        if (button) {

            button.disabled = false;

            button.textContent =
                "Apply Settings";
        }
    }
}


/* =========================================================
   RESET SETTINGS
   ========================================================= */

async function resetSettings() {

    const button =
        $("resetSettings");

    const message =
        $("settingsMessage");


    if (button) {

        button.disabled = true;

        button.textContent =
            "Resetting...";
    }


    try {

        /*
           Try backend reset first.
        */

        let data = null;

        try {

            data =
                await apiRequest(
                    API.reset,
                    {
                        method: "POST"
                    }
                );

        } catch (resetError) {

            /*
               If backend doesn't expose reset,
               simply reload defaults from settings.
            */

            console.warn(
                "Backend reset unavailable:",
                resetError
            );
        }


        if (
            data &&
            (
                data.settings ||
                data.data
            )
        ) {

            populateSettings(
                data.settings ||
                data.data
            );

        } else {

            await loadSettings();
        }


        if (message) {

            message.textContent =
                "✓ Settings reset";
        }


        setTimeout(
            () => {

                if (message) {
                    message.textContent = "";
                }

            },
            2500
        );


    } catch (error) {

        console.error(
            "Reset error:",
            error
        );


        if (message) {

            message.textContent =
                `Error: ${error.message}`;
        }

    } finally {

        if (button) {

            button.disabled = false;

            button.textContent =
                "Reset";
        }
    }
}


/* =========================================================
   EVENT LISTENERS
   ========================================================= */

function setupEvents() {


    /* -----------------------------------------------------
       SIGNAL FILTER
       ----------------------------------------------------- */

    const signalFilter =
        $("signalFilter");

    if (signalFilter) {

        signalFilter.addEventListener(
            "change",
            event => {

                state.signalFilter =
                    event.target.value;

                applyFilters();
            }
        );
    }


    /* -----------------------------------------------------
       STOCK SEARCH
       ----------------------------------------------------- */

    const search =
        $("stockSearch");

    if (search) {

        search.addEventListener(
            "input",
            event => {

                state.searchText =
                    event.target.value;

                applyFilters();
            }
        );
    }


    /* -----------------------------------------------------
       APPLY SETTINGS
       ----------------------------------------------------- */

    const apply =
        $("applySettings");

    if (apply) {

        apply.addEventListener(
            "click",
            applySettings
        );
    }


    /* -----------------------------------------------------
       RESET SETTINGS
       ----------------------------------------------------- */

    const reset =
        $("resetSettings");

    if (reset) {

        reset.addEventListener(
            "click",
            resetSettings
        );
    }
}


/* =========================================================
   AUTO REFRESH
   ========================================================= */

function startPolling() {

    /*
       Clear old timers first.
    */

    if (state.statusTimer) {

        clearInterval(
            state.statusTimer
        );
    }

    if (state.scannerTimer) {

        clearInterval(
            state.scannerTimer
        );
    }


    /*
       STATUS
    */

    state.statusTimer =
        setInterval(
            loadStatus,
            POLL_INTERVAL
        );


    /*
       SCANNER
    */

    state.scannerTimer =
        setInterval(
            loadScanner,
            SCANNER_INTERVAL
        );
}


/* =========================================================
   INITIALIZATION
   ========================================================= */

async function initializeApp() {

    console.log(
        "Indian F&O Scanner starting..."
    );


    setupEvents();


    /*
       Initial status.
    */

    await loadStatus();


    /*
       Load settings.
    */

    await loadSettings();


    /*
       Load scanner.
    */

    await loadScanner();


    /*
       Start automatic refresh.
    */

    startPolling();


    console.log(
        "Indian F&O Scanner ready."
    );
}


/* =========================================================
   PAGE VISIBILITY
   ========================================================= */

document.addEventListener(
    "visibilitychange",
    () => {

        /*
           When user comes back to the tab,
           immediately refresh the data.
        */

        if (
            document.visibilityState ===
            "visible"
        ) {

            loadStatus();
            loadScanner();
        }
    }
);


/* =========================================================
   START
   ========================================================= */

if (
    document.readyState ===
    "loading"
) {

    document.addEventListener(
        "DOMContentLoaded",
        initializeApp
    );

} else {

    initializeApp();
}
