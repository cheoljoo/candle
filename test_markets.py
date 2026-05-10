
from pykrx import stock
import pandas as pd

symbol = "473210"
start = "20240501"
end = "20240508"

for m in ["KOSPI", "KOSDAQ", "KONEX"]:
    df = stock.get_market_ohlcv_by_date(start, end, symbol, market=m)
    if not df.empty:
        print(f"Found in {m}!")
        print(df)
        break
else:
    print("Not found in any stock market.")

# Try ETF market explicitly in a different way
# pykrx doesn't have a market='ETF' for get_market_ohlcv_by_date
# But maybe we can get it from all? 
# Actually, let's try to get all OHLCV for a day and see if it's there.
df = stock.get_market_ohlcv_by_date(end, end, "ALL")
if symbol in df.index:
    print("Found in ALL market for the day.")
else:
    print("Not found in ALL market.")
