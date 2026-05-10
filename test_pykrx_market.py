
from pykrx import stock
import pandas as pd
from datetime import datetime

symbol = "473210"
start_date = "20240501"
end_date = "20240508"

print(f"Fetching {symbol} using get_market_ohlcv_by_date...")
df = stock.get_market_ohlcv_by_date(start_date, end_date, symbol)
print(df)
