
import pandas as pd
from fetch_data import fetch_us_marketcap_table, STOCKS_US_DIR, fetch_us_stock_list, normalize_symbol
import os

def debug_fetch_us_marketcap_table():
    df = fetch_us_stock_list()
    df['normalized_symbol'] = df['Symbol'].apply(normalize_symbol)
    
    mcaps = {}
    print(f"Scanning {STOCKS_US_DIR}...")
    files = list(STOCKS_US_DIR.glob("*.csv"))
    print(f"Found {len(files)} files.")
    
    for f in files:
        try:
            # Read only last few rows
            temp = pd.read_csv(f, index_col=0)
            if 'Marcap' in temp.columns:
                mcap = temp['Marcap'].dropna().iloc[-1] if not temp['Marcap'].dropna().empty else None
                if mcap is not None:
                    mcaps[f.stem] = mcap
        except Exception as e:
            # print(f"Error {f.name}: {e}")
            continue
            
    print(f"Loaded {len(mcaps)} market caps.")
    df['marketcap'] = df['Symbol'].map(mcaps)
    
    # Check some symbols
    for sym in ['AAPL', 'MSFT', 'GOOGL']:
        print(f"{sym} in mcaps: {sym in mcaps}, value: {mcaps.get(sym)}")
        
    return df

print("Running debug...")
df = debug_fetch_us_marketcap_table()
print(f"Total rows in df: {len(df)}")
print(f"Non-null marketcap in df: {df['marketcap'].notnull().sum()}")
print(df.sort_values('marketcap', ascending=False).head(20))
