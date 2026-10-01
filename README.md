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
