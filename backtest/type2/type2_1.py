import pandas as pd
from pathlib import Path

def run_backtest_type2_1(df, ticker_name, plus_days=3, minus_days=3):
    """
    Type 2-1: consecutive plus_days buy 10, consecutive minus_days sell 10.
    """
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
            qty_to_buy = 10
            shares += qty_to_buy
            history.append({
                'Date': date, 'Ticker': ticker_name, 'Action': 'BUY',
                'Price': price, 'Qty': qty_to_buy, 'Total_Qty': shares
            })
            plus_count = 0 # Reset after buy to wait for next plus_days? Or keep counting?
            # Requirement says "확인 후 ... 매수". Usually it means once per signal period.
            # I'll reset to avoid buying every day after plus_days.
            
        elif minus_count == minus_days:
            if shares >= 10:
                qty_to_sell = 10
                shares -= qty_to_sell
                history.append({
                    'Date': date, 'Ticker': ticker_name, 'Action': 'SELL',
                    'Price': price, 'Qty': qty_to_sell, 'Total_Qty': shares
                })
            minus_count = 0
            
    return history

def main():
    results = []
    data_dirs = [Path("data/stocks_kr"), Path("data/stocks_us")]
    for d in data_dirs:
        if not d.exists(): continue
        for f in d.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            results.extend(run_backtest_type2_1(df, f.stem))
            
    if results:
        pd.DataFrame(results).to_csv("backtest/type2/results_type2_1.csv", index=False)

if __name__ == "__main__":
    main()
