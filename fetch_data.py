import os
import re
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import time

# Directories
DATA_DIR = Path("data")
STOCKS_KR_DIR = DATA_DIR / "stocks_kr"
STOCKS_US_DIR = DATA_DIR / "stocks_us"
RANK_DIR = DATA_DIR / "rank"
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"
SP500_LIST_FILE = DATA_DIR / "sp500_list.csv"

for d in [DATA_DIR, STOCKS_KR_DIR, STOCKS_US_DIR, RANK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ETF Lists
KR_ETFS = {
    "441640": "KODEX 미국배당커버드콜액티브",
    "0013R0": "RISE 테슬라미국채타겟커버드콜혼합(합성)",
    "0085N0": "ACE 미국10년국채액티브(H)",
    "0080G0": "KODEX 방산TOP10",
    "481060": "KODEX 미국30년국채타겟커버드콜",
    "0117V0": "TIGER 코리아AI전력기기TOP3플러스",
    "475720": "RISE 200위클리커버드콜",
    "480020": "ACE 미국빅테크7+데일리타겟커버드콜",
    "229200": "KODEX 코스닥150",
    "426030": "TIME 미국나스닥100액티브",
    "484880": "SOL 금융지주플러스고배당"
}

US_ETFS = {
    "VOO": "Vanguard S&P 500 ETF",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "SCHD": "Schwab US Dividend Equity ETF",
    "JEPI": "JPMorgan Equity Premium Income ETF",
    "SOXX": "iShares Semiconductor ETF",
    "XLE": "Energy Select Sector SPDR Fund",
    "^SOX": "PHLX Semiconductor Index"
}

def get_ma(series, window):
    return series.rolling(window=window).mean()

def compute_ma10m(series):
    # 10 month moving average using monthly end prices, then forward fill to daily
    monthly = series.resample('ME').last()
    ma10m = monthly.rolling(window=10).mean()
    return ma10m.reindex(series.index, method='ffill')

def calculate_indicators(df):
    if df.empty: return df
    df['MA10D'] = get_ma(df['Close'], 10)
    df['MA50D'] = get_ma(df['Close'], 50)
    df['MA10M'] = compute_ma10m(df['Close'])
    
    # MA10M_UPDOWN: + if Close > MA10M, - if Close < MA10M
    df['MA10M_UPDOWN'] = df.apply(lambda row: '+' if row['Close'] > row['MA10M'] else '-' if row['Close'] < row['MA10M'] else '', axis=1)
    
    # Inflection point: when Close crosses MA10M
    # We can detect this by checking if the sign of (Close - MA10M) changed from previous day
    diff = df['Close'] - df['MA10M']
    df['Inflection'] = (diff * diff.shift(1) < 0)
    
    return df

def fetch_kr_stock_list():
    df = fdr.StockListing('KOSPI')
    # Filter for KOSPI 200 (approximate by top 200 by market cap for now as fdr doesn't directly give 'KOSPI200' list with all details easily)
    # Actually fdr.StockListing('KOSPI') gives all KOSPI stocks. We'll take top 200.
    df = df.sort_values('Marcap', ascending=False).head(200)
    return df

def fetch_us_stock_list():
    # S&P 500
    df = fdr.StockListing('S&P500')
    return df

def normalize_symbol(symbol):
    """지수나 티커에서 특수문자 제거 및 대문화 (예: ^GSPC -> GSPC)"""
    return re.sub(r'[^a-zA-Z0-9]', '', str(symbol)).upper()

def fetch_us_marketcap_table():
    """S&P 500 리스트를 가져와 시가총액 비교를 위한 테이블 반환"""
    df = fetch_us_stock_list()
    df['normalized_symbol'] = df['Symbol'].apply(normalize_symbol)
    
    # Try to get marketcap from existing CSV files efficiently
    mcaps = {}
    for f in STOCKS_US_DIR.glob("*.csv"):
        try:
            # Read only last 10 lines to find latest non-null Marcap
            with open(f, 'rb') as fh:
                fh.seek(0, 2)
                size = fh.tell()
                # Read last 2048 bytes (enough for 10+ lines)
                fh.seek(max(0, size - 2048))
                chunk = fh.read().decode('utf-8', errors='ignore')
                lines = chunk.splitlines()
                # Process lines from bottom to top
                header = "Marcap"
                for line in reversed(lines):
                    parts = line.split(',')
                    # We need to know which column Marcap is. 
                    # Assuming standard format or checking header once.
                    # Since column order can vary, it's safer but slower to use pandas for first few files
                    # then cache column index if they are identical.
                    # For simplicity and correctness, let's use pandas but only on small tail.
                    pass
            
            # Use pandas but only on a small tail
            temp = pd.read_csv(f, index_col=0).tail(10)
            if 'Marcap' in temp.columns:
                valid_mcap = temp['Marcap'].dropna()
                if not valid_mcap.empty:
                    mcaps[f.stem] = valid_mcap.iloc[-1]
        except:
            continue
            
    # Map using normalized symbols to be more robust
    df['marketcap'] = df['normalized_symbol'].map(mcaps)
    
    # If still missing, check if Marcap is in original df
    if 'Marcap' in df.columns:
        df['marketcap'] = df['marketcap'].fillna(pd.to_numeric(df['Marcap'], errors='coerce'))
        
    return df

def fetch_and_save_data(symbol, name, region='KR', is_etf=False):
    path = (STOCKS_KR_DIR if region == 'KR' else STOCKS_US_DIR) / f"{symbol}.csv"
    
    # Incremental update logic
    start_date = "2010-01-01"
    existing_df = pd.DataFrame()
    if path.exists():
        existing_df = pd.read_csv(path, index_col=0, parse_dates=True)
        if not existing_df.empty:
            existing_df.index = pd.to_datetime(existing_df.index, utc=True).tz_localize(None)
            last_date = existing_df.index[-1]
            if last_date.date() >= datetime.now().date():
                print(f"Skipping {symbol} ({name}) - already up to date.")
                return
            start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"Fetching {symbol} ({name}) from {start_date}...")
    
    try:
        if region == 'KR':
            df = fdr.DataReader(symbol, start_date)
            # Add PER, PBR if possible. FDR doesn't provide historical PER/PBR easily.
            # We might need to fetch from other sources or just stick to what fdr provides.
            # For now, let's use what's available.
        else:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date)
            if not df.empty:
                df.index = df.index.tz_localize(None)
            
            if df.empty:
                # If yfinance history is empty for start_date, try full history if file doesn't exist
                if existing_df.empty:
                    df = ticker.history(period="max")
                    if not df.empty:
                        df.index = df.index.tz_localize(None)
            
            # yfinance columns: Open, High, Low, Close, Volume, Dividends, Stock Splits
            # Rename to match FDR: Close, Open, High, Low, Volume
            df = df.rename(columns={'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'})

        if df.empty:
            print(f"No new data for {symbol}")
            return

        combined_df = pd.concat([existing_df, df])
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
        combined_df.sort_index(inplace=True)
        
        # Calculate indicators on the full combined dataset to ensure MAs are correct
        combined_df = calculate_indicators(combined_df)
        
        # Fetch fundamental data (PER, PBR, Dividends, Marcap, Shares)
        if region == 'US':
            ticker = yf.Ticker(symbol)
            info = ticker.info
            combined_df.loc[combined_df.index[-1], 'PER'] = info.get('forwardPE')
            combined_df.loc[combined_df.index[-1], 'PBR'] = info.get('priceToBook')
            combined_df.loc[combined_df.index[-1], 'Marcap'] = info.get('marketCap')
            combined_df.loc[combined_df.index[-1], 'Shares'] = info.get('sharesOutstanding')
            # Dividends are already in df from history(with dividends=True which is default)
            if 'Dividends' in combined_df.columns:
                # Calculate Dividend Yield based on last 12 months dividends
                last_year = combined_df.index[-1] - timedelta(days=365)
                recent_divs = combined_df[combined_df.index > last_year]['Dividends'].sum()
                combined_df.loc[combined_df.index[-1], 'DivYield'] = recent_divs / combined_df.iloc[-1]['Close'] if combined_df.iloc[-1]['Close'] > 0 else 0

        combined_df.to_csv(path)
        
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")

def main():
    print(f"Start Data Fetching: {datetime.now()}")
    
    # Group 1: KOSPI 200
    print("Fetching KOSPI 200 list...")
    kospi200 = fetch_kr_stock_list()
    kospi200.to_csv(KOSPI_LIST_FILE, index=False, encoding='utf-8-sig')
    for _, row in kospi200.iterrows():
        fetch_and_save_data(row['Code'], row['Name'], region='KR')
        time.sleep(0.1)
    
    # Group 3: KR ETFs
    print("Fetching KR ETFs...")
    for symbol, name in KR_ETFS.items():
        fetch_and_save_data(symbol, name, region='KR', is_etf=True)
        time.sleep(0.1)

    # Group 2: S&P 500
    print("Fetching S&P 500 list...")
    sp500 = fetch_us_stock_list()
    sp500.to_csv(SP500_LIST_FILE, index=False, encoding='utf-8-sig')
    for _, row in sp500.iterrows():
        fetch_and_save_data(row['Symbol'], row['Name'], region='US')
        time.sleep(0.2) # yfinance rate limiting

    # Group 4: US ETFs
    print("Fetching US ETFs...")
    for symbol, name in US_ETFS.items():
        fetch_and_save_data(symbol, name, region='US', is_etf=True)
        time.sleep(0.2)

    print("Data Fetching Completed.")

if __name__ == "__main__":
    main()
