
from pykrx import stock
import pandas as pd

date = "20260508"
tickers = stock.get_market_ticker_list(date, market="ALL")
if "473210" in tickers:
    print("473210 found in market tickers.")
    name = stock.get_market_ticker_name("473210")
    print(f"Name: {name}")
else:
    print("473210 NOT found in market tickers.")

# Search for the name instead
all_tickers = stock.get_market_ticker_list(date, market="ALL")
for t in all_tickers:
    name = stock.get_market_ticker_name(t)
    if "미국배당커버드콜" in name:
        print(f"Found: {t} - {name}")
