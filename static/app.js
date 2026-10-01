"use strict";

/*
 * Indian F&O Scanner
 * Frontend controller
 *
 * Connects to:
 *   /api/status
 *   /api/scanner
 *   /api/settings
 *   /api/reset
 */

const state = {
    scanner: [],
    settings: {},
    status: {},
    filter: "ALL",
    search: ""
};


// =====================================================
// HELPERS
// =====================================================

function $(id) {
    return document.getElementById(id);
}


function safeNumber(value, fallback = 0) {
    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : fallback;
}


function formatNumber(value, decimals = 2) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "--";
    }

    return number.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}


function formatPrice(value) {
    const number = Number(value);

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

    if (Math.abs(number) >= 1) {
        return number.toFixed(2);
    }

    return number.toFixed(4);
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function normalizeDirection(value) {
    const direction = String(value ?? "").toUpperCase();

    if (
        direction.includes("BUY") ||
        direction === "LONG" ||
        direction === "BULLISH"
    ) {
        return "BUY";
    }

    if (
        direction.includes("SELL") ||
        direction === "SHORT" ||
        direction === "BEARISH"
    ) {
        return "SELL";
    }

    return "WAIT";
}


function signalClass(signal) {
    const value = normalizeDirection(signal);

    if (value === "BUY") {
        return "signal-buy";
    }

    if (value === "SELL") {
        return "signal-sell";
    }

    return "signal-wait";
}


function directionClass(direction) {
    const value = normalizeDirection(direction);

    if (value === "BUY") {
        return "direction-buy";
    }

    if (value === "SELL") {
        return "direction-sell";
    }

    return "direction-wait";
}


function displayDirection(value) {
    const direction = normalizeDirection(value);

    if (direction === "BUY") {
        return "BUY";
    }

    if (direction === "SELL") {
        return "SELL";
    }

    return "WAIT";
}


// =====================================================
// API
// =====================================================

async function apiGet(url) {
    const response = await fetch(url, {
        method: "GET",
        cache: "no-store"
    });

    if (!response.ok) {
        throw new Error(
            `HTTP ${response.status}: ${response.statusText}`
        );
    }

    return await response.json();
}


async function apiPost(url, data = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        const text = await response.text();

        throw new Error(
            `HTTP ${response.status}: ${text || response.statusText}`
        );
    }

    return await response.json();
}


// =====================================================
// STATUS
// =====================================================

async function loadStatus() {
    try {

        const data = await apiGet("/api/status");

        state.status = data || {};

        updateConnection(data);
        updateDataStatus(data);

    } catch (error) {

        console.error("Status error:", error);

        updateConnection({
            connected: false,
            status: "offline"
        });

        if ($("historyStatus")) {
            $("historyStatus").textContent =
                "Unable to read scanner status";
        }
    }
}


function updateConnection(data) {

    const connected =
        data?.connected === true ||
        data?.status === "connected" ||
        data?.status === "running" ||
        data?.online === true;

    const dot = $("statusDot");
    const text = $("statusText");

    if (!dot || !text) {
        return;
    }

    dot.classList.remove(
        "online",
        "offline",
        "warning"
    );

    if (connected) {

        dot.classList.add("online");
        text.textContent = "Connected";

    } else {

        dot.classList.add("warning");
        text.textContent = "Connecting...";
    }
}


function updateDataStatus(data) {

    const loaded =
        safeNumber(
            data?.history_loaded ??
            data?.loaded_stocks ??
            data?.stocks_loaded ??
            0
        );

    const total =
        safeNumber(
            data?.total_stocks ??
            data?.universe_size ??
            data?.fno_stocks ??
            0
        );

    if ($("loadedStocks")) {
        $("loadedStocks").textContent =
            loaded.toLocaleString("en-IN");
    }

    if ($("dataStatus")) {

        if (loaded > 0) {
            $("dataStatus").textContent = "LIVE";
        } else {
            $("dataStatus").textContent = "WAITING";
        }
    }

    if ($("historyStatus")) {

        if (total > 0 && loaded > 0) {

            $("historyStatus").textContent =
                `Historical candles loaded for ${loaded}/${total} stocks`;

        } else if (total > 0) {

            $("historyStatus").textContent =
                `Historical candles loaded for 0/${total} stocks`;

        } else {

            $("historyStatus").textContent =
                "Waiting for market data...";
        }
    }
}


// =====================================================
// SETTINGS
// =====================================================

const settingMap = {
    entryTimeframe: "entry_timeframe",
    waveTimeframe: "wave_timeframe",
    tideTimeframe: "tide_timeframe",

    emaFast: "ema_fast",
    emaMedium: "ema_medium",
    emaSlow: "ema_slow",

    rsiPeriod: "rsi_period",

    macdFast: "macd_fast",
    macdSlow: "macd_slow",
    macdSignal: "macd_signal",

    stochPeriod: "stoch_period",
    stochSmooth: "stoch_smooth",

    volumePeriod: "volume_period",

    srLookback: "sr_lookback",
    pivot: "pivot",

    minConfirmation: "min_confirmation",

    riskReward: "risk_reward",

    buyThreshold: "buy_threshold",
    sellThreshold: "sell_threshold"
};


function getInputValue(elementId) {

    const element = $(elementId);

    if (!element) {
        return null;
    }

    if (element.tagName === "SELECT") {
        return element.value;
    }

    return safeNumber(element.value);
}


function collectSettings() {

    const settings = {};

    for (const [elementId, key] of Object.entries(settingMap)) {

        const value = getInputValue(elementId);

        if (value !== null) {
            settings[key] = value;
        }
    }

    return settings;
}


function setInputValue(elementId, value) {

    const element = $(elementId);

    if (!element || value === undefined || value === null) {
        return;
    }

    element.value = value;
}


function applySettingsToForm(settings) {

    if (!settings || typeof settings !== "object") {
        return;
    }

    for (const [elementId, key] of Object.entries(settingMap)) {

        if (settings[key] !== undefined) {
            setInputValue(elementId, settings[key]);
        }
    }
}


async function loadSettings() {

    try {

        const data = await apiGet("/api/settings");

        let settings = data;

        if (data && data.settings) {
            settings = data.settings;
        }

        state.settings = settings || {};

        applySettingsToForm(state.settings);

    } catch (error) {

        console.error("Settings load error:", error);
    }
}


async function saveSettings() {

    const button = $("applySettings");
    const message = $("settingsMessage");

    const settings = collectSettings();

    if (button) {
        button.disabled = true;
        button.textContent = "Applying...";
    }

    if (message) {
        message.textContent = "";
        message.className = "";
    }

    try {

        const response = await apiPost(
            "/api/settings",
            settings
        );

        state.settings = response?.settings || settings;

        applySettingsToForm(state.settings);

        if (message) {
            message.textContent = "Settings applied";
            message.className = "success-message";
        }

        await loadScanner();

    } catch (error) {

        console.error("Settings save error:", error);

        if (message) {
            message.textContent =
                `Error: ${error.message}`;

            message.className = "error-message";
        }

    } finally {

        if (button) {
            button.disabled = false;
            button.textContent = "Apply Settings";
        }
    }
}


async function resetSettings() {

    const button = $("resetSettings");

    if (button) {
        button.disabled = true;
        button.textContent = "Resetting...";
    }

    try {

        const response = await apiPost("/api/reset", {});

        const settings =
            response?.settings ||
            response?.data ||
            response;

        state.settings = settings || {};

        applySettingsToForm(state.settings);

        const message = $("settingsMessage");

        if (message) {
            message.textContent =
                "Settings reset to default";

            message.className =
                "success-message";
        }

        await loadScanner();

    } catch (error) {

        console.error("Reset error:", error);

        const message = $("settingsMessage");

        if (message) {
            message.textContent =
                `Reset error: ${error.message}`;

            message.className =
                "error-message";
        }

    } finally {

        if (button) {
            button.disabled = false;
            button.textContent = "Reset";
        }
    }
}


// =====================================================
// SCANNER
// =====================================================

async function loadScanner() {

    try {

        const data = await apiGet("/api/scanner");

        let rows = [];

        if (Array.isArray(data)) {
            rows = data;
        } else if (Array.isArray(data?.stocks)) {
            rows = data.stocks;
        } else if (Array.isArray(data?.scanner)) {
            rows = data.scanner;
        } else if (Array.isArray(data?.data)) {
            rows = data.data;
        } else if (Array.isArray(data?.results)) {
            rows = data.results;
        }

        state.scanner = rows;

        renderScanner(rows);
        updateSummary(rows);

        updateLastUpdate();

    } catch (error) {

        console.error("Scanner error:", error);

        const body = $("scannerBody");

        if (body) {

            body.innerHTML = `
                <tr>
                    <td colspan="17" class="empty-state error-row">
                        Unable to load scanner data
                    </td>
                </tr>
            `;
        }
    }
}


// =====================================================
// NORMALIZE STOCK DATA
// =====================================================

function getStockSymbol(row) {

    return (
        row?.symbol ??
        row?.trading_symbol ??
        row?.groww_symbol ??
        row?.name ??
        row?.ticker ??
        "--"
    );
}


function getLtp(row) {

    return (
        row?.ltp ??
        row?.last_price ??
        row?.lastPrice ??
        row?.price ??
        row?.close ??
        0
    );
}


function getChange(row) {

    return (
        row?.change_percent ??
        row?.change_pct ??
        row?.changePercent ??
        row?.percent_change ??
        row?.change ??
        0
    );
}


function getWave(row) {

    return (
        row?.wave ??
        row?.wave_direction ??
        row?.wave_signal ??
        "WAIT"
    );
}


function getTide(row) {

    return (
        row?.tide ??
        row?.tide_direction ??
        row?.tide_signal ??
        "WAIT"
    );
}


function getSignal(row) {

    return (
        row?.signal ??
        row?.action ??
        row?.trade_signal ??
        "WAIT"
    );
}


function getScore(row) {

    return (
        row?.score ??
        row?.signal_score ??
        row?.total_score ??
        0
    );
}


function getRsi(row) {

    return (
        row?.rsi ??
        row?.RSI ??
        row?.rsi_value ??
        0
    );
}


function getMacd(row) {

    return (
        row?.macd ??
        row?.MACD ??
        row?.macd_value ??
        0
    );
}


function getEma(row) {

    return (
        row?.ema_direction ??
        row?.ema_signal ??
        row?.ema_trend ??
        row?.ema ??
        "WAIT"
    );
}


function getVolume(row) {

    return (
        row?.volume_signal ??
        row?.volume_status ??
        row?.volume ??
        "WAIT"
    );
}


function getSupport(row) {

    return (
        row?.support ??
        row?.support_level ??
        row?.support_price ??
        0
    );
}


function getResistance(row) {

    return (
        row?.resistance ??
        row?.resistance_level ??
        row?.resistance_price ??
        0
    );
}


function getStopLoss(row) {

    return (
        row?.stop_loss ??
        row?.sl ??
        row?.stopLoss ??
        0
    );
}


function getTarget(row) {

    return (
        row?.target ??
        row?.target_price ??
        row?.targetPrice ??
        0
    );
}


function getRR(row) {

    return (
        row?.rr ??
        row?.risk_reward ??
        row?.riskReward ??
        0
    );
}


// =====================================================
// TABLE
// =====================================================

function renderScanner(rows) {

    const body = $("scannerBody");

    if (!body) {
        return;
    }

    const filtered = filterRows(rows);

    if (!filtered.length) {

        body.innerHTML = `
            <tr>
                <td colspan="17" class="empty-state">
                    No stocks match the current filter
                </td>
            </tr>
        `;

        return;
    }

    body.innerHTML = filtered.map((row, index) => {

        const symbol =
            escapeHtml(getStockSymbol(row));

        const ltp =
            getLtp(row);

        const change =
            safeNumber(getChange(row));

        const wave =
            normalizeDirection(getWave(row));

        const tide =
            normalizeDirection(getTide(row));

        const ema =
            normalizeDirection(getEma(row));

        const rsi =
            safeNumber(getRsi(row));

        const macd =
            safeNumber(getMacd(row));

        const volume =
            normalizeDirection(getVolume(row));

        const support =
            getSupport(row);

        const resistance =
            getResistance(row);

        const score =
            safeNumber(getScore(row));

        const signal =
            normalizeDirection(getSignal(row));

        const sl =
            getStopLoss(row);

        const target =
            getTarget(row);

        const rr =
            safeNumber(getRR(row));

        const changeClass =
            change > 0
                ? "positive"
                : change < 0
                    ? "negative"
                    : "";

        return `
            <tr>

                <td>${index + 1}</td>

                <td>
                    <div class="stock-name">
                        ${symbol}
                    </div>
                </td>

                <td class="price-cell">
                    ${formatPrice(ltp)}
                </td>

                <td class="${changeClass}">
                    ${change > 0 ? "+" : ""}
                    ${formatNumber(change, 2)}%
                </td>

                <td>
                    <span class="direction ${directionClass(wave)}">
                        ${wave}
                    </span>
                </td>

                <td>
                    <span class="direction ${directionClass(tide)}">
                        ${tide}
                    </span>
                </td>

                <td>
                    <span class="direction ${directionClass(ema)}">
                        ${ema}
                    </span>
                </td>

                <td>
                    ${formatNumber(rsi, 2)}
                </td>

                <td>
                    ${formatNumber(macd, 4)}
                </td>

                <td>
                    <span class="direction ${directionClass(volume)}">
                        ${volume}
                    </span>
                </td>

                <td>
                    ${formatPrice(support)}
                </td>

                <td>
                    ${formatPrice(resistance)}
                </td>

                <td>
                    <span class="score">
                        ${formatNumber(score, 0)}
                    </span>
                </td>

                <td>
                    <span class="signal ${signalClass(signal)}">
                        ${signal}
                    </span>
                </td>

                <td>
                    ${formatPrice(sl)}
                </td>

                <td>
                    ${formatPrice(target)}
                </td>

                <td>
                    ${rr > 0 ? "1:" + formatNumber(rr, 1) : "--"}
                </td>

            </tr>
        `;

    }).join("");
}


function filterRows(rows) {

    const search =
        state.search.trim().toUpperCase();

    const filter =
        state.filter;

    return rows.filter(row => {

        const symbol =
            String(getStockSymbol(row))
                .toUpperCase();

        const signal =
            normalizeDirection(getSignal(row));

        const matchesSearch =
            !search ||
            symbol.includes(search);

        const matchesFilter =
            filter === "ALL" ||
            signal === filter;

        return (
            matchesSearch &&
            matchesFilter
        );
    });
}


// =====================================================
// SUMMARY
// =====================================================

function updateSummary(rows) {

    let buy = 0;
    let sell = 0;
    let wait = 0;

    for (const row of rows) {

        const signal =
            normalizeDirection(getSignal(row));

        if (signal === "BUY") {
            buy++;
        } else if (signal === "SELL") {
            sell++;
        } else {
            wait++;
        }
    }

    if ($("totalStocks")) {
        $("totalStocks").textContent =
            rows.length.toLocaleString("en-IN");
    }

    if ($("buyCount")) {
        $("buyCount").textContent =
            buy.toLocaleString("en-IN");
    }

    if ($("sellCount")) {
        $("sellCount").textContent =
            sell.toLocaleString("en-IN");
    }

    if ($("waitCount")) {
        $("waitCount").textContent =
            wait.toLocaleString("en-IN");
    }
}


// =====================================================
// TIME
// =====================================================

function updateLastUpdate() {

    const element = $("lastUpdate");

    if (!element) {
        return;
    }

    const now = new Date();

    element.textContent =
        `Updated ${now.toLocaleTimeString("en-IN")}`;
}


// =====================================================
// EVENTS
// =====================================================

function setupEvents() {

    const applyButton =
        $("applySettings");

    if (applyButton) {
        applyButton.addEventListener(
            "click",
            saveSettings
        );
    }


    const resetButton =
        $("resetSettings");

    if (resetButton) {
        resetButton.addEventListener(
            "click",
            resetSettings
        );
    }


    const filter =
        $("signalFilter");

    if (filter) {

        filter.addEventListener(
            "change",
            event => {

                state.filter =
                    event.target.value;

                renderScanner(state.scanner);
            }
        );
    }


    const search =
        $("searchStock");

    if (search) {

        search.addEventListener(
            "input",
            event => {

                state.search =
                    event.target.value;

                renderScanner(state.scanner);
            }
        );
    }
}


// =====================================================
// POLLING
// =====================================================

let scannerTimer = null;
let statusTimer = null;


function startPolling() {

    if (scannerTimer) {
        clearInterval(scannerTimer);
    }

    if (statusTimer) {
        clearInterval(statusTimer);
    }

    /*
     * Scanner refresh:
     * every 5 seconds
     */
    scannerTimer = setInterval(
        loadScanner,
        5000
    );

    /*
     * Status refresh:
     * every 5 seconds
     */
    statusTimer = setInterval(
        loadStatus,
        5000
    );
}


// =====================================================
// START APPLICATION
// =====================================================

async function startApp() {

    setupEvents();

    await loadSettings();

    await loadStatus();

    await loadScanner();

    startPolling();
}


document.addEventListener(
    "DOMContentLoaded",
    startApp
);
