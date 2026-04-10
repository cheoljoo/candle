"""
fetch_data.py
KOSPI 상위 200 종목의 일봉 종가 데이터를 data/ 디렉터리에 저장합니다.
같은 날 재실행해도 이미 오늘 날짜 데이터가 있으면 네트워크 요청을 건너뜁니다.
"""

import FinanceDataReader as fdr
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STOCKS_DIR = DATA_DIR / "stocks"
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"

DATA_DIR.mkdir(exist_ok=True)
STOCKS_DIR.mkdir(exist_ok=True)


def fetch_kospi_list() -> pd.DataFrame:
    """KOSPI 종목 목록을 가져와 저장하고 반환합니다."""
    print("KOSPI 종목 목록을 가져오는 중...")
    df = fdr.StockListing('KOSPI')
    df.to_csv(KOSPI_LIST_FILE, index=False, encoding='utf-8-sig')
    print(f"  → {len(df)}개 종목 저장 완료: {KOSPI_LIST_FILE}")
    return df


def load_existing(code: str) -> pd.DataFrame | None:
    """저장된 일봉 데이터를 불러옵니다. 없으면 None 반환."""
    path = STOCKS_DIR / f"{code}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df


def fetch_stock(code: str, name: str, today: date) -> bool:
    """
    종목 일봉 데이터를 업데이트합니다.
    이미 오늘 데이터가 있으면 스킵(False 반환), 갱신하면 True 반환.
    """
    path = STOCKS_DIR / f"{code}.csv"
    existing = load_existing(code)

    if existing is not None and not existing.empty:
        last_date = existing.index[-1].date()
        if last_date >= today:
            return False  # 이미 최신 데이터 보유
        start = last_date + timedelta(days=1)
    else:
        start = None  # 전체 기간 신규 수집

    try:
        df_new = fdr.DataReader(code, start=start.strftime('%Y-%m-%d') if start else None)
        if df_new is None or df_new.empty:
            return False

        # 종가(Close) 컬럼만 유지
        df_new = df_new[['Close']].dropna()

        if existing is not None and not existing.empty:
            df_combined = pd.concat([existing, df_new])
            df_combined = df_combined[~df_combined.index.duplicated(keep='last')]
        else:
            df_combined = df_new

        df_combined.sort_index(inplace=True)
        df_combined.to_csv(path, encoding='utf-8-sig')
        return True

    except Exception as e:
        print(f"  [오류] {name}({code}): {e}")
        return False


def main():
    today = date.today()
    print(f"=== 데이터 수집 시작 (기준일: {today}) ===\n")

    # 종목 목록 (항상 최신으로 갱신)
    kospi_df = fetch_kospi_list()
    top200 = kospi_df.head(200)

    updated, skipped, failed = 0, 0, 0

    for _, row in top200.iterrows():
        code = row['Code']
        name = row['Name']
        result = fetch_stock(code, name, today)
        if result is True:
            print(f"  [갱신] {name}({code})")
            updated += 1
        elif result is False:
            skipped += 1
        else:
            failed += 1

    print(f"\n=== 완료: 갱신 {updated}개 / 스킵 {skipped}개 / 오류 {failed}개 ===")


if __name__ == "__main__":
    main()
