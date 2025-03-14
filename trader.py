import os
import time
from datetime import datetime
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Initialize Alpaca clients
trading_client = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_API_SECRET"),
    paper=os.getenv("ALPACA_PAPER", "True").lower() == "true"
)

data_client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_API_SECRET")
)

class OnePercentTrader:
    def __init__(self, symbol, investment_amount=10000):
        self.symbol = symbol
        self.investment_amount = investment_amount
        self.position = None
        self.entry_price = None
        self.target_profit_pct = 0.01  # 1%
        self.stop_loss_pct = 0.005     # 0.5%

    def get_current_price(self):
        """Get the current price of the symbol."""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=[self.symbol],
                timeframe=TimeFrame.Minute,
                start=datetime.now().date()
            )
            bars = data_client.get_stock_bars(request)
            return bars[self.symbol][-1].close
        except Exception as e:
            logging.error(f"Error getting current price: {e}")
            return None

    def place_buy_order(self):
        """Place a market buy order."""
        try:
            current_price = self.get_current_price()
            if not current_price:
                return False

            # Calculate quantity based on investment amount
            qty = self.investment_amount // current_price

            # Place market buy order
            order_details = MarketOrderRequest(
                symbol=self.symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            order = trading_client.submit_order(order_details)
            
            # Wait for order to fill
            filled_order = trading_client.get_order(order.id)
            while filled_order.status != 'filled':
                time.sleep(1)
                filled_order = trading_client.get_order(order.id)

            self.entry_price = float(filled_order.filled_avg_price)
            self.position = filled_order
            
            logging.info(f"Buy order filled at {self.entry_price}")
            return True

        except Exception as e:
            logging.error(f"Error placing buy order: {e}")
            return False

    def place_sell_orders(self):
        """Place take-profit and stop-loss orders."""
        if not self.position or not self.entry_price:
            return False

        try:
            # Calculate target and stop prices
            target_price = self.entry_price * (1 + self.target_profit_pct)
            stop_price = self.entry_price * (1 - self.stop_loss_pct)

            # Place take-profit limit order
            tp_order = LimitOrderRequest(
                symbol=self.symbol,
                qty=self.position.filled_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=target_price
            )
            trading_client.submit_order(tp_order)
            logging.info(f"Take-profit order placed at {target_price}")

            # Place stop-loss order
            sl_order = StopOrderRequest(
                symbol=self.symbol,
                qty=self.position.filled_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                stop_price=stop_price
            )
            trading_client.submit_order(sl_order)
            logging.info(f"Stop-loss order placed at {stop_price}")
            
            return True

        except Exception as e:
            logging.error(f"Error placing sell orders: {e}")
            return False

    def check_market_conditions(self):
        """
        Check if market conditions are favorable for trading.
        This is a simple implementation - you can enhance it with your own criteria.
        """
        try:
            # Get recent price data
            request = StockBarsRequest(
                symbol_or_symbols=[self.symbol],
                timeframe=TimeFrame.Hour,
                start=datetime.now().date()
            )
            bars = data_client.get_stock_bars(request)
            
            # Simple volume check
            recent_volume = bars[self.symbol][-1].volume
            avg_volume = sum(bar.volume for bar in bars[self.symbol]) / len(bars[self.symbol])
            
            return recent_volume > avg_volume * 0.8  # 80% of average volume
        except Exception as e:
            logging.error(f"Error checking market conditions: {e}")
            return False

    def run(self):
        """Main trading loop."""
        logging.info(f"Starting trading bot for {self.symbol}")
        
        while True:
            try:
                # Check if market is open
                clock = trading_client.get_clock()
                if not clock.is_open:
                    logging.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                # Check if we have any existing position
                positions = trading_client.get_all_positions()
                if any(p.symbol == self.symbol for p in positions):
                    logging.info("Position already exists. Monitoring...")
                    time.sleep(60)
                    continue

                # Check market conditions
                if not self.check_market_conditions():
                    logging.info("Market conditions not favorable. Waiting...")
                    time.sleep(60)
                    continue

                # Place buy order
                if self.place_buy_order():
                    # Place take-profit and stop-loss orders
                    self.place_sell_orders()

                time.sleep(60)  # Wait for 1 minute before next iteration

            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write("ALPACA_API_KEY=your_api_key\n")
            f.write("ALPACA_API_SECRET=your_api_secret\n")
            f.write("ALPACA_PAPER=True\n")
        logging.warning("Created .env file. Please fill in your Alpaca API credentials.")
        exit(1)

    symbol = input("Enter the stock symbol to trade (e.g., AAPL): ").upper()
    investment = float(input("Enter the investment amount per trade (default: 10000): ") or 10000)
    
    trader = OnePercentTrader(symbol, investment)
    trader.run()
