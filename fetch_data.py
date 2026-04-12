"""
fetch_data.py
KOSPI 상위 200 종목 · S&P500 전 종목 · 주요 ETF의
일봉 종가/거래량 데이터를 data/ 디렉터리에 저장합니다.
당일 데이터가 이미 있으면 스킵(증분 수집)합니다.
"""

import FinanceDataReader as fdr
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

DATA_DIR        = Path(__file__).parent / "data"
STOCKS_DIR      = DATA_DIR / "stocks"       # KOSPI
US_STOCKS_DIR   = DATA_DIR / "stocks_us"    # S&P500 + ETF
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"
SP500_LIST_FILE = DATA_DIR / "sp500_list.csv"

ETF_SYMBOLS = ['VOO', 'SPY', 'QQQ', 'SCHD', 'JEPI', 'SOXX', 'XLE']

for _d in [DATA_DIR, STOCKS_DIR, US_STOCKS_DIR]:
    _d.mkdir(exist_ok=True)


def _load_csv(path: Path) -> pd.DataFrame | None:
    """저장된 CSV 일봉 파일 로드. 없으면 None 반환."""
    if not path.exists():
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def compute_ma10m(close_series: pd.Series) -> pd.Series:
    """월말 종가 기준 10개월 이동평균을 일봉 인덱스로 forward-fill하여 반환."""
    monthly = close_series.resample('ME').last().dropna()
    ma10_monthly = monthly.rolling(window=10).mean()
    return ma10_monthly.reindex(close_series.index, method='ffill')


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    """DataReader 결과를 Close/Volume/MA10M 형식으로 정리."""
    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = (
        pd.to_numeric(df["Volume"], errors="coerce")
        if "Volume" in df.columns
        else pd.Series(index=df.index, dtype="float64")
    )
    price_df = pd.DataFrame({"Close": close, "Volume": volume}, index=df.index).dropna(subset=["Close"])
    price_df.sort_index(inplace=True)
    price_df["MA10M"] = compute_ma10m(price_df["Close"])
    return price_df


def fetch_stock_data(symbol: str, name: str, today: date, stocks_dir: Path) -> bool | None:
    """
    일봉 종가 + 거래량 + 10월이평(MA10M) 데이터를 증분 수집해 CSV에 저장.
    True: 갱신 완료 / False: 이미 최신(스킵) / None: 오류

    CSV 컬럼: Date(index), Close, Volume, MA10M
    MA10M: 월말 종가 기준 10개월 이동평균을 일봉 인덱스에 forward-fill
    """
    path = stocks_dir / f"{symbol}.csv"
    existing = _load_csv(path)

    if existing is not None and not existing.empty:
        last_date = existing.index[-1].date()
        needs_backfill = "MA10M" not in existing.columns or "Volume" not in existing.columns
        if last_date >= today and not needs_backfill:
            return False
        start = existing.index[0].date() if needs_backfill else last_date + timedelta(days=1)
    else:
        start = None

    try:
        df_new = fdr.DataReader(
            symbol,
            start=start.strftime('%Y-%m-%d') if start else None,
        )
        if df_new is None or df_new.empty:
            return None

        df_new = normalize_price_frame(df_new)

        if existing is not None and not existing.empty:
            existing = normalize_price_frame(existing)
            df_combined = pd.concat([existing[["Close", "Volume"]], df_new[["Close", "Volume"]]])
            df_combined = df_combined[~df_combined.index.duplicated(keep='last')]
        else:
            df_combined = df_new[["Close", "Volume"]]

        df_combined = normalize_price_frame(df_combined)
        df_combined.to_csv(path, encoding='utf-8-sig')
        return True

    except Exception as e:
        print(f"  [오류] {name}({symbol}): {e}")
        return None


def _batch_fetch(pairs: list[tuple[str, str]], stocks_dir: Path, today: date, label: str):
    """(symbol, name) 목록을 일괄 수집하고 요약을 출력."""
    updated = skipped = failed = 0
    for symbol, name in pairs:
        result = fetch_stock_data(symbol, name, today, stocks_dir)
        if result is True:
            print(f"  [갱신] {name}({symbol})")
            updated += 1
        elif result is False:
            skipped += 1
        else:
            failed += 1
    print(f"  {label} 완료 — 갱신 {updated}개 / 스킵 {skipped}개 / 오류 {failed}개\n")


def main():
    today = date.today()
    print(f"=== 데이터 수집 시작 (기준일: {today}) ===\n")

    # ── KOSPI 상위 200 ────────────────────────────────────────────
    print("KOSPI 종목 목록을 가져오는 중...")
    kospi_df = fdr.StockListing('KOSPI')
    kospi_df.to_csv(KOSPI_LIST_FILE, index=False, encoding='utf-8-sig')
    print(f"  → {len(kospi_df)}개 종목 저장 완료")
    kospi_pairs = [(str(r['Code']), str(r['Name'])) for _, r in kospi_df.head(200).iterrows()]
    _batch_fetch(kospi_pairs, STOCKS_DIR, today, "KOSPI 상위 200")

    # ── S&P500 ────────────────────────────────────────────────────
    print("S&P500 종목 목록을 가져오는 중...")
    sp500_df = fdr.StockListing('S&P500')
    sp500_df.to_csv(SP500_LIST_FILE, index=False, encoding='utf-8-sig')
    print(f"  → {len(sp500_df)}개 종목 저장 완료")
    sp500_pairs = [(str(r['Symbol']), str(r['Name'])) for _, r in sp500_df.iterrows()]
    _batch_fetch(sp500_pairs, US_STOCKS_DIR, today, "S&P500")

    # ── ETF ──────────────────────────────────────────────────────
    print("ETF 데이터 수집 중...")
    etf_pairs = [(sym, sym) for sym in ETF_SYMBOLS]
    _batch_fetch(etf_pairs, US_STOCKS_DIR, today, "ETF")

    print("=== 전체 수집 완료 ===")


if __name__ == "__main__":
    main()
