import pandas as pd
import os
from pathlib import Path

def run_backtest_type1_2(df, ticker_name, initial_cash):
    """
    Type 1-2: - to + buy ALL, + to - sell all.
    """
    cash = initial_cash
    shares = 0
    history = []
    
    if 'MA10M_UPDOWN' not in df.columns:
        return []

    for i in range(1, len(df)):
        prev_sign = df['MA10M_UPDOWN'].iloc[i-1]
        curr_sign = df['MA10M_UPDOWN'].iloc[i]
        date = df.index[i]
        price = df['Close'].iloc[i]
        
        # - to + : BUY ALL
        if prev_sign == '-' and curr_sign == '+':
            if cash > price:
                qty_to_buy = int(cash // price)
                amount = qty_to_buy * price
                shares += qty_to_buy
                cash -= amount
                history.append({
                    'Date': date,
                    'Ticker': ticker_name,
                    'Action': 'BUY',
                    'Price': price,
                    'Qty': qty_to_buy,
                    'Amount': amount,
                    'Total_Qty': shares,
                    'Cash': cash,
                    'Total_Value': shares * price + cash
                })
            
        # + to - : SELL all
        elif prev_sign == '+' and curr_sign == '-':
            if shares > 0:
                qty_to_sell = shares
                amount = qty_to_sell * price
                shares = 0
                cash += amount
                history.append({
                    'Date': date,
                    'Ticker': ticker_name,
                    'Action': 'SELL',
                    'Price': price,
                    'Qty': qty_to_sell,
                    'Amount': amount,
                    'Total_Qty': shares,
                    'Cash': cash,
                    'Total_Value': cash
                })
    
    # Final valuation
    last_price = df['Close'].iloc[-1]
    history.append({
        'Date': df.index[-1],
        'Ticker': ticker_name,
        'Action': 'FINAL_VAL',
        'Price': last_price,
        'Qty': shares,
        'Amount': shares * last_price,
        'Total_Qty': shares,
        'Cash': cash,
        'Total_Value': shares * last_price + cash,
        'ROI': (shares * last_price + cash - initial_cash) / initial_cash * 100
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
            ticker = f.stem
            history = run_backtest_type1_2(df, ticker, 10_000_000)
            results.extend(history)
            
    # US
    us_dir = Path("data/stocks_us")
    if us_dir.exists():
        for f in us_dir.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            ticker = f.stem
            history = run_backtest_type1_2(df, ticker, 1000)
            results.extend(history)
            
    if results:
        res_df = pd.DataFrame(results)
        output_path = Path("backtest/type1/results_type1_2.csv")
        res_df.to_csv(output_path, index=False)
        print(f"Type 1-2 results saved to {output_path}")

if __name__ == "__main__":
    main()
