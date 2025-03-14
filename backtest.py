import os
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

class OnePercentBacktest:
    def __init__(self, symbol, initial_capital=10000):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.entry_price = None
        self.target_profit_pct = 0.01  # 1%
        self.stop_loss_pct = 0.005     # 0.5%
        self.trades = []
        
        # Initialize Alpaca client
        self.data_client = StockHistoricalDataClient(
            os.getenv("ALPACA_API_KEY"),
            os.getenv("ALPACA_API_SECRET")
        )

    def get_historical_data(self, start_date, end_date):
        """Fetch historical data for the specified period."""
        request = StockBarsRequest(
            symbol_or_symbols=[self.symbol],
            timeframe=TimeFrame.Minute,
            start=start_date,
            end=end_date
        )
        return self.data_client.get_stock_bars(request)

    def run_backtest(self, start_date, end_date):
        """Run backtest over the specified period."""
        # Get historical data
        bars = self.get_historical_data(start_date, end_date)
        df = pd.DataFrame([bar.__dict__ for bar in bars[self.symbol]])
        
        # Reset metrics
        self.capital = self.initial_capital
        self.trades = []
        self.position = None
        
        # Iterate through each bar
        for i in range(len(df)):
            current_bar = df.iloc[i]
            
            if self.position is None:
                # Check for entry conditions (simple volume-based condition)
                if i >= 20:  # Need some bars for volume average
                    avg_volume = df.iloc[i-20:i]['volume'].mean()
                    if current_bar['volume'] > avg_volume * 1.2:  # Volume spike
                        # Enter position
                        self.entry_price = current_bar['close']
                        shares = int(self.capital / self.entry_price)
                        self.position = {
                            'shares': shares,
                            'entry_price': self.entry_price,
                            'entry_time': current_bar['timestamp'],
                            'target_price': self.entry_price * (1 + self.target_profit_pct),
                            'stop_price': self.entry_price * (1 - self.stop_loss_pct)
                        }
            else:
                # Check for exit conditions
                if (current_bar['high'] >= self.position['target_price'] or 
                    current_bar['low'] <= self.position['stop_price']):
                    
                    # Determine exit price
                    if current_bar['high'] >= self.position['target_price']:
                        exit_price = self.position['target_price']
                        exit_type = 'target'
                    else:
                        exit_price = self.position['stop_price']
                        exit_type = 'stop'
                    
                    # Calculate profit/loss
                    pl = (exit_price - self.position['entry_price']) * self.position['shares']
                    self.capital += pl
                    
                    # Record trade
                    self.trades.append({
                        'entry_time': self.position['entry_time'],
                        'exit_time': current_bar['timestamp'],
                        'entry_price': self.position['entry_price'],
                        'exit_price': exit_price,
                        'shares': self.position['shares'],
                        'pl': pl,
                        'exit_type': exit_type
                    })
                    
                    # Reset position
                    self.position = None

    def get_stats(self):
        """Calculate and return backtest statistics."""
        if not self.trades:
            return "No trades executed"
        
        total_trades = len(self.trades)
        profitable_trades = len([t for t in self.trades if t['pl'] > 0])
        total_pl = sum(t['pl'] for t in self.trades)
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        return {
            'Initial Capital': self.initial_capital,
            'Final Capital': self.capital,
            'Total Return': f"{((self.capital - self.initial_capital) / self.initial_capital * 100):.2f}%",
            'Total Trades': total_trades,
            'Profitable Trades': profitable_trades,
            'Win Rate': f"{win_rate * 100:.2f}%",
            'Total P/L': f"${total_pl:.2f}"
        }

def main():
    # Get user input
    symbol = input("Enter the stock symbol to backtest (e.g., AAPL): ").upper()
    days = int(input("Enter number of days to backtest (default: 30): ") or 30)
    capital = float(input("Enter initial capital (default: 10000): ") or 10000)
    
    # Setup dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Run backtest
    backtest = OnePercentBacktest(symbol, capital)
    print(f"\nRunning backtest for {symbol} from {start_date.date()} to {end_date.date()}...")
    backtest.run_backtest(start_date, end_date)
    
    # Print results
    print("\nBacktest Results:")
    stats = backtest.get_stats()
    if isinstance(stats, str):
        print(stats)
    else:
        for key, value in stats.items():
            print(f"{key}: {value}")
        
        # Print detailed trade log
        print("\nDetailed Trade Log:")
        for i, trade in enumerate(backtest.trades, 1):
            print(f"\nTrade {i}:")
            print(f"Entry Time: {trade['entry_time']}")
            print(f"Exit Time: {trade['exit_time']}")
            print(f"Entry Price: ${trade['entry_price']:.2f}")
            print(f"Exit Price: ${trade['exit_price']:.2f}")
            print(f"Shares: {trade['shares']}")
            print(f"P/L: ${trade['pl']:.2f}")
            print(f"Exit Type: {trade['exit_type']}")

if __name__ == "__main__":
    main()