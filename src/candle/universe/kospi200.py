"""KOSPI200 멤버십.

pykrx 1.2.x 부터 KRX 인증이 필요한 endpoint 가 늘었고, KRX_ID/KRX_PW 환경변수가
없으면 빈 응답 + stdout/logging 노이즈를 토함. 그래서 fallback 순서:

  1) pykrx (최대 1번만 시도, 노이즈 억제)
  2) FinanceDataReader 'KRX' listing 의 시총 top 200 (KOSPI200 근사)
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from ._quiet import quiet_pykrx

log = logging.getLogger(__name__)


def fetch_members(as_of: date) -> pd.DataFrame:
    """as_of 기준 KOSPI200 구성종목 list. 실패 시 fallback."""
    df = _try_pykrx(as_of)
    if not df.empty:
        return df
    log.info("pykrx KOSPI200 미사용 → FinanceDataReader fallback (시총 top 200)")
    return _fallback_fdr_top200()


def _try_pykrx(as_of: date) -> pd.DataFrame:
    try:
        from pykrx import stock
    except Exception as e:
        log.warning(f"pykrx import 실패: {e}")
        return pd.DataFrame(columns=["ticker", "name"])

    ymd = as_of.strftime("%Y%m%d")
    try:
        with quiet_pykrx():
            result = stock.get_index_portfolio_deposit_file("1028", date=ymd)
    except Exception:
        return pd.DataFrame(columns=["ticker", "name"])

    tickers: list[str] = []
    if isinstance(result, pd.DataFrame):
        if result.empty:
            return pd.DataFrame(columns=["ticker", "name"])
        tickers = [str(t) for t in result.index.tolist()]
    elif isinstance(result, (list, tuple)):
        if not result:
            return pd.DataFrame(columns=["ticker", "name"])
        tickers = [str(t) for t in result]
    else:
        return pd.DataFrame(columns=["ticker", "name"])

    rows = []
    with quiet_pykrx():
        for t in tickers:
            try:
                name = stock.get_market_ticker_name(t)
            except Exception:
                name = ""
            rows.append({"ticker": t, "name": name})
    return pd.DataFrame(rows)


def _fallback_fdr_top200() -> pd.DataFrame:
    try:
        import FinanceDataReader as fdr
    except Exception as e:
        log.warning(f"FinanceDataReader import 실패: {e}")
        return pd.DataFrame(columns=["ticker", "name"])

    try:
        df = fdr.StockListing("KRX")
    except Exception as e:
        log.warning(f"fdr.StockListing('KRX') 실패: {e}")
        return pd.DataFrame(columns=["ticker", "name"])

    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "name"])

    cols = {c.lower(): c for c in df.columns}
    code_col = cols.get("code") or cols.get("symbol")
    name_col = cols.get("name")
    market_col = cols.get("market")
    cap_col = cols.get("marcap") or cols.get("market_cap")
    if not (code_col and name_col and market_col and cap_col):
        log.warning(f"FinanceDataReader 컬럼 인식 실패: {list(df.columns)}")
        return pd.DataFrame(columns=["ticker", "name"])

    kospi = df[df[market_col].astype(str).str.upper() == "KOSPI"].copy()
    kospi[cap_col] = pd.to_numeric(kospi[cap_col], errors="coerce")
    kospi = kospi.dropna(subset=[cap_col]).sort_values(cap_col, ascending=False).head(200)

    out = kospi[[code_col, name_col]].rename(columns={code_col: "ticker", name_col: "name"})
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    log.info(f"KOSPI200 fallback: 시총 top 200 ({len(out)} 종목)")
    return out.reset_index(drop=True)
