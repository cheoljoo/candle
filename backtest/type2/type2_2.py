import pandas as pd
from pathlib import Path

def run_backtest_type2_2(df, ticker_name, initial_cash, plus_days=3, minus_days=3):
    """
    Type 2-2: consecutive plus_days buy ALL, consecutive minus_days sell ALL.
    """
    cash = initial_cash
    shares = 0
    history = []
    
    if 'MA10M_UPDOWN' not in df.columns:
        return []

    plus_count = 0
    minus_count = 0
    
    for i in range(len(df)):
        sign = df['MA10M_UPDOWN'].iloc[i]
        date = df.index[i]
        price = df['Close'].iloc[i]
        
        if sign == '+':
            plus_count += 1
            minus_count = 0
        elif sign == '-':
            minus_count += 1
            plus_count = 0
        else:
            plus_count = 0
            minus_count = 0
            
        if plus_count == plus_days:
            if cash > price:
                qty_to_buy = int(cash // price)
                cash -= qty_to_buy * price
                shares += qty_to_buy
                history.append({
                    'Date': date, 'Ticker': ticker_name, 'Action': 'BUY',
                    'Price': price, 'Qty': qty_to_buy, 'Total_Qty': shares, 'Cash': cash
                })
            plus_count = 0
            
        elif minus_count == minus_days:
            if shares > 0:
                cash += shares * price
                qty_to_sell = shares
                shares = 0
                history.append({
                    'Date': date, 'Ticker': ticker_name, 'Action': 'SELL',
                    'Price': price, 'Qty': qty_to_sell, 'Total_Qty': shares, 'Cash': cash
                })
            minus_count = 0
            
    return history

def main():
    results = []
    # KR
    kr_dir = Path("data/stocks_kr")
    if kr_dir.exists():
        for f in kr_dir.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            results.extend(run_backtest_type2_2(df, f.stem, 10_000_000 if "kr" in str(f) else 1000))
    # US
    us_dir = Path("data/stocks_us")
    if us_dir.exists():
        for f in us_dir.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            results.extend(run_backtest_type2_2(df, f.stem, 1000))
            
    if results:
        pd.DataFrame(results).to_csv("backtest/type2/results_type2_2.csv", index=False)

if __name__ == "__main__":
    main()
