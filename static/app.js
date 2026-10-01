/* =========================================================
   INDIAN F&O SCANNER
   PROFESSIONAL DASHBOARD JAVASCRIPT
   ========================================================= */

"use strict";


/* =========================================================
   GLOBAL CONFIGURATION
   ========================================================= */

const API = {

    status: "/api/status",

    scanner: "/api/scanner",

    settings: "/api/settings",

    reset: "/api/reset",

    growwTest: "/api/groww-test"

};


const POLL_INTERVAL = 5000;

const STATUS_INTERVAL = 5000;


/* =========================================================
   DEFAULT SETTINGS
   ========================================================= */

const DEFAULT_SETTINGS = {

    entry_timeframe: "5m",

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

    sell_score: 30

};


/* =========================================================
   APPLICATION STATE
   ========================================================= */

const STATE = {

    settings: {
        ...DEFAULT_SETTINGS
    },

    scannerData: [],

    filteredData: [],

    status: null,

    lastScannerUpdate: null,

    isLoadingScanner: false,

    isApplyingSettings: false,

    isResetting: false

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
        value === undefined
            ? "-"
            : String(value);

}


function setHTML(id, html) {

    const element = $(id);

    if (!element) {
        return;
    }

    element.innerHTML = html;

}


function showElement(id) {

    const element = $(id);

    if (!element) {
        return;
    }

    element.classList.remove("hidden");

}


function hideElement(id) {

    const element = $(id);

    if (!element) {
        return;
    }

    element.classList.add("hidden");

}


/* =========================================================
   SAFE NUMBER
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


/* =========================================================
   SAFE TEXT
   ========================================================= */

function safeText(value, fallback = "-") {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return fallback;

    }

    return String(value);

}


/* =========================================================
   FETCH JSON
   ========================================================= */

async function fetchJSON(
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


    let data = null;


    try {

        data = await response.json();

    } catch (error) {

        data = null;

    }


    if (!response.ok) {

        let message =
            `HTTP ${response.status}`;

        if (data) {

            if (typeof data === "string") {

                message = data;

            } else if (data.message) {

                message = data.message;

            } else if (data.detail) {

                message = data.detail;

            }

        }

        throw new Error(message);

    }


    return data;

}


/* =========================================================
   TOAST
   ========================================================= */

let toastTimer = null;


function showToast(
    message,
    type = "normal"
) {

    const toast = $("toast");

    const toastMessage =
        $("toastMessage");


    if (!toast || !toastMessage) {
        return;
    }


    toastMessage.textContent =
        message;


    toast.classList.remove(
        "toast-success",
        "toast-error"
    );


    if (type === "success") {

        toast.classList.add(
            "toast-success"
        );

    }


    if (type === "error") {

        toast.classList.add(
            "toast-error"
        );

    }


    toast.classList.add("show");


    clearTimeout(toastTimer);


    toastTimer = setTimeout(
        () => {

            toast.classList.remove(
                "show"
            );

        },
        2800
    );

}


/* =========================================================
   ERROR DISPLAY
   ========================================================= */

function showError(message) {

    const box = $("errorMessage");

    if (!box) {
        return;
    }


    box.textContent =
        safeText(
            message,
            "Scanner error"
        );


    box.classList.remove(
        "hidden"
    );

}


function clearError() {

    const box = $("errorMessage");

    if (!box) {
        return;
    }

    box.textContent = "";

    box.classList.add(
        "hidden"
    );

}


/* =========================================================
   SETTINGS COLLAPSE
   ========================================================= */

function initSettingsToggle() {

    const toggle =
        $("settingsToggle");

    const content =
        $("settingsContent");


    if (!toggle || !content) {
        return;
    }


    function toggleSettings() {

        const open =
            content.classList.contains(
                "open"
            );


        if (open) {

            content.classList.remove(
                "open"
            );

            toggle.classList.remove(
                "open"
            );

            toggle.setAttribute(
                "aria-expanded",
                "false"
            );

        } else {

            content.classList.add(
                "open"
            );

            toggle.classList.add(
                "open"
            );

            toggle.setAttribute(
                "aria-expanded",
                "true"
            );

        }

    }


    toggle.addEventListener(
        "click",
        toggleSettings
    );


    toggle.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Enter" ||
                event.key === " "
            ) {

                event.preventDefault();

                toggleSettings();

            }

        }
    );

}


/* =========================================================
   INPUT HELPERS
   ========================================================= */

function getInputValue(id) {

    const element = $(id);

    if (!element) {
        return null;
    }

    return element.value;

}


function getNumberInput(
    id,
    fallback
) {

    const value =
        getInputValue(id);

    const number =
        Number(value);


    return Number.isFinite(number)
        ? number
        : fallback;

}


function getCheckboxValue(id) {

    const element = $(id);

    if (!element) {
        return false;
    }

    return Boolean(
        element.checked
    );

}


/* =========================================================
   READ SETTINGS FROM FORM
   ========================================================= */

function readSettingsFromForm() {

    return {

        /*
         * Backend keeps the entry timeframe.
         * UI intentionally shows only Wave + Tide.
         */
        entry_timeframe: "5m",


        wave_timeframe:
            getInputValue(
                "wave_timeframe"
            ) ||
            DEFAULT_SETTINGS.wave_timeframe,


        tide_timeframe:
            getInputValue(
                "tide_timeframe"
            ) ||
            DEFAULT_SETTINGS.tide_timeframe,


        wave_ema_fast:
            getNumberInput(
                "wave_ema_fast",
                DEFAULT_SETTINGS.wave_ema_fast
            ),


        wave_ema_medium:
            getNumberInput(
                "wave_ema_medium",
                DEFAULT_SETTINGS.wave_ema_medium
            ),


        wave_ema_slow:
            getNumberInput(
                "wave_ema_slow",
                DEFAULT_SETTINGS.wave_ema_slow
            ),


        tide_ema_fast:
            getNumberInput(
                "tide_ema_fast",
                DEFAULT_SETTINGS.tide_ema_fast
            ),


        tide_ema_medium:
            getNumberInput(
                "tide_ema_medium",
                DEFAULT_SETTINGS.tide_ema_medium
            ),


        tide_ema_slow:
            getNumberInput(
                "tide_ema_slow",
                DEFAULT_SETTINGS.tide_ema_slow
            ),


        filter_ema_fast:
            getNumberInput(
                "filter_ema_fast",
                DEFAULT_SETTINGS.filter_ema_fast
            ),


        filter_ema_slow:
            getNumberInput(
                "filter_ema_slow",
                DEFAULT_SETTINGS.filter_ema_slow
            ),


        wave_heikin_ashi:
            getCheckboxValue(
                "wave_heikin_ashi"
            ),


        tide_heikin_ashi:
            getCheckboxValue(
                "tide_heikin_ashi"
            ),


        rsi_period:
            getNumberInput(
                "rsi_period",
                DEFAULT_SETTINGS.rsi_period
            ),


        macd_fast:
            getNumberInput(
                "macd_fast",
                DEFAULT_SETTINGS.macd_fast
            ),


        macd_slow:
            getNumberInput(
                "macd_slow",
                DEFAULT_SETTINGS.macd_slow
            ),


        macd_signal:
            getNumberInput(
                "macd_signal",
                DEFAULT_SETTINGS.macd_signal
            ),


        stochastic_period:
            getNumberInput(
                "stochastic_period",
                DEFAULT_SETTINGS.stochastic_period
            ),


        stochastic_smooth:
            getNumberInput(
                "stochastic_smooth",
                DEFAULT_SETTINGS.stochastic_smooth
            ),


        volume_sma:
            getNumberInput(
                "volume_sma",
                DEFAULT_SETTINGS.volume_sma
            ),


        sr_lookback:
            getNumberInput(
                "sr_lookback",
                DEFAULT_SETTINGS.sr_lookback
            ),


        pivot:
            getNumberInput(
                "pivot",
                DEFAULT_SETTINGS.pivot
            ),


        min_confirmation:
            getNumberInput(
                "min_confirmation",
                DEFAULT_SETTINGS.min_confirmation
            ),


        risk_reward:
            getNumberInput(
                "risk_reward",
                DEFAULT_SETTINGS.risk_reward
            ),


        buy_score:
            getNumberInput(
                "buy_score",
                DEFAULT_SETTINGS.buy_score
            ),


        sell_score:
            getNumberInput(
                "sell_score",
                DEFAULT_SETTINGS.sell_score
            )

    };

}


/* =========================================================
   WRITE SETTINGS TO FORM
   ========================================================= */

function writeSetting(
    id,
    value
) {

    const element = $(id);

    if (!element) {
        return;
    }


    if (
        element.type === "checkbox"
    ) {

        element.checked =
            Boolean(value);

        return;

    }


    if (
        value !== null &&
        value !== undefined
    ) {

        element.value =
            value;

    }

}


/* =========================================================
   APPLY SETTINGS TO FORM
   ========================================================= */

function applySettingsToForm(
    settings
) {

    if (!settings) {
        return;
    }


    const merged = {

        ...DEFAULT_SETTINGS,

        ...settings

    };


    writeSetting(
        "wave_timeframe",
        merged.wave_timeframe
    );


    writeSetting(
        "tide_timeframe",
        merged.tide_timeframe
    );


    writeSetting(
        "wave_ema_fast",
        merged.wave_ema_fast
    );


    writeSetting(
        "wave_ema_medium",
        merged.wave_ema_medium
    );


    writeSetting(
        "wave_ema_slow",
        merged.wave_ema_slow
    );


    writeSetting(
        "tide_ema_fast",
        merged.tide_ema_fast
    );


    writeSetting(
        "tide_ema_medium",
        merged.tide_ema_medium
    );


    writeSetting(
        "tide_ema_slow",
        merged.tide_ema_slow
    );


    writeSetting(
        "filter_ema_fast",
        merged.filter_ema_fast
    );


    writeSetting(
        "filter_ema_slow",
        merged.filter_ema_slow
    );


    writeSetting(
        "wave_heikin_ashi",
        merged.wave_heikin_ashi
    );


    writeSetting(
        "tide_heikin_ashi",
        merged.tide_heikin_ashi
    );


    writeSetting(
        "rsi_period",
        merged.rsi_period
    );


    writeSetting(
        "macd_fast",
        merged.macd_fast
    );


    writeSetting(
        "macd_slow",
        merged.macd_slow
    );


    writeSetting(
        "macd_signal",
        merged.macd_signal
    );


    writeSetting(
        "stochastic_period",
        merged.stochastic_period
    );


    writeSetting(
        "stochastic_smooth",
        merged.stochastic_smooth
    );


    writeSetting(
        "volume_sma",
        merged.volume_sma
    );


    writeSetting(
        "sr_lookback",
        merged.sr_lookback
    );


    writeSetting(
        "pivot",
        merged.pivot
    );


    writeSetting(
        "min_confirmation",
        merged.min_confirmation
    );


    writeSetting(
        "risk_reward",
        merged.risk_reward
    );


    writeSetting(
        "buy_score",
        merged.buy_score
    );


    writeSetting(
        "sell_score",
        merged.sell_score
    );


    STATE.settings =
        merged;


    updateActiveStrategy(
        merged
    );

}


/* =========================================================
   LOAD SETTINGS FROM SERVER
   ========================================================= */

async function loadSettings() {

    try {

        const data =
            await fetchJSON(
                API.settings
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


        if (
            settings &&
            typeof settings === "object"
        ) {

            applySettingsToForm(
                settings
            );

        }

    } catch (error) {

        console.warn(
            "Settings load failed:",
            error
        );

        applySettingsToForm(
            DEFAULT_SETTINGS
        );

    }

}


/* =========================================================
   APPLY SETTINGS TO SERVER
   ========================================================= */

async function saveSettings() {

    if (STATE.isApplyingSettings) {
        return;
    }


    const button =
        $("applySettings");


    STATE.isApplyingSettings =
        true;


    if (button) {

        button.disabled = true;

        button.classList.add(
            "loading"
        );

        button.textContent =
            "Applying...";

    }


    clearError();


    try {

        const settings =
            readSettingsFromForm();


        validateSettings(
            settings
        );


        const data =
            await fetchJSON(
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


        const serverSettings =
            data &&
            data.settings
                ? data.settings
                : settings;


        applySettingsToForm(
            serverSettings
        );


        showToast(
            "Strategy settings applied successfully.",
            "success"
        );


        /*
         * Refresh scanner after strategy change.
         */
        setTimeout(
            loadScanner,
            250
        );


    } catch (error) {

        console.error(
            "Settings error:",
            error
        );


        showError(
            `Settings error: ${error.message}`
        );


        showToast(
            "Could not apply settings.",
            "error"
        );

    } finally {

        STATE.isApplyingSettings =
            false;


        if (button) {

            button.disabled = false;

            button.classList.remove(
                "loading"
            );

            button.textContent =
                "✓ Apply Settings";

        }

    }

}


/* =========================================================
   VALIDATE SETTINGS
   ========================================================= */

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

        if (
            !Number.isFinite(
                Number(settings[field])
            ) ||
            Number(settings[field]) <= 0
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
            "BUY score must be between 1 and 100."
        );

    }


    if (
        settings.sell_score < 1 ||
        settings.sell_score > 100
    ) {

        throw new Error(
            "SELL score must be between 1 and 100."
        );

    }

}


/* =========================================================
   RESET SETTINGS
   ========================================================= */

async function resetSettings() {

    if (STATE.isResetting) {
        return;
    }


    STATE.isResetting =
        true;


    const button =
        $("resetSettings");


    if (button) {

        button.disabled = true;

        button.textContent =
            "Resetting...";

    }


    try {

        /*
         * First restore the UI immediately.
         */
        applySettingsToForm(
            DEFAULT_SETTINGS
        );


        /*
         * Then try to restore backend defaults.
         */
        try {

            await fetchJSON(
                API.reset,
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

        } catch (resetError) {

            console.warn(
                "Backend reset endpoint unavailable:",
                resetError
            );


            /*
             * Some backend versions expect
             * settings POST instead of /api/reset.
             */
            await fetchJSON(
                API.settings,
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

        }


        showToast(
            "Settings reset to default.",
            "success"
        );


        setTimeout(
            loadScanner,
            250
        );


    } catch (error) {

        console.error(
            "Reset error:",
            error
        );


        showError(
            `Reset error: ${error.message}`
        );


        showToast(
            "Could not reset settings.",
            "error"
        );

    } finally {

        STATE.isResetting =
            false;


        if (button) {

            button.disabled = false;

            button.textContent =
                "↻ Reset";

        }

    }

}


/* =========================================================
   ACTIVE STRATEGY DISPLAY
   ========================================================= */

function updateActiveStrategy(
    settings
) {

    if (!settings) {
        return;
    }


    const waveText =
        formatTimeframe(
            settings.wave_timeframe
        );


    const tideText =
        formatTimeframe(
            settings.tide_timeframe
        );


    setText(
        "waveBadge",
        waveText
    );


    setText(
        "tideBadge",
        tideText
    );


    /*
     * Update strategy badge values
     * without depending on fixed positions.
     */
    const badges =
        document.querySelectorAll(
            ".strategy-badge strong"
        );


    if (badges.length >= 7) {

        badges[0].textContent =
            waveText;

        badges[1].textContent =
            tideText;

        badges[2].textContent =
            `${settings.wave_ema_fast} / ${settings.wave_ema_medium} / ${settings.wave_ema_slow}`;

        badges[3].textContent =
            `${settings.tide_ema_fast} / ${settings.tide_ema_medium} / ${settings.tide_ema_slow}`;

        badges[4].textContent =
            `${settings.filter_ema_fast} / ${settings.filter_ema_slow}`;

        badges[5].textContent =
            `1 : ${settings.risk_reward}`;

        badges[6].textContent =
            (
                settings.wave_heikin_ashi ||
                settings.tide_heikin_ashi
            )
                ? "Heikin Ashi"
                : "Disabled";

    }

}


/* =========================================================
   TIMEFRAME FORMAT
   ========================================================= */

function formatTimeframe(
    value
) {

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


    return (
        map[value] ||
        safeText(value)
    );

}


/* =========================================================
   STATUS
   ========================================================= */

async function loadStatus() {

    try {

        const data =
            await fetchJSON(
                API.status
            );


        STATE.status =
            data;


        updateStatusUI(
            data
        );


        clearError();


    } catch (error) {

        console.error(
            "Status error:",
            error
        );


        setConnectionStatus(
            false,
            "Connection Error"
        );

    }

}


/* =========================================================
   UPDATE STATUS UI
   ========================================================= */

function updateStatusUI(
    data
) {

    if (!data) {
        return;
    }


    const authenticated =
        Boolean(
            data.authenticated
        );


    const instrumentsLoaded =
        Boolean(
            data.instruments_loaded
        );


    const marketStatus =
        safeText(
            data.market_status,
            "UNKNOWN"
        );


    setText(
        "fnoStocks",
        data.fno_stock_count ??
        data.fno_stocks ??
        0
    );


    setText(
        "connectionCard",
        authenticated
            ? "Live"
            : "Offline"
    );


    /*
     * Connection pill.
     */
    if (authenticated) {

        setConnectionStatus(
            true,
            "Connected"
        );

    } else {

        setConnectionStatus(
            false,
            "Waiting"
        );

    }


    /*
     * Market status.
     */
    const marketElement =
        $("marketStatus");


    if (marketElement) {

        marketElement.classList.remove(
            "market-open",
            "market-closed",
            "market-error"
        );


        if (
            marketStatus === "OPEN" ||
            marketStatus === "LIVE"
        ) {

            marketElement.classList.add(
                "market-open"
            );

            marketElement.textContent =
                "● Market Open";

        } else if (
            marketStatus === "ERROR"
        ) {

            marketElement.classList.add(
                "market-error"
            );

            marketElement.textContent =
                "● Data Error";

        } else {

            marketElement.classList.add(
                "market-closed"
            );

            marketElement.textContent =
                "● Market Data";

        }

    }


    /*
     * History.
     */
    const loaded =
        numberValue(
            data.history_loaded,
            0
        );


    const failed =
        numberValue(
            data.history_failed,
            0
        );


    const total =
        numberValue(
            data.fno_stock_count,
            0
        );


    const progress =
        total > 0
            ? Math.min(
                100,
                Math.round(
                    (
                        loaded /
                        total
                    ) * 100
                )
            )
            : 0;


    setText(
        "historyProgress",
        total > 0
            ? `${loaded} / ${total}`
            : "Waiting..."
    );


    const progressBar =
        $("historyProgressBar");


    if (progressBar) {

        progressBar.style.width =
            `${progress}%`;

    }


    if (
        failed > 0 &&
        data.last_error
    ) {

        /*
         * Don't display errors permanently
         * if scanner is otherwise working.
         */
        console.warn(
            "Scanner backend:",
            data.last_error
        );

    }


    setText(
        "marketLastUpdate",
        formatDateTime(
            data.last_history_update ||
            data.last_ltp_update
        )
    );


    setText(
        "scannerLastUpdate",
        formatDateTime(
            data.last_ltp_update ||
            data.last_history_update
        )
    );


    /*
     * If backend gives an error, show it.
     */
    if (
        data.last_error &&
        !authenticated
    ) {

        showError(
            data.last_error
        );

    }


    /*
     * instruments_loaded isn't an error.
     */
    void instrumentsLoaded;

}


/* =========================================================
   CONNECTION STATUS
   ========================================================= */

function setConnectionStatus(
    connected,
    text
) {

    const pill =
        $("connectionStatus");

    const textElement =
        $("connectionText");


    if (!pill) {
        return;
    }


    pill.classList.remove(
        "status-connected",
        "status-error",
        "status-loading"
    );


    if (connected) {

        pill.classList.add(
            "status-connected"
        );

    } else {

        pill.classList.add(
            "status-error"
        );

    }


    if (textElement) {

        textElement.textContent =
            text;

    }

}


/* =========================================================
   SCANNER
   ========================================================= */

async function loadScanner() {

    if (STATE.isLoadingScanner) {
        return;
    }


    STATE.isLoadingScanner =
        true;


    try {

        const data =
            await fetchJSON(
                API.scanner
            );


        const rows =
            extractScannerRows(
                data
            );


        STATE.scannerData =
            rows;


        STATE.lastScannerUpdate =
            new Date();


        updateScannerCounts(
            rows
        );


        applyScannerFilters();


        setText(
            "scannerLastUpdate",
            formatDateTime(
                STATE.lastScannerUpdate
            )
        );


    } catch (error) {

        console.error(
            "Scanner error:",
            error
        );


        /*
         * Don't destroy a previously loaded table
         * because one polling request failed.
         */
        if (
            STATE.scannerData.length === 0
        ) {

            renderEmptyState(
                "Waiting for scanner data..."
            );

        }

    } finally {

        STATE.isLoadingScanner =
            false;

    }

}


/* =========================================================
   EXTRACT SCANNER ROWS
   ========================================================= */

function extractScannerRows(
    data
) {

    if (Array.isArray(data)) {
        return data;
    }


    if (
        data &&
        Array.isArray(data.data)
    ) {

        return data.data;

    }


    if (
        data &&
        Array.isArray(data.results)
    ) {

        return data.results;

    }


    if (
        data &&
        Array.isArray(data.scanner)
    ) {

        return data.scanner;

    }


    if (
        data &&
        Array.isArray(data.rows)
    ) {

        return data.rows;

    }


    if (
        data &&
        data.data &&
        typeof data.data === "object"
    ) {

        return objectToRows(
            data.data
        );

    }


    if (
        data &&
        typeof data === "object"
    ) {

        /*
         * Some scanner versions return:
         *
         * {
         *   "RELIANCE": {...},
         *   "TCS": {...}
         * }
         */
        const keys =
            Object.keys(data);


        const possibleRows =
            keys
                .filter(
                    key =>
                        data[key] &&
                        typeof data[key] === "object" &&
                        !Array.isArray(data[key])
                )
                .map(
                    key => ({
                        symbol: key,
                        ...data[key]
                    })
                );


        if (
            possibleRows.length > 0
        ) {

            return possibleRows;

        }

    }


    return [];

}


/* =========================================================
   OBJECT TO ROWS
   ========================================================= */

function objectToRows(
    object
) {

    return Object.entries(
        object || {}
    ).map(
        ([symbol, value]) => {

            if (
                value &&
                typeof value === "object"
            ) {

                return {

                    symbol,

                    ...value

                };

            }


            return {

                symbol,

                value

            };

        }
    );

}


/* =========================================================
   SCANNER FILTERS
   ========================================================= */

function initScannerFilters() {

    const signalFilter =
        $("signalFilter");

    const stockSearch =
        $("stockSearch");


    if (signalFilter) {

        signalFilter.addEventListener(
            "change",
            applyScannerFilters
        );

    }


    if (stockSearch) {

        stockSearch.addEventListener(
            "input",
            applyScannerFilters
        );

    }

}


/* =========================================================
   APPLY FILTERS
   ========================================================= */

function applyScannerFilters() {

    const signalFilter =
        $("signalFilter");


    const stockSearch =
        $("stockSearch");


    const signal =
        signalFilter
            ? String(
                signalFilter.value
            ).toUpperCase()
            : "ALL";


    const search =
        stockSearch
            ? String(
                stockSearch.value
            )
                .trim()
                .toUpperCase()
            : "";


    STATE.filteredData =
        STATE.scannerData.filter(
            row => {

                const rowSignal =
                    getSignal(row);


                const symbol =
                    getSymbol(row)
                        .toUpperCase();


                const signalMatches =
                    signal === "ALL" ||
                    rowSignal === signal;


                const searchMatches =
                    !search ||
                    symbol.includes(search);


                return (
                    signalMatches &&
                    searchMatches
                );

            }
        );


    renderScanner(
        STATE.filteredData
    );

}


/* =========================================================
   SCANNER COUNTS
   ========================================================= */

function updateScannerCounts(
    rows
) {

    let buy = 0;

    let sell = 0;

    let wait = 0;


    rows.forEach(
        row => {

            const signal =
                getSignal(row);


            if (signal === "BUY") {

                buy++;

            } else if (
                signal === "SELL"
            ) {

                sell++;

            } else {

                wait++;

            }

        }
    );


    setText(
        "buyCount",
        buy
    );


    setText(
        "sellCount",
        sell
    );


    setText(
        "waitCount",
        wait
    );

}


/* =========================================================
   GET SYMBOL
   ========================================================= */

function getSymbol(row) {

    return safeText(

        row.symbol ??
        row.stock ??
        row.stock_symbol ??
        row.trading_symbol ??
        row.groww_symbol ??
        row.name,

        "UNKNOWN"

    );

}


/* =========================================================
   GET SIGNAL
   ========================================================= */

function getSignal(row) {

    const value =
        row.signal ??
        row.action ??
        row.side ??
        row.direction ??
        row.recommendation ??
        "WAIT";


    const signal =
        String(value)
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
   GET WAVE
   ========================================================= */

function getWave(row) {

    return safeText(

        row.wave ??
        row.wave_signal ??
        row.wave_direction ??
        row.wave_trend ??
        "-"

    );

}


/* =========================================================
   GET TIDE
   ========================================================= */

function getTide(row) {

    return safeText(

        row.tide ??
        row.tide_signal ??
        row.tide_direction ??
        row.tide_trend ??
        "-"

    );

}


/* =========================================================
   GET FILTER
   ========================================================= */

function getFilter(row) {

    return safeText(

        row.filter ??
        row.trend_filter ??
        row.ema_filter ??
        row.filter_signal ??
        "-"

    );

}


/* =========================================================
   GET VALUE
   ========================================================= */

function firstValue(
    row,
    keys,
    fallback = "-"
) {

    for (
        const key of keys
    ) {

        if (
            row[key] !== undefined &&
            row[key] !== null &&
            row[key] !== ""
        ) {

            return row[key];

        }

    }


    return fallback;

}


/* =========================================================
   FORMAT NUMBER
   ========================================================= */

function formatNumber(
    value,
    decimals = 2
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return "-";

    }


    const number =
        Number(value);


    if (!Number.isFinite(number)) {

        return safeText(
            value
        );

    }


    return number.toLocaleString(
        "en-IN",
        {

            minimumFractionDigits:
                decimals,

            maximumFractionDigits:
                decimals

        }
    );

}


/* =========================================================
   FORMAT PRICE
   ========================================================= */

function formatPrice(
    value
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return "-";

    }


    const number =
        Number(value);


    if (!Number.isFinite(number)) {

        return safeText(
            value
        );

    }


    return number.toLocaleString(
        "en-IN",
        {

            minimumFractionDigits:
                2,

            maximumFractionDigits:
                2

        }
    );

}


/* =========================================================
   FORMAT PERCENT
   ========================================================= */

function formatPercent(
    value
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return "-";

    }


    const number =
        Number(value);


    if (!Number.isFinite(number)) {

        return safeText(
            value
        );

    }


    const sign =
        number > 0
            ? "+"
            : "";


    return (
        sign +
        number.toFixed(2) +
        "%"
    );

}


/* =========================================================
   FORMAT DATE
   ========================================================= */

function formatDateTime(
    value
) {

    if (!value) {

        return "Waiting for update...";

    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {

        return safeText(
            value
        );

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


/* =========================================================
   RENDER SCANNER
   ========================================================= */

function renderScanner(
    rows
) {

    const body =
        $("scannerBody");


    if (!body) {
        return;
    }


    if (
        !rows ||
        rows.length === 0
    ) {

        renderEmptyState(
            STATE.scannerData.length > 0
                ? "No stocks match your filter."
                : "Waiting for scanner data..."
        );

        return;

    }


    /*
     * Sort:
     *
     * BUY
     * SELL
     * WAIT
     *
     * then score.
     */
    const sorted =
        [...rows].sort(
            (a, b) => {

                const priority = {

                    BUY: 0,

                    SELL: 1,

                    WAIT: 2

                };


                const signalA =
                    getSignal(a);

                const signalB =
                    getSignal(b);


                if (
                    priority[signalA] !==
                    priority[signalB]
                ) {

                    return (
                        priority[signalA] -
                        priority[signalB]
                    );

                }


                const scoreA =
                    Number(
                        firstValue(
                            a,
                            [
                                "score",
                                "signal_score",
                                "total_score"
                            ],
                            0
                        )
                    );


                const scoreB =
                    Number(
                        firstValue(
                            b,
                            [
                                "score",
                                "signal_score",
                                "total_score"
                            ],
                            0
                        )
                    );


                return scoreB - scoreA;

            }
        );


    body.innerHTML =
        sorted
            .map(
                (row, index) =>
                    createScannerRow(
                        row,
                        index
                    )
            )
            .join("");

}


/* =========================================================
   CREATE SCANNER ROW
   ========================================================= */

function createScannerRow(
    row,
    index
) {

    const signal =
        getSignal(row);


    const symbol =
        getSymbol(row);


    const ltp =
        firstValue(
            row,
            [
                "ltp",
                "price",
                "last_price",
                "lastPrice",
                "close"
            ]
        );


    const change =
        firstValue(
            row,
            [
                "change_percent",
                "change_pct",
                "change",
                "percent_change",
                "day_change"
            ]
        );


    const wave =
        getWave(row);


    const tide =
        getTide(row);


    const filter =
        getFilter(row);


    const ema =
        firstValue(
            row,
            [
                "ema",
                "ema_signal",
                "ema_status"
            ]
        );


    const rsi =
        firstValue(
            row,
            [
                "rsi",
                "rsi_value"
            ]
        );


    const macd =
        firstValue(
            row,
            [
                "macd",
                "macd_signal",
                "macd_status"
            ]
        );


    const volume =
        firstValue(
            row,
            [
                "volume",
                "volume_ratio",
                "volume_status"
            ]
        );


    const support =
        firstValue(
            row,
            [
                "support",
                "support_level",
                "nearest_support"
            ]
        );


    const resistance =
        firstValue(
            row,
            [
                "resistance",
                "resistance_level",
                "nearest_resistance"
            ]
        );


    const score =
        firstValue(
            row,
            [
                "score",
                "signal_score",
                "total_score"
            ]
        );


    const sl =
        firstValue(
            row,
            [
                "sl",
                "stop_loss",
                "stoploss"
            ]
        );


    const target =
        firstValue(
            row,
            [
                "target",
                "target_price",
                "take_profit"
            ]
        );


    const rr =
        firstValue(
            row,
            [
                "rr",
                "risk_reward",
                "riskReward"
            ]
        );


    const signalClass =
        signal === "BUY"
            ? "buy-badge"
            : signal === "SELL"
                ? "sell-badge"
                : "wait-badge";


    const changeNumber =
        Number(change);


    const changeClass =
        Number.isFinite(changeNumber)
            ? (
                changeNumber > 0
                    ? "signal-buy"
                    : changeNumber < 0
                        ? "signal-sell"
                        : ""
            )
            : "";


    return `

        <tr>

            <td>
                ${index + 1}
            </td>

            <td>
                <strong>
                    ${escapeHTML(symbol)}
                </strong>
            </td>

            <td>
                ${formatPrice(ltp)}
            </td>

            <td class="${changeClass}">
                ${formatPercent(change)}
            </td>

            <td>
                ${escapeHTML(wave)}
            </td>

            <td>
                ${escapeHTML(tide)}
            </td>

            <td>
                ${escapeHTML(filter)}
            </td>

            <td>
                ${escapeHTML(
                    formatGenericValue(ema)
                )}
            </td>

            <td>
                ${formatGenericValue(rsi)}
            </td>

            <td>
                ${escapeHTML(
                    formatGenericValue(macd)
                )}
            </td>

            <td>
                ${escapeHTML(
                    formatGenericValue(volume)
                )}
            </td>

            <td>
                ${formatPrice(support)}
            </td>

            <td>
                ${formatPrice(resistance)}
            </td>

            <td>
                <strong>
                    ${formatGenericValue(score)}
                </strong>
            </td>

            <td>

                <span
                    class="${signalClass}"
                >
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
                ${formatGenericValue(rr)}
            </td>

        </tr>

    `;

}


/* =========================================================
   GENERIC VALUE FORMAT
   ========================================================= */

function formatGenericValue(
    value
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {

        return "-";

    }


    if (
        typeof value === "number"
    ) {

        return Number.isInteger(value)
            ? String(value)
            : value.toFixed(2);

    }


    return String(value);

}


/* =========================================================
   ESCAPE HTML
   ========================================================= */

function escapeHTML(
    value
) {

    return String(value)
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );

}


/* =========================================================
   EMPTY TABLE
   ========================================================= */

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
                    ${escapeHTML(message)}
                </strong>

                <span>
                    Waiting for NSE market data
                </span>

            </td>

        </tr>

    `;

}


/* =========================================================
   RESET FILTERS
   ========================================================= */

function resetScannerFilters() {

    const signalFilter =
        $("signalFilter");

    const stockSearch =
        $("stockSearch");


    if (signalFilter) {

        signalFilter.value =
            "ALL";

    }


    if (stockSearch) {

        stockSearch.value =
            "";

    }


    applyScannerFilters();

}


/* =========================================================
   GROW TEST
   ========================================================= */

async function runGrowwTest() {

    try {

        const data =
            await fetchJSON(
                API.growwTest
            );


        console.log(
            "Groww API test:",
            data
        );


        return data;

    } catch (error) {

        console.error(
            "Groww test failed:",
            error
        );


        return null;

    }

}


/* =========================================================
   EVENT LISTENERS
   ========================================================= */

function initEvents() {

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


    initScannerFilters();


    /*
     * Enter key inside settings.
     */
    const settingsContent =
        $("settingsContent");


    if (settingsContent) {

        settingsContent.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter" &&
                    event.target.tagName === "INPUT"
                ) {

                    /*
                     * Don't submit automatically.
                     */
                    event.preventDefault();

                }

            }
        );

    }

}


/* =========================================================
   POLLING
   ========================================================= */

let statusTimer = null;

let scannerTimer = null;


function startPolling() {

    clearInterval(
        statusTimer
    );

    clearInterval(
        scannerTimer
    );


    statusTimer =
        setInterval(
            loadStatus,
            STATUS_INTERVAL
        );


    scannerTimer =
        setInterval(
            loadScanner,
            POLL_INTERVAL
        );

}


/* =========================================================
   INITIALIZE
   ========================================================= */

async function initializeApp() {

    console.log(
        "Indian F&O Scanner starting..."
    );


    initSettingsToggle();

    initEvents();


    /*
     * Load saved settings first.
     */
    await loadSettings();


    /*
     * Then get backend status.
     */
    await loadStatus();


    /*
     * Load scanner.
     */
    await loadScanner();


    /*
     * Continue live updates.
     */
    startPolling();


    console.log(
        "Indian F&O Scanner ready."
    );

}


/* =========================================================
   PAGE LOAD
   ========================================================= */

if (
    document.readyState === "loading"
) {

    document.addEventListener(
        "DOMContentLoaded",
        initializeApp
    );

} else {

    initializeApp();

}


/* =========================================================
   GLOBAL DEBUG HELPERS
   ========================================================= */

window.IndianFNOScanner = {

    state: STATE,

    reload: async function () {

        await loadStatus();

        await loadScanner();

    },

    reloadSettings:
        loadSettings,

    applySettings:
        saveSettings,

    resetSettings:
        resetSettings,

    growwTest:
        runGrowwTest

};
