"""ETF list — config의 고정 list. KR ETF는 이름→ticker 매핑.

매핑 출처: pykrx (1차, 노이즈 억제) → FinanceDataReader 'ETF/KR' (fallback).
pykrx 1.2.x KRX 인증 정책 변경 시 fallback이 동작.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ._quiet import quiet_pykrx

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return "".join(s.split()).lower()


def _build_kr_etf_lookup() -> dict[str, str]:
    """이름 정규화 → ticker. pykrx 우선, 실패 시 FinanceDataReader."""
    lookup: dict[str, str] = {}
    # 1) pykrx (노이즈 억제, 실패해도 silent)
    try:
        from pykrx import stock
        with quiet_pykrx():
            all_tickers = stock.get_etf_ticker_list()
            for t in all_tickers or []:
                try:
                    n = stock.get_etf_ticker_name(t)
                except Exception:
                    continue
                if n:
                    lookup[_norm(n)] = t
    except Exception:
        pass

    if lookup:
        return lookup

    log.info("pykrx ETF list 미사용 → FinanceDataReader fallback")
    # 2) FinanceDataReader
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("ETF/KR")
    except Exception as e:
        log.warning(f"FinanceDataReader ETF/KR 실패: {e}")
        return lookup

    if df is None or df.empty:
        return lookup
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol")
    name_col = cols.get("name")
    if not (sym_col and name_col):
        log.warning(f"FinanceDataReader ETF/KR 컬럼 인식 실패: {list(df.columns)}")
        return lookup
    for _, r in df.iterrows():
        n = str(r[name_col])
        t = str(r[sym_col]).zfill(6)
        if n and t:
            lookup[_norm(n)] = t
    log.info(f"ETF_KR fallback: FinanceDataReader 에서 {len(lookup)} 매핑")
    return lookup


def resolve_kr_etf_tickers(items: list[dict[str, Any]]) -> pd.DataFrame:
    """config items (name, ticker?) 를 받아 ticker 채워 DataFrame 반환."""
    name_to_ticker = _build_kr_etf_lookup()
    rows: list[dict[str, str | None]] = []
    for it in items:
        name = it["name"]
        ticker = it.get("ticker")
        if not ticker:
            ticker = name_to_ticker.get(_norm(name))
        rows.append({"ticker": ticker, "name": name})
    return pd.DataFrame(rows)


def us_etf_df(items: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{"ticker": it["ticker"], "name": it["name"]} for it in items])
