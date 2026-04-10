"""
analyze.py
fetch_data.py 로 수집된 데이터를 읽어 다음 세 그룹을 분석합니다.
  - KOSPI 상위 200 종목
  - S&P500 전 종목
  - 주요 ETF (VOO, SPY, QQQ, SCHD, JEPI, SOXX, XLE)

각 그룹 출력:
  1. [★ 변곡점 종목] – 최근 7거래일 내 이격률 부호가 바뀐 종목 (가장 중요)
  2. [전체 분석]     – 티커·종목명·시가총액·현재가·10월이평·최근 7거래일 이격률
"""

import re
import unicodedata
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR        = Path(__file__).parent / "data"
STOCKS_DIR      = DATA_DIR / "stocks"
US_STOCKS_DIR   = DATA_DIR / "stocks_us"
KOSPI_LIST_FILE = DATA_DIR / "kospi_list.csv"
SP500_LIST_FILE = DATA_DIR / "sp500_list.csv"
ETF_SYMBOLS     = ['VOO', 'SPY', 'QQQ', 'SCHD', 'JEPI', 'SOXX', 'XLE']
LOOKBACK        = 7
INFLECTION_FILE = DATA_DIR / "inflection_points.csv"  # 변곡점 종목 저장 파일


# ── 한글 너비 보정 출력 헬퍼 ─────────────────────────────────────────────────

def str_width(s) -> int:
    """터미널 표시 너비 계산 (한글 등 전각문자 = 2칸)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in str(s))


def rpad(s, width: int) -> str:
    s = str(s)
    return s + ' ' * max(0, width - str_width(s))


def lpad(s, width: int) -> str:
    s = str(s)
    return ' ' * max(0, width - str_width(s)) + s


def print_table(df: pd.DataFrame, right_cols: set | None = None) -> None:
    """한글 너비를 고려해 DataFrame을 터미널에 정렬 출력."""
    if df.empty:
        return
    if right_cols is None:
        right_cols = set()

    cols = list(df.columns)
    col_w: dict[str, int] = {}
    for col in cols:
        w = str_width(col)
        for v in df[col]:
            w = max(w, str_width(str(v)))
        col_w[col] = w

    SEP = '  '

    def fmt_row(values: dict) -> str:
        parts = []
        for col in cols:
            v = str(values[col])
            parts.append(lpad(v, col_w[col]) if col in right_cols else rpad(v, col_w[col]))
        return SEP.join(parts)

    header = fmt_row({col: col for col in cols})
    total_w = sum(col_w[c] for c in cols) + len(SEP) * (len(cols) - 1)
    print(header)
    print('─' * total_w)
    for _, row in df.iterrows():
        print(fmt_row(row.to_dict()))


# ── 시가총액 포맷 ─────────────────────────────────────────────────────────────

def format_marcap(marcap) -> str:
    """시가총액(원)을 조/억 단위로 표시."""
    try:
        v = int(float(marcap))
    except (ValueError, TypeError):
        return '-'
    jo  = v // 1_000_000_000_000
    eok = (v % 1_000_000_000_000) // 100_000_000
    if jo > 0:
        return f"{jo}조 {eok}억" if eok else f"{jo}조"
    return f"{eok}억" if eok else '-'


# ── 데이터 로드 ──────────────────────────────────────────────────────────────

def load_kospi_list() -> pd.DataFrame:
    if not KOSPI_LIST_FILE.exists():
        raise FileNotFoundError(f"{KOSPI_LIST_FILE} 없음. fetch_data.py 를 먼저 실행하세요.")
    return pd.read_csv(KOSPI_LIST_FILE, dtype={'Code': str}, encoding='utf-8-sig')


def load_sp500_list() -> pd.DataFrame:
    if not SP500_LIST_FILE.exists():
        raise FileNotFoundError(f"{SP500_LIST_FILE} 없음. fetch_data.py 를 먼저 실행하세요.")
    return pd.read_csv(SP500_LIST_FILE, encoding='utf-8-sig')


# ── 종목 분석 ─────────────────────────────────────────────────────────────────

def analyze_stock(
    ticker: str,
    name: str,
    stocks_dir: Path,
    marcap: str = '-',
    min_price: float = 0.0,
    integer_price: bool = False,
) -> dict | None:
    """
    저장된 일봉 데이터로 10월 이평 분석.
    min_price: 현재가 하한 필터 (KOSPI: 3000, US: 0)
    integer_price: True면 현재가·이평을 정수 반환 (KRW용)
    """
    path = stocks_dir / f"{ticker}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df is None or df.empty:
        return None

    # CSV에 사전 계산된 MA10M 컬럼 사용 (없으면 즉석 계산)
    if 'MA10M' in df.columns:
        ma10_daily = df['MA10M']
        if ma10_daily.dropna().empty:
            return None
    else:
        monthly_close = df['Close'].resample('ME').last().dropna()
        if len(monthly_close) < 10:
            return None
        ma10_monthly = monthly_close.rolling(window=10).mean()
        ma10_daily   = ma10_monthly.reindex(df.index, method='ffill')

    current_price = df['Close'].iloc[-1]
    if min_price > 0 and current_price < min_price:
        return None

    divergence  = ((df['Close'] - ma10_daily) / ma10_daily * 100).round(2)
    last_n      = df['Close'].tail(LOOKBACK)
    last_n_ma   = ma10_daily.reindex(last_n.index)
    last_n_div  = divergence.reindex(last_n.index)

    current_ma10 = float(last_n_ma.iloc[-1])
    current_div  = float(last_n_div.iloc[-1])
    status = "위(매수/보유)" if current_div > 0 else "아래(관망/매도)"

    price_val = int(current_price)       if integer_price else round(float(current_price), 2)
    ma10_val  = int(current_ma10)        if integer_price else round(current_ma10, 2)

    signs = last_n_div > 0
    inflection_dir = None
    if signs.nunique() > 1:
        for i in range(len(signs) - 1):
            if signs.iloc[i] != signs.iloc[i + 1]:
                inflection_dir = "-→+" if (not signs.iloc[i] and signs.iloc[i + 1]) else "+→-"
                break

    return {
        'ticker':         ticker,
        'name':           name,
        'marcap':         marcap,
        'current_price':  price_val,
        'ma10':           ma10_val,
        'status':         status,
        'current_div':    round(current_div, 2),
        'last_n_div':     last_n_div,
        'inflection_dir': inflection_dir,
    }


# ── 테이블 빌드 ───────────────────────────────────────────────────────────────

def build_tables(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    if not records:
        return pd.DataFrame(), pd.DataFrame(), []

    all_dates = sorted({d for r in records for d in r['last_n_div'].index})
    date_keys = all_dates[-LOOKBACK:]
    date_cols = [d.strftime('%m-%d') for d in date_keys]

    full_rows    = []
    inflect_rows = []

    for r in records:
        div_vals = {}
        for dk, dc in zip(date_keys, date_cols):
            raw = r['last_n_div'].get(dk, float('nan'))
            div_vals[dc] = '-' if pd.isna(raw) else raw

        base = {
            '티커':    r['ticker'],
            '종목명':  r['name'],
            '시가총액': r['marcap'],
            '현재가':  r['current_price'],
            '10월이평': r['ma10'],
            '상태':    r['status'],
        }
        full_rows.append({**base, **div_vals})

        if r['inflection_dir']:
            inflect_rows.append({
                '티커':          r['ticker'],
                '종목명':        r['name'],
                '시가총액':      r['marcap'],
                '방향':          r['inflection_dir'],
                '현재가':        r['current_price'],
                '10월이평':      r['ma10'],
                '현재이격률(%)': r['current_div'],
                **div_vals,
            })

    full_df = pd.DataFrame(full_rows)
    full_df = full_df.sort_values(
        by=date_cols[-1],
        ascending=False,
        key=lambda col: pd.to_numeric(col, errors='coerce'),
    )

    inflect_df = pd.DataFrame(inflect_rows) if inflect_rows else pd.DataFrame()
    if not inflect_df.empty:
        inflect_df = inflect_df.sort_values(by='방향')

    return full_df, inflect_df, date_cols


# ── 섹션 출력 ─────────────────────────────────────────────────────────────────

DATE_PAT = re.compile(r'^\d{2}-\d{2}$')


def print_section(title: str, records: list[dict]) -> pd.DataFrame:
    """변곡점 + 전체분석 섹션을 출력. 변곡점 DataFrame 반환."""
    if not records:
        print(f"\n  [{title}] 분석 가능한 종목 없음 (fetch_data.py 실행 필요)\n")
        return pd.DataFrame()

    full_df, inflect_df, date_cols = build_tables(records)
    right_cols = {'현재가', '10월이평', '현재이격률(%)'} | {c for c in full_df.columns if DATE_PAT.match(c)}
    bar = "=" * 110

    print(f"\n{bar}")
    print(f"★  [{title}] 변곡점 종목  (최근 {LOOKBACK}거래일 내 이격률 부호 변경)")
    print(bar)
    if inflect_df.empty:
        print("  해당 종목 없음")
    else:
        inflect_right = {'현재가', '10월이평', '현재이격률(%)'} | {c for c in inflect_df.columns if DATE_PAT.match(c)}
        print_table(inflect_df, right_cols=inflect_right)

    print(f"\n{bar}")
    print(f"[{title}] 전체 분석  (최근 {LOOKBACK}거래일 이격률 [%])")
    print(bar)
    print_table(full_df, right_cols=right_cols)

    # 그룹명 컬럼 추가 후 반환
    if not inflect_df.empty:
        inflect_df.insert(0, '그룹', title)
    return inflect_df


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    today_str = datetime.now().strftime('%Y-%m-%d')
    print(f"KOSPI 200 / S&P500 / ETF 분석을 시작합니다...")
    print(f"기준일: {today_str}")

    # ── KOSPI ────────────────────────────────────────────────────
    kospi_df = load_kospi_list()
    kospi_records = []
    for _, row in kospi_df.head(200).iterrows():
        r = analyze_stock(
            ticker=str(row['Code']),
            name=str(row['Name']),
            stocks_dir=STOCKS_DIR,
            marcap=format_marcap(row.get('Marcap', 0)),
            min_price=3000,
            integer_price=True,
        )
        if r:
            kospi_records.append(r)
    kospi_inflect = print_section("KOSPI 200", kospi_records)

    # ── S&P500 ───────────────────────────────────────────────────
    sp500_df = load_sp500_list()
    sp500_records = []
    for _, row in sp500_df.iterrows():
        r = analyze_stock(
            ticker=str(row['Symbol']),
            name=str(row['Name']),
            stocks_dir=US_STOCKS_DIR,
        )
        if r:
            sp500_records.append(r)
    sp500_inflect = print_section("S&P500", sp500_records)

    # ── ETF ──────────────────────────────────────────────────────
    etf_records = []
    for sym in ETF_SYMBOLS:
        r = analyze_stock(ticker=sym, name=sym, stocks_dir=US_STOCKS_DIR)
        if r:
            etf_records.append(r)
    etf_inflect = print_section("ETF", etf_records)

    # ── 변곡점 종목 파일 저장 ─────────────────────────────────────
    all_inflect = pd.concat(
        [df for df in [kospi_inflect, sp500_inflect, etf_inflect] if not df.empty],
        ignore_index=True,
    )
    if not all_inflect.empty:
        all_inflect.insert(0, '기준일', today_str)
        all_inflect.to_csv(INFLECTION_FILE, index=False, encoding='utf-8-sig')
        print(f"\n★ 변곡점 종목 {len(all_inflect)}개 → {INFLECTION_FILE}")
    else:
        print(f"\n★ 변곡점 종목 없음")


if __name__ == "__main__":
    main()
