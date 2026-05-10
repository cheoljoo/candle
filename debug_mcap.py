
import pandas as pd
from fetch_data import fetch_us_marketcap_table
import FinanceDataReader as fdr

print("Fetching US marketcap table...")
df = fetch_us_marketcap_table()
print(f"Total rows: {len(df)}")
print(f"Non-null marketcap count: {df['marketcap'].notnull().sum()}")
print(df.sort_values('marketcap', ascending=False).head(10))
