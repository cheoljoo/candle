
from pykrx import stock
import pandas as pd
from datetime import datetime

symbol = "069500" # KODEX 200
start_date = "20240501"
end_date = "20240508"

print(f"Fetching {symbol} using pykrx...")
df = stock.get_etf_ohlcv_by_date(start_date, end_date, symbol)
print(df)
