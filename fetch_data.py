"""
fetch_data.py
KOSPI 상위 200 종목 · S&P500 전 종목 · 주요 ETF의
일봉 종가/거래량/MA10M/Shares/Marcap 데이터를 data/ 디렉터리에 저장합니다.
당일 데이터가 이미 있으면 스킵(증분 수집)합니다.
수집 완료 후 KOSPI·S&P500 일별 시가총액 순위 파일을 생성합니다.
"""

import re
import urllib.request
from io import StringIO

import FinanceDataReader as fdr
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

DATA_DIR        = Path(__file__).parent / "data"
STOCKS_DIR      = DATA_DIR / "stocks"       # KOSPI
US_STOCKS_DIR   = DATA_DIR / "stocks_us"    # S&P500 + ETF
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"
SP500_LIST_FILE = DATA_DIR / "sp500_list.csv"
KOSPI_RANK_FILE = DATA_DIR / "kospi_daily_rank.csv"   # 날짜 × 티커 시총순위 행렬
SP500_RANK_FILE = DATA_DIR / "sp500_daily_rank.csv"   # 날짜 × 티커 시총순위 행렬

ETF_SYMBOLS = ['VOO', 'SPY', 'QQQ', 'SCHD', 'JEPI', 'SOXX', 'XLE']

US_MARKETCAP_CSV_URL = (
    "https://companiesmarketcap.com/usa/largest-companies-in-the-usa-by-market-cap/?download=csv"
)

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


def normalize_symbol(symbol: str) -> str:
    """심볼에서 알파벳/숫자 외 문자를 제거해 정규화."""
    return re.sub(r"[^A-Z0-9]", "", str(symbol).upper())


def fetch_us_marketcap_table() -> pd.DataFrame:
    """companiesmarketcap.com에서 미국 시가총액 데이터를 수집합니다."""
    req = urllib.request.Request(US_MARKETCAP_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        text = response.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df["normalized_symbol"] = df["Symbol"].map(normalize_symbol)
    df["marketcap"] = pd.to_numeric(df["marketcap"], errors="coerce")
    df["price (USD)"] = pd.to_numeric(df["price (USD)"], errors="coerce")
    return df.dropna(subset=["marketcap", "price (USD)"])


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


def compute_and_save_rank_table(
    stocks_dir: Path,
    tickers: list[str],
    shares_map: dict[str, float],
    output_path: Path,
) -> None:
    """
    날짜별 근사 시가총액(Close × 유통주식수)을 계산해 시총순위 테이블로 저장합니다.
    순위 1 = 해당일 시가총액 최대.  출력: CSV (Date index, Ticker 컬럼, 순위 값).
    """
    cap_series: dict[str, pd.Series] = {}
    for ticker in tickers:
        path = stocks_dir / f"{ticker}.csv"
        df = _load_csv(path)
        if df is None or "Close" not in df.columns:
            continue
        shares = shares_map.get(ticker)
        if shares and pd.notna(shares) and float(shares) > 0:
            close = pd.to_numeric(df["Close"], errors="coerce")
            cap_series[ticker] = close * float(shares)
        elif "Marcap" in df.columns:
            cap_series[ticker] = pd.to_numeric(df["Marcap"], errors="coerce")

    if not cap_series:
        print("  [주의] 시가총액 데이터 없음 — 순위 파일 생성 건너뜀")
        return

    cap_df = pd.DataFrame(cap_series).sort_index()
    # rank: 1 = 최대 시가총액, NaN 위치는 NaN 유지
    rank_df = cap_df.rank(axis=1, ascending=False, method="min", na_option="keep")
    rank_df = rank_df.where(cap_df.notna())
    rank_df.to_csv(output_path, encoding="utf-8-sig")
    print(f"  → 일별 시총순위 저장: {output_path.name} ({len(rank_df)}행 × {len(rank_df.columns)}열)")


def fetch_stock_data(
    symbol: str,
    name: str,
    today: date,
    stocks_dir: Path,
    shares: float | None = None,
) -> bool | None:
    """
    일봉 종가 + 거래량 + 10월이평(MA10M) 데이터를 증분 수집해 CSV에 저장.
    shares 제공 시 Shares(유통주식수), Marcap(근사 시가총액) 컬럼도 함께 저장.
    True: 갱신 완료 / False: 이미 최신(스킵) / None: 오류

    CSV 컬럼: Date(index), Close, Volume, MA10M[, Shares, Marcap]
    """
    path = stocks_dir / f"{symbol}.csv"
    existing = _load_csv(path)

    if existing is not None and not existing.empty:
        last_date = existing.index[-1].date()
        needs_backfill = "MA10M" not in existing.columns or "Volume" not in existing.columns
        needs_marcap = (
            shares is not None
            and pd.notna(shares)
            and float(shares) > 0
            and "Marcap" not in existing.columns
        )

        if last_date >= today and not needs_backfill:
            if needs_marcap:
                # 네트워크 재수신 없이 기존 종가 데이터로 Shares/Marcap 계산
                clean = normalize_price_frame(existing)
                clean["Shares"] = float(shares)
                clean["Marcap"] = clean["Close"] * float(shares)
                clean.to_csv(path, encoding="utf-8-sig")
                return True
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
            existing_clean = normalize_price_frame(existing)
            df_combined = pd.concat([existing_clean[["Close", "Volume"]], df_new[["Close", "Volume"]]])
            df_combined = df_combined[~df_combined.index.duplicated(keep='last')]
        else:
            df_combined = df_new[["Close", "Volume"]]

        df_combined = normalize_price_frame(df_combined)
        if shares is not None and pd.notna(shares) and float(shares) > 0:
            df_combined["Shares"] = float(shares)
            df_combined["Marcap"] = df_combined["Close"] * float(shares)
        df_combined.to_csv(path, encoding='utf-8-sig')
        return True

    except Exception as e:
        print(f"  [오류] {name}({symbol}): {e}")
        return None


def _batch_fetch(
    pairs: list[tuple[str, str]],
    stocks_dir: Path,
    today: date,
    label: str,
    shares_map: dict[str, float] | None = None,
):
    """(symbol, name) 목록을 일괄 수집하고 요약을 출력."""
    updated = skipped = failed = 0
    for symbol, name in pairs:
        shares = (shares_map or {}).get(symbol)
        result = fetch_stock_data(symbol, name, today, stocks_dir, shares=shares)
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
    kospi_top200 = kospi_df.head(200)
    kospi_pairs = [(str(r['Code']), str(r['Name'])) for _, r in kospi_top200.iterrows()]
    kospi_shares_map: dict[str, float] = {
        str(row['Code']): float(row['Stocks'])
        for _, row in kospi_top200.iterrows()
        if pd.notna(row.get('Stocks')) and float(row.get('Stocks', 0)) > 0
    }
    _batch_fetch(kospi_pairs, STOCKS_DIR, today, "KOSPI 상위 200", shares_map=kospi_shares_map)

    print("KOSPI 일별 시총순위 계산 중...")
    compute_and_save_rank_table(
        STOCKS_DIR,
        [str(r['Code']) for _, r in kospi_top200.iterrows()],
        kospi_shares_map,
        KOSPI_RANK_FILE,
    )

    # ── S&P500 ────────────────────────────────────────────────────
    print("S&P500 종목 목록을 가져오는 중...")
    sp500_df = fdr.StockListing('S&P500')
    sp500_df.to_csv(SP500_LIST_FILE, index=False, encoding='utf-8-sig')
    print(f"  → {len(sp500_df)}개 종목 저장 완료")
    sp500_pairs = [(str(r['Symbol']), str(r['Name'])) for _, r in sp500_df.iterrows()]

    sp500_shares_map: dict[str, float] = {}
    try:
        print("  S&P500 시가총액 데이터 수집 중 (companiesmarketcap.com)...")
        us_mc = fetch_us_marketcap_table()
        print(f"  → {len(us_mc)}개 시총 데이터 수집 완료")
        sp500_symbols = {str(r['Symbol']) for _, r in sp500_df.iterrows()}
        for sym in sp500_symbols:
            norm = normalize_symbol(sym)
            row = us_mc[us_mc["normalized_symbol"] == norm].head(1)
            if not row.empty:
                mc = float(row["marketcap"].iloc[0])
                price = float(row["price (USD)"].iloc[0])
                if price > 0:
                    sp500_shares_map[sym] = mc / price
        print(f"  → S&P500 유통주식수 근사 계산: {len(sp500_shares_map)}개 종목")
    except Exception as e:
        print(f"  [주의] S&P500 시가총액 수집 실패 (Shares/Marcap 컬럼 미저장): {e}")

    _batch_fetch(
        sp500_pairs,
        US_STOCKS_DIR,
        today,
        "S&P500",
        shares_map=sp500_shares_map or None,
    )

    if sp500_shares_map:
        print("S&P500 일별 시총순위 계산 중...")
        compute_and_save_rank_table(
            US_STOCKS_DIR,
            [str(r['Symbol']) for _, r in sp500_df.iterrows()],
            sp500_shares_map,
            SP500_RANK_FILE,
        )

    # ── ETF ──────────────────────────────────────────────────────
    print("ETF 데이터 수집 중...")
    etf_pairs = [(sym, sym) for sym in ETF_SYMBOLS]
    _batch_fetch(etf_pairs, US_STOCKS_DIR, today, "ETF")

    print("=== 전체 수집 완료 ===")


if __name__ == "__main__":
    main()
