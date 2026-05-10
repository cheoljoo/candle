
from pykrx import stock
import pandas as pd
from datetime import datetime

symbol = "473210"
start_date = "20240101"
end_date = datetime.now().strftime("%Y%m%d")

print(f"Fetching {symbol} from {start_date} to {end_date} using pykrx...")
df = stock.get_etf_ohlcv_by_date(start_date, end_date, symbol)
print(df.head())
print(df.tail())
if not df.empty:
    print(f"Successfully fetched {len(df)} rows.")
else:
    print("Failed to fetch data.")
