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
        losing_trades = total_trades - profitable_trades
        total_pl = sum(t['pl'] for t in self.trades)
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        # Calculate additional statistics
        if profitable_trades > 0:
            avg_profit = sum(t['pl'] for t in self.trades if t['pl'] > 0) / profitable_trades
            max_profit = max(t['pl'] for t in self.trades if t['pl'] > 0)
        else:
            avg_profit = 0
            max_profit = 0
            
        if losing_trades > 0:
            avg_loss = sum(t['pl'] for t in self.trades if t['pl'] <= 0) / losing_trades
            max_loss = min(t['pl'] for t in self.trades if t['pl'] <= 0)
        else:
            avg_loss = 0
            max_loss = 0
        
        target_exits = len([t for t in self.trades if t['exit_type'] == 'target'])
        stop_exits = len([t for t in self.trades if t['exit_type'] == 'stop'])
        
        return {
            'Initial Capital': f"${self.initial_capital:,.2f}",
            'Final Capital': f"${self.capital:,.2f}",
            'Total Return': f"{((self.capital - self.initial_capital) / self.initial_capital * 100):.2f}%",
            'Total Trades': total_trades,
            'Profitable Trades': profitable_trades,
            'Losing Trades': losing_trades,
            'Win Rate': f"{win_rate * 100:.2f}%",
            'Total P/L': f"${total_pl:,.2f}",
            'Average Profit': f"${avg_profit:,.2f}",
            'Average Loss': f"${avg_loss:,.2f}",
            'Max Profit': f"${max_profit:,.2f}",
            'Max Loss': f"${max_loss:,.2f}",
            'Target Exits': target_exits,
            'Stop-Loss Exits': stop_exits
        }

    def get_trade_summary(self):
        """Generate a summary of trade performance by day."""
        if not self.trades:
            return "No trades to summarize"
            
        # Convert trades to DataFrame for analysis
        df = pd.DataFrame(self.trades)
        df['entry_time'] = pd.to_datetime(df['entry_time'])
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        df['trade_duration'] = df['exit_time'] - df['entry_time']
        
        # Group trades by day
        df['date'] = df['entry_time'].dt.date
        daily_summary = df.groupby('date').agg({
            'pl': ['count', 'sum', 'mean'],
            'exit_type': lambda x: x.value_counts().to_dict()
        }).round(2)
        
        return daily_summary

    def get_summary(self):
        """Get a concise summary of trading performance."""
        if not self.trades:
            return "No trades executed during this period."
            
        # Calculate key metrics
        total_trades = len(self.trades)
        profitable_trades = len([t for t in self.trades if t['pl'] > 0])
        total_pl = sum(t['pl'] for t in self.trades)
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate holding times
        trade_durations = []
        for trade in self.trades:
            entry = pd.to_datetime(trade['entry_time'])
            exit = pd.to_datetime(trade['exit_time'])
            duration = exit - entry
            trade_durations.append(duration)
        
        avg_duration = sum(trade_durations, pd.Timedelta(0)) / len(trade_durations) if trade_durations else pd.Timedelta(0)
        
        # Format summary
        summary = f"""
=== Trading Summary ===
Initial Capital: ${self.initial_capital:,.2f}
Final Capital: ${self.capital:,.2f}
Total Profit/Loss: ${total_pl:,.2f} ({((self.capital - self.initial_capital) / self.initial_capital * 100):.2f}% return)
Number of Trades: {total_trades}
Win Rate: {win_rate:.1f}%
Average Trade Duration: {str(avg_duration).split('.')[0]}  # Removing microseconds
Best Trade: ${max([t['pl'] for t in self.trades], default=0):,.2f}
Worst Trade: ${min([t['pl'] for t in self.trades], default=0):,.2f}
"""
        return summary

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
    
    # Print summary first
    print(backtest.get_summary())
    
    # Ask if user wants detailed statistics
    show_details = input("\nWould you like to see detailed statistics? (y/n): ").lower() == 'y'
    
    if show_details:
        print("\n=== Detailed Statistics ===")
        stats = backtest.get_stats()
        if isinstance(stats, str):
            print(stats)
        else:
            for key, value in stats.items():
                print(f"{key}: {value}")
            
            print("\n=== Daily Trade Summary ===")
            daily_summary = backtest.get_trade_summary()
            if isinstance(daily_summary, str):
                print(daily_summary)
            else:
                print("\nDaily Performance:")
                print(daily_summary)
            
            print("\n=== Detailed Trade Log ===")
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