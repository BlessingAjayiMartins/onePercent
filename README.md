# OnePercent Trading Bot

An automated trading bot that aims to make 1% profit per trade using Alpaca API.

## Setup
1. Create an Alpaca account at https://alpaca.markets/
2. Create a `.env` file with your Alpaca API credentials:
```
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret
ALPACA_PAPER=True  # Set to False for live trading
```

## Installation
```bash
pip install -r requirements.txt
```

## Usage

### Regular Trading Mode
```bash
python trader.py
```
You'll be prompted to enter a stock symbol and investment amount.

### View Trade Summary
To view a summary of trades for a specific symbol:
```bash
python trader.py --summary AAPL
```
Replace AAPL with your desired symbol. This will check for completed trades in the past 7 days and display performance metrics.

### Generate Test Summary
For testing the trade summary functionality without actual trades:
```bash
python trader.py --force-summary AAPL
```
This creates sample trade data with a profitable trade and generates summary files.

## Strategy
The bot implements a simple 1% profit target strategy:
1. Monitors real-time price data
2. Places buy orders when conditions are favorable
3. Sets take-profit orders at 1% above entry price
4. Includes basic risk management with stop-loss orders

## Trade Tracking
The bot automatically tracks all trades and calculates performance metrics:
- Win/loss ratio
- Total and average profit/loss
- Profit factor
- Individual trade details

Trade summaries are saved in the `trades` directory in both JSON and CSV formats:
- `{symbol}_trades_{timestamp}.json` - Detailed trade data for each batch of trades
- `{symbol}_summary.csv` - Cumulative record of all trades for easy spreadsheet import
