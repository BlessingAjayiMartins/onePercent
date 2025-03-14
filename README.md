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
```bash
python trader.py
```

## Strategy
The bot implements a simple 1% profit target strategy:
1. Monitors real-time price data
2. Places buy orders when conditions are favorable
3. Sets take-profit orders at 1% above entry price
4. Includes basic risk management with stop-loss orders
