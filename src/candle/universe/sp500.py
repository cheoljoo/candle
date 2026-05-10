"""S&P 500 멤버십 — Wikipedia HTML table (1차) → FinanceDataReader (fallback)."""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# 일부 환경에서 Wikipedia 403. 흔한 봇 차단 — User-Agent 명시.
WIKI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


def fetch_members() -> pd.DataFrame:
    df = _try_wikipedia()
    if not df.empty:
        return df
    log.warning("Wikipedia SP500 조회 실패 → FinanceDataReader fallback")
    return _fallback_fdr()


def _try_wikipedia() -> pd.DataFrame:
    try:
        import requests
        r = requests.get(WIKI_URL, headers=WIKI_HEADERS, timeout=15)
        r.raise_for_status()
        tables = pd.read_html(r.text, attrs={"id": "constituents"})
    except Exception as e:
        log.warning(f"Wikipedia 요청 실패: {e}")
        return pd.DataFrame(columns=["ticker", "name"])

    if not tables:
        return pd.DataFrame(columns=["ticker", "name"])
    df = tables[0]
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol")
    name_col = cols.get("security") or cols.get("company")
    if sym_col is None or name_col is None:
        return pd.DataFrame(columns=["ticker", "name"])
    out = df[[sym_col, name_col]].rename(columns={sym_col: "ticker", name_col: "name"})
    # Wikipedia의 'BRK.B' 표기는 yfinance에서 'BRK-B'로 사용
    out["ticker"] = out["ticker"].astype(str).str.replace(".", "-", regex=False)
    return out.reset_index(drop=True)


def _fallback_fdr() -> pd.DataFrame:
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("S&P500")
    except Exception as e:
        log.warning(f"FinanceDataReader S&P500 실패: {e}")
        return pd.DataFrame(columns=["ticker", "name"])

    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "name"])
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol")
    name_col = cols.get("name")
    if sym_col is None or name_col is None:
        log.warning(f"FinanceDataReader S&P500 컬럼 인식 실패: {list(df.columns)}")
        return pd.DataFrame(columns=["ticker", "name"])
    out = df[[sym_col, name_col]].rename(columns={sym_col: "ticker", name_col: "name"})
    out["ticker"] = out["ticker"].astype(str).str.replace(".", "-", regex=False)
    log.info(f"S&P500 fallback: {len(out)} 종목")
    return out.reset_index(drop=True)
