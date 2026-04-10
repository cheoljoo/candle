"""
analyze.py
fetch_data.py 로 수집된 데이터를 읽어 KOSPI 상위 200 종목의
10월 이동평균 대비 현재가 위치를 분석합니다.

출력:
  1. [★ 변곡점 종목] – 최근 7거래일 내 이격률 부호가 바뀐 종목 (가장 중요)
  2. [전체 분석]     – 전 종목의 현재가·10월이평·최근 7거래일 이격률
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STOCKS_DIR = DATA_DIR / "stocks"
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"
LOOKBACK = 7  # 표시할 거래일 수


def load_kospi_list() -> pd.DataFrame:
    if not KOSPI_LIST_FILE.exists():
        raise FileNotFoundError(
            f"{KOSPI_LIST_FILE} 이 없습니다. 먼저 fetch_data.py 를 실행하세요."
        )
    return pd.read_csv(KOSPI_LIST_FILE, dtype={'Code': str}, encoding='utf-8-sig')


def analyze_stock(code: str, name: str) -> dict | None:
    """
    저장된 일봉 데이터로 10월 이평 분석.
    - 10월 이평: 월말 종가 기준 rolling(10) → 일봉 인덱스에 forward-fill
    - 조건 미달(데이터 부족, 주가 3000원 미만) 시 None 반환
    """
    path = STOCKS_DIR / f"{code}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df is None or df.empty:
        return None

    # 월말 종가 → 10월 이동평균 → 일봉으로 forward-fill
    monthly_close = df['Close'].resample('ME').last().dropna()
    if len(monthly_close) < 10:
        return None

    ma10_monthly = monthly_close.rolling(window=10).mean()
    ma10_daily = ma10_monthly.reindex(df.index, method='ffill')

    current_price = df['Close'].iloc[-1]
    if current_price < 3000:
        return None

    # 전체 기간 이격률
    divergence = ((df['Close'] - ma10_daily) / ma10_daily * 100).round(2)

    # 최근 LOOKBACK 거래일
    last_n = df['Close'].tail(LOOKBACK)
    last_n_ma = ma10_daily.reindex(last_n.index)
    last_n_div = divergence.reindex(last_n.index)

    current_ma10 = float(last_n_ma.iloc[-1])
    current_div = float(last_n_div.iloc[-1])
    status = "위(매수/보유)" if current_div > 0 else "아래(관망/매도)"

    # 변곡점 판별: 부호가 바뀌는 구간이 있는지
    signs = last_n_div > 0
    inflection_dir = None
    if signs.nunique() > 1:
        # 연속된 쌍 중 부호가 다른 첫 지점의 방향으로 결정
        for i in range(len(signs) - 1):
            if signs.iloc[i] != signs.iloc[i + 1]:
                inflection_dir = "-→+" if (not signs.iloc[i] and signs.iloc[i + 1]) else "+→-"
                break

    return {
        'name': name,
        'current_price': int(current_price),
        'ma10': round(current_ma10, 2),
        'status': status,
        'current_div': round(current_div, 2),
        'last_n_div': last_n_div,   # Series (날짜 인덱스)
        'inflection_dir': inflection_dir,
    }


def build_tables(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    records 로부터 두 DataFrame 생성:
      full_df    – 전체 분석표 (이격률 컬럼: 날짜별)
      inflect_df – 변곡점 종목표
    """
    # 공통 날짜 컬럼 (최근 LOOKBACK일 날짜를 MM-DD 형식으로)
    if not records:
        return pd.DataFrame(), pd.DataFrame()

    # 날짜 컬럼 이름 수집 (모든 종목의 날짜 합집합 → 정렬 후 마지막 LOOKBACK개)
    all_dates = sorted({d for r in records for d in r['last_n_div'].index})
    date_cols = [d.strftime('%m-%d') for d in all_dates[-LOOKBACK:]]
    date_keys = all_dates[-LOOKBACK:]

    full_rows = []
    inflect_rows = []

    for r in records:
        div_vals = {d.strftime('%m-%d'): r['last_n_div'].get(d, float('nan'))
                    for d in date_keys}
        base = {
            '종목명': r['name'],
            '현재가': r['current_price'],
            '10월이평': r['ma10'],
            '상태': r['status'],
        }
        full_rows.append({**base, **div_vals})

        if r['inflection_dir']:
            inflect_rows.append({
                '종목명': r['name'],
                '방향': r['inflection_dir'],
                '현재가': r['current_price'],
                '현재이격률(%)': r['current_div'],
                **div_vals,
            })

    full_df = pd.DataFrame(full_rows)
    full_df = full_df.sort_values(by=date_cols[-1], ascending=False)

    inflect_df = pd.DataFrame(inflect_rows) if inflect_rows else pd.DataFrame()
    if not inflect_df.empty:
        inflect_df = inflect_df.sort_values(by='방향')

    return full_df, inflect_df


def main():
    print("KOSPI 200 종목 분석을 시작합니다...")

    kospi_df = load_kospi_list()
    top200 = kospi_df.head(200)

    records = []
    for _, row in top200.iterrows():
        result = analyze_stock(str(row['Code']), str(row['Name']))
        if result is not None:
            records.append(result)

    if not records:
        print("분석된 결과가 없습니다. fetch_data.py 를 먼저 실행하세요.")
        return

    full_df, inflect_df = build_tables(records)

    print(f"\n기준일: {datetime.now().strftime('%Y-%m-%d')}")

    # ── 1. 변곡점 종목 ──────────────────────────────────────────
    print("\n" + "=" * 80)
    print("★  변곡점 종목  (최근 7거래일 내 이격률 부호 변경)")
    print("=" * 80)
    if inflect_df.empty:
        print("  해당 종목 없음")
    else:
        print(inflect_df.to_string(index=False))

    # ── 2. 전체 분석 ────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"전체 분석  (최근 {LOOKBACK}거래일 이격률 [%])")
    print("=" * 80)
    print(full_df.to_string(index=False))

    # 파일로 저장하고 싶다면 아래 주석 해제
    # full_df.to_csv("kospi200_full.csv", encoding='utf-8-sig', index=False)
    # inflect_df.to_csv("kospi200_inflection.csv", encoding='utf-8-sig', index=False)


if __name__ == "__main__":
    main()

