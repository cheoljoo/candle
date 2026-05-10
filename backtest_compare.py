import pandas as pd
from pathlib import Path

def aggregate_results(file_path, strategy_name):
    if not file_path.exists():
        return pd.DataFrame()
    
    df = pd.read_csv(file_path)
    if df.empty:
        return pd.DataFrame()
        
    # Filter for final valuations to get current status
    final_vals = df[df['Action'] == 'FINAL_VAL'].copy()
    
    # Calculate buy/sell counts
    buy_counts = df[df['Action'] == 'BUY'].groupby('Ticker').size().rename('Buy_Count')
    sell_counts = df[df['Action'] == 'SELL'].groupby('Ticker').size().rename('Sell_Count')
    
    final_vals = final_vals.set_index('Ticker')
    final_vals = final_vals.join(buy_counts).join(sell_counts).fillna(0)
    
    final_vals['Strategy'] = strategy_name
    return final_vals

def main():
    strategies = {
        "Type 1-1": Path("backtest/type1/results_type1_1.csv"),
        "Type 1-2": Path("backtest/type1/results_type1_2.csv"),
        "Type 2-1": Path("backtest/type2/results_type2_1.csv"),
        "Type 2-2": Path("backtest/type2/results_type2_2.csv"),
        "Type 3": Path("backtest/type3/results_type3.csv"),
    }
    
    all_summaries = []
    for name, path in strategies.items():
        summary = aggregate_results(path, name)
        if not summary.empty:
            all_summaries.append(summary)
            
    if not all_summaries:
        print("No results to compare.")
        return
        
    compare_df = pd.concat(all_summaries).reset_index()
    
    # Key metrics
    # Ticker, Strategy, Total_Value, ROI, Buy_Count, Sell_Count
    compare_df = compare_df[['Ticker', 'Strategy', 'Total_Value', 'ROI', 'Buy_Count', 'Sell_Count', 'Total_Qty']]
    
    # Sort and display
    compare_df.sort_values(['Ticker', 'ROI'], ascending=[True, False], inplace=True)
    
    print("\n=== Strategy Comparison ===")
    print(compare_df.head(20)) # Print top 20
    
    compare_df.to_csv("backtest_compare.csv", index=False)
    print(f"\nFull comparison saved to backtest_compare.csv")
    
    # Best strategy per ticker
    best_per_ticker = compare_df.sort_values('ROI', ascending=False).groupby('Ticker').head(1)
    print("\n=== Best Strategy per Ticker (Top 10) ===")
    print(best_per_ticker.head(10))

if __name__ == "__main__":
    main()
