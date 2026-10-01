# 🇮🇳 Indian F&O Market Scanner

A live NSE F&O stock scanner powered by Groww API.

## Features

- NSE F&O stocks only
- Live market scanner
- Groww API integration
- Multi-timeframe analysis
- Entry / Wave / Tide timeframes
- EMA 9 / 20 / 50
- EMA 20 / 50 trend filter
- RSI
- MAC
- Stochastic
- Volume analysis
- Support & Resistance
- Confirmation scoring
- BUY / SELL / WAIT signals
- Risk / Stop Loss / Target calculation
- Default 1:2 Risk-Reward
- Live dashboard
- Online deployment with Render

## Default Strategy

### Entry
5 minutes

### Wave
15 minutes

### Tide
1 hour

### EMA
- EMA 9
- EMA 20
- EMA 50

### Trend Filter
- EMA 20
- EMA 50

### RSI
14

### MACD
12 / 26 / 9

### Stochastic
14 / 3

### Volume
20-period SMA

### Support / Resistance
- Lookback: 160 candles
- Pivot: 3

### Signal

Base score: 50

BUY:

- Score >= 70
- Wave direction = BUY
- Tide direction = BUY
- Minimum confirmation = 7

SELL:

- Score <= 30
- Wave direction = SELL
- Tide direction = SELL
- Minimum confirmation = 7

### Risk Reward

Default:

1 : 2

## Deployment

The application is designed to run on Render.

### Required environment variables

```text
GROWW_API_KEY
GROWW_API_SECRET
