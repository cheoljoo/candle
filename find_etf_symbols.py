
import FinanceDataReader as fdr
import pandas as pd

etf_names = [
    "KODEX 미국배당커버드콜액티브",
    "RISE 테슬라미국채타겟커버드콜혼합(합성)",
    "ACE 미국10년국채액티브(H)",
    "KODEX 방산TOP10",
    "KODEX 미국30년국채타겟커버드콜",
    "TIGER 코리아AI전력기기TOP3플러스",
    "RISE 200위클리커버드콜",
    "ACE 미국빅테크7+데일리타겟커버드콜",
    "KODEX 코스닥150",
    "TIME 미국나스닥100액티브",
    "SOL 금융지주플러스고배당"
]

print("Searching for ETFs in FinanceDataReader...")
df = fdr.StockListing('ETF/KR')
results = {}
for name in etf_names:
    match = df[df['Name'].str.contains(name.split('(')[0])]
    if not match.empty:
        results[name] = match.iloc[0]['Symbol']
    else:
        # Try fuzzy match
        match = df[df['Name'].str.contains(name[:10])]
        if not match.empty:
            results[name] = match.iloc[0]['Symbol']
        else:
            results[name] = "NOT FOUND"

for name, symbol in results.items():
    print(f"{name}: {symbol}")
