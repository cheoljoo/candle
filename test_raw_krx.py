
import requests
import pandas as pd

# This is what pykrx roughly does for ETF list
url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
data = {
    "bld": "dbstat/program/di/etf/item/list_etf_ticker",
    "date": "20240508",
    "market": "ALL"
}
headers = {
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdcMdiMain.cmd",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
r = requests.post(url, data=data, headers=headers)
print(r.status_code)
# print(r.text) # Uncomment if needed
if r.status_code == 200:
    j = r.json()
if 'block1' in j:
    df = pd.DataFrame(j['block1'])
    print("Columns:", df.columns.tolist())
    print(df.head())
    if not df.empty:
        res = df[df['ISU_SRT_CD'] == '473210']
        print("Search 473210:")
        print(res)
else:
    print("No block1 in response.")
    print(j)
