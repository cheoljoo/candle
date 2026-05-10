
from pykrx import stock
import pandas as pd
from datetime import datetime

today = "20260508" # Use Friday
print(f"Listing ETFs for {today}...")
df = stock.get_etf_ticker_list(today)
print(f"Total ETFs: {len(df)}")
if "473210" in df:
    print("473210 found in ticker list.")
else:
    print("473210 NOT found in ticker list.")
    print("Sample tickers:", df[:10])

# Try to get name
name = stock.get_etf_ticker_name("473210")
print(f"Name for 473210: {name}")
