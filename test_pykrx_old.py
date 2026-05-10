
from pykrx import stock
import pandas as pd

symbol = "473210"
try:
    df = stock.get_market_ohlcv_by_date("20230101", "20260508", symbol)
    if not df.empty:
        print(f"Success! {len(df)} rows.")
        print(df.tail())
    else:
        print("Still empty.")
except Exception as e:
    print(f"Error: {e}")
