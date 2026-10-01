Indian F&O Intraday Scanner
Groww-powered NSE F&O stock scanner using the same strategy concept as the previous Delta scanner.
Deployment
Upload this project to GitHub.
Create a Render Web Service from the repository.
Build command:
`pip install -r requirements.txt`
Start command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`
Add Render environment variable:
`GROWW_ACCESS_TOKEN`
Do not commit credentials to GitHub.
Current scope
NSE stocks whose underlying has an NSE F&O instrument.
Groww live feed.
Configurable Wave/Tide/Entry timeframes.
Configurable EMA, RSI, MACD, Stochastic, volume, S/R and scoring thresholds.
Dashboard API and UI.
The strategy engine is structured so full candle aggregation and indicator calculations can be extended without changing the Groww data layer.

Telegram signals
Telegram is controlled by the Telegram Signals switch in the web dashboard.
OFF (default): the scanner continues running, but sends no Telegram alerts.
ON: Telegram alerts are sent only for qualifying BUY/SELL signals.
The same BUY/SELL state is not repeatedly spammed.
Required Render environment variables:
`TELEGRAM_BOT_TOKEN`
`TELEGRAM_CHAT_ID`
Never put these credentials in GitHub.

Groww authentication
For the current deployment, use the Groww API Key + API Secret flow.
Render Environment Variables:
`GROWW_API_KEY`
`GROWW_API_SECRET`
The application calls `GrowwAPI.get_access_token(api_key=..., secret=...)` at startup and keeps the resulting access token in memory. Do not commit either credential to GitHub or share them in chat.
Telegram is disabled unless explicitly enabled in the dashboard and configured separately.
