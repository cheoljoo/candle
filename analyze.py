"""
analyze.py
fetch_data.py 로 수집된 데이터를 읽어 KOSPI 상위 200 종목의
10월 이동평균 대비 현재가 위치를 분석합니다.
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STOCKS_DIR = DATA_DIR / "stocks"
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"


def load_kospi_list() -> pd.DataFrame:
    if not KOSPI_LIST_FILE.exists():
        raise FileNotFoundError(
            f"{KOSPI_LIST_FILE} 이 없습니다. 먼저 fetch_data.py 를 실행하세요."
        )
    return pd.read_csv(KOSPI_LIST_FILE, dtype={'Code': str}, encoding='utf-8-sig')


def analyze_stock(code: str) -> pd.Series | None:
    """저장된 일봉 데이터로 10월 이평 분석. 조건 미달 시 None 반환."""
    path = STOCKS_DIR / f"{code}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df is None or df.empty:
        return None

    # 월봉 리샘플링
    df_monthly = df['Close'].resample('ME').last().dropna()
    if len(df_monthly) < 10:
        return None

    current_price = df['Close'].iloc[-1]

    # 주가 3,000원 이상 필터링
    if current_price < 3000:
        return None

    ma10 = df_monthly.rolling(window=10).mean().iloc[-1]
    diff_ratio = ((current_price - ma10) / ma10) * 100
    status = "위(매수/보유)" if current_price > ma10 else "아래(관망/매도)"

    return pd.Series({
        '현재가': int(current_price),
        '10월이평': round(ma10, 2),
        '상태': status,
        '이격률(%)': round(diff_ratio, 2),
    })


def main():
    print("KOSPI 200 종목 분석을 시작합니다...")

    kospi_df = load_kospi_list()
    top200 = kospi_df.head(200)

    rows = []
    for _, row in top200.iterrows():
        result = analyze_stock(str(row['Code']))
        if result is not None:
            rows.append({'종목명': row['Name'], **result})

    result_df = pd.DataFrame(rows)
    if result_df.empty:
        print("분석된 결과가 없습니다. fetch_data.py 를 먼저 실행하세요.")
        return

    result_df = result_df.sort_values(by='이격률(%)', ascending=False)

    print(f"\n기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(result_df.to_string(index=False))

    # 파일로 저장하고 싶다면 아래 주석 해제
    # result_df.to_csv("kospi200_trend_analysis.csv", encoding='utf-8-sig', index=False)


if __name__ == "__main__":
    main()
