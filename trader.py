import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    OrderRequest, TakeProfitRequest, StopLossRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, OrderClass
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
        self.order_states = {}

    def get_current_price(self):
        """Get the current price of the symbol."""
        try:
            # Use proper datetime objects
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(minutes=10)  # Get data for the last 10 minutes
            
            logging.info(f"Getting current price for {self.symbol}")
            
            request = StockBarsRequest(
                symbol_or_symbols=[self.symbol],
                timeframe=TimeFrame.Minute,
                start=start_dt,
                end=end_dt
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
            filled_order = trading_client.get_order_by_id(order.id)
            while filled_order.status != 'filled':
                time.sleep(1)
                filled_order = trading_client.get_order_by_id(order.id)

            self.entry_price = float(filled_order.filled_avg_price)
            self.position = filled_order
            
            logging.info(f"Buy order filled at {self.entry_price}")
            return True

        except Exception as e:
            logging.error(f"Error placing buy order: {e}")
            return False

    def place_sell_orders(self):
        """Smart order placement with quantity validation"""
        try:
            if not self.position:
                return False

            # Get REAL available shares
            position = trading_client.get_open_position(self.symbol)
            available_qty = int(position.qty_available)
            
            if available_qty <= 0:
                logging.error("No shares available for trading")
                return False

            # Calculate prices
            target_price = round(float(position.avg_entry_price) * 1.01, 2)
            stop_price = round(float(position.avg_entry_price) * 0.99, 2)

            # Place bracket order
            bracket_order = OrderRequest(
                symbol=self.symbol,
                qty=str(available_qty),
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                limit_price=str(target_price),
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=str(target_price)),
                stop_loss=StopLossRequest(stop_price=str(stop_price))
            )
            
            trading_client.submit_order(bracket_order)
            logging.info(f"✅ Bracket order placed for {available_qty} shares")
            return True

        except Exception as e:
            logging.error(f"Order placement failed: {str(e)[:200]}")
            return False

    def cancel_existing_orders(self):
        """Cancel orders with retries and verification"""
        try:
            # First pass cancellation
            orders = trading_client.get_orders(status='open')
            for order in orders:
                if order.symbol == self.symbol:
                    trading_client.cancel_order_by_id(order.id)
                    logging.info(f"Initiated cancellation for order {order.id}")

            # Verify cancellation
            retries = 0
            while retries < 3:
                remaining_orders = [
                    o for o in trading_client.get_orders(status='open') 
                    if o.symbol == self.symbol
                ]
                
                if not remaining_orders:
                    break
                    
                for order in remaining_orders:
                    trading_client.cancel_order_by_id(order.id)
                    logging.warning(f"Retrying cancellation for {order.id}")
                
                time.sleep(1)
                retries += 1

            # Final check
            if remaining_orders:
                logging.error(f"Failed to cancel orders: {[o.id for o in remaining_orders]}")
                return False
                
            return True

        except Exception as e:
            logging.error(f"Order cancellation error: {str(e)[:200]}")
            return False

    def check_and_handle_existing_position(self):
        """Check for existing positions and create exit orders if needed."""
        try:
            # Get all positions
            positions = trading_client.get_all_positions()
            position = next((p for p in positions if p.symbol == self.symbol), None)
            
            if position:
                logging.info(f"Found existing position for {self.symbol}: {position.qty} shares at avg price {position.avg_entry_price}")
                
                # Check if there are any existing orders for this symbol
                orders = trading_client.get_orders()
                has_tp_order = any(o.symbol == self.symbol and o.side == 'sell' and o.type == 'limit' for o in orders)
                has_sl_order = any(o.symbol == self.symbol and o.side == 'sell' and o.type == 'stop' for o in orders)
                
                # Set up the position and entry price
                self.position = position
                self.entry_price = float(position.avg_entry_price)
                
                if not has_tp_order or not has_sl_order:
                    logging.info(f"Missing exit orders for existing position. Creating exit orders...")
                    # Create exit orders
                    self.place_sell_orders()
                else:
                    logging.info(f"Exit orders already exist for {self.symbol}. Continuing monitoring...")
                
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking existing positions: {e}")
            return False

    def check_market_conditions(self):
        """
        Check if market conditions are favorable for trading.
        This is a simple implementation - you can enhance it with your own criteria.
        """
        try:
            # Get recent price data
        # Use datetime objects properly formatted for Alpaca API
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=120)  # Get data for the last 24 hours
        
            logging.info(f"Requesting bars for {self.symbol} from {start_dt.isoformat()} to {end_dt.isoformat()}")
        
            request = StockBarsRequest(
                symbol_or_symbols=[self.symbol],
                timeframe=TimeFrame.Hour,
                start=start_dt,
                end=end_dt
            )
            
            bars = data_client.get_stock_bars(request)
            
            # Simple volume check
            recent_volume = bars[self.symbol][-1].volume
            avg_volume = sum(bar.volume for bar in bars[self.symbol]) / len(bars[self.symbol])
            
            return recent_volume > avg_volume * 0.8  # 80% of average volume
        
        except Exception as e:
            logging.error(f"Error checking market conditions: {e}")
            return False

    def monitor_orders(self):
        """Track order state changes with expiry alerts"""
        try:
            orders = trading_client.get_orders()
            for order in orders:
                if order.symbol == self.symbol:
                    status = order.status.value
                    if status != self.order_states.get(order.id):
                        logging.info(f"Order {order.id} changed to {status}")
                        self.order_states[order.id] = status
                    
                    # Alert on stale orders
                    if (datetime.now() - order.created_at).seconds > 3600:
                        logging.warning(f"Stale order {order.id} ({status}) older than 1 hour")
        except Exception as e:
            logging.error(f"Order monitoring failed: {str(e)[:200]}")

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
                if self.check_and_handle_existing_position():
                    logging.info("Existing position found. Monitoring...")
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

                self.monitor_orders()

                time.sleep(60)  # Wait for 1 minute before next iteration

            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(60)

    def _get_position_quantity(self):
        return self.position.qty if hasattr(self.position, 'qty') else self.position.filled_qty

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
