import pandas as pd
from pathlib import Path
from dateutil.relativedelta import relativedelta

def run_backtest_type3(df, ticker_name, amount_per_period):
    """
    Type 3: Buy amount_per_period every 3 months.
    """
    cash = 0 # In DCA, we assume we inject cash every 3 months
    shares = 0
    history = []
    
    if df.empty: return []
    
    last_buy_date = None
    
    for i in range(len(df)):
        date = pd.to_datetime(df.index[i])
        price = df['Close'].iloc[i]
        
        # Buy on the first day, then every 3 months
        if last_buy_date is None or date >= last_buy_date + relativedelta(months=3):
            qty_to_buy = int(amount_per_period // price)
            shares += qty_to_buy
            last_buy_date = date
            history.append({
                'Date': date, 'Ticker': ticker_name, 'Action': 'BUY',
                'Price': price, 'Qty': qty_to_buy, 'Total_Qty': shares,
                'Invested': (len(history) + 1) * amount_per_period
            })
            
    # Final valuation
    last_price = df['Close'].iloc[-1]
    total_invested = len([h for h in history if h['Action'] == 'BUY']) * amount_per_period
    current_value = shares * last_price
    history.append({
        'Date': df.index[-1], 'Ticker': ticker_name, 'Action': 'FINAL_VAL',
        'Price': last_price, 'Qty': shares, 'Total_Qty': shares,
        'Total_Value': current_value,
        'ROI': (current_value - total_invested) / total_invested * 100 if total_invested > 0 else 0
    })
    
    return history

def main():
    results = []
    # KR
    kr_dir = Path("data/stocks_kr")
    if kr_dir.exists():
        for f in kr_dir.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            results.extend(run_backtest_type3(df, f.stem, 10_000_000))
    # US
    us_dir = Path("data/stocks_us")
    if us_dir.exists():
        for f in us_dir.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            results.extend(run_backtest_type3(df, f.stem, 1000))
            
    if results:
        pd.DataFrame(results).to_csv("backtest/type3/results_type3.csv", index=False)

if __name__ == "__main__":
    main()
