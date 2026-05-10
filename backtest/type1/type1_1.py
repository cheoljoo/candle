import pandas as pd
import os
from pathlib import Path

def run_backtest_type1_1(df, ticker_name, initial_cash=float('inf')):
    """
    Type 1-1: - to + buy 10 shares, + to - sell all.
    """
    cash = initial_cash
    shares = 0
    history = []
    
    # We need 'Inflection' and 'MA10M_UPDOWN'
    # Signal: current is + and prev was - (or vice versa)
    if 'MA10M_UPDOWN' not in df.columns:
        return []

    for i in range(1, len(df)):
        prev_sign = df['MA10M_UPDOWN'].iloc[i-1]
        curr_sign = df['MA10M_UPDOWN'].iloc[i]
        date = df.index[i]
        price = df['Close'].iloc[i]
        
        # - to + : BUY 10 shares
        if prev_sign == '-' and curr_sign == '+':
            qty_to_buy = 10
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
                'Total_Value': shares * price + (0 if cash == float('inf') else cash)
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
                    'Total_Value': (0 if cash == float('inf') else cash)
                })
    
    # Final valuation
    if shares > 0:
        last_price = df['Close'].iloc[-1]
        history.append({
            'Date': df.index[-1],
            'Ticker': ticker_name,
            'Action': 'FINAL_VAL',
            'Price': last_price,
            'Qty': shares,
            'Amount': shares * last_price,
            'Total_Qty': shares,
            'Total_Value': shares * last_price + (0 if cash == float('inf') else cash)
        })
        
    return history

def main():
    data_dirs = [Path("data/stocks_kr"), Path("data/stocks_us")]
    results = []
    
    for d in data_dirs:
        if not d.exists(): continue
        for f in d.glob("*.csv"):
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            ticker = f.stem
            history = run_backtest_type1_1(df, ticker)
            results.extend(history)
            
    if results:
        res_df = pd.DataFrame(results)
        output_path = Path("backtest/type1/results_type1_1.csv")
        res_df.to_csv(output_path, index=False)
        print(f"Type 1-1 results saved to {output_path}")

if __name__ == "__main__":
    main()
