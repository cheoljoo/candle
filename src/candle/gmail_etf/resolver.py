"""Ticker 시장 판별 및 종목 정보 조회.

KR 판별: 6자리 영숫자 (예: 005930, 069500, 0190Y0)
         ※ KRX는 숫자+영문 혼합 코드도 사용 (예: ETF 0190Y0)
US 판별: 영문자 1~5글자 (예: VOO, AAPL, SCHD)
"""
from __future__ import annotations

import logging
import re
from typing import TypedDict

log = logging.getLogger(__name__)

# KR: 6자리 영숫자 (숫자+영문 혼합 포함, 예: 0190Y0)
_KR_RE = re.compile(r"^[0-9A-Z]{6}$")
_US_RE = re.compile(r"^[A-Z]{1,5}$")


class TickerInfo(TypedDict):
    ticker: str
    name: str
    market: str       # "KR" | "US"
    group_name: str   # "ETF_KR" | "ETF_US"
    currency: str     # "KRW" | "USD"


def detect_market(ticker: str) -> str | None:
    """ticker 형식으로 시장 판별. 판별 불가 시 None."""
    t = ticker.strip().upper()
    if _KR_RE.match(t):
        return "KR"
    if _US_RE.match(t):
        return "US"
    return None


def resolve_ticker(ticker: str, market: str) -> TickerInfo | None:
    """ticker + market 으로 종목명·그룹 확인. 찾지 못하면 None.

    KR: pykrx → FinanceDataReader fallback
    US: yfinance
    """
    t = ticker.strip().upper()
    if market == "KR":
        return _resolve_kr(t)
    if market == "US":
        return _resolve_us(t)
    return None


def _resolve_kr(ticker: str) -> TickerInfo | None:
    """KR 종목 이름 조회. ETF 여부 확인 후 group_name 결정."""
    name: str | None = None

    # 1) pykrx
    try:
        from pykrx import stock
        from ..universe._quiet import quiet_pykrx
        import pandas as pd
        with quiet_pykrx():
            result = stock.get_market_ticker_name(ticker)
        if isinstance(result, pd.DataFrame) or isinstance(result, pd.Series):
            pass  # pykrx returned empty DataFrame — not found
        elif result and isinstance(result, str):
            name = result
    except Exception:
        pass

    # 2) FinanceDataReader fallback
    if not name:
        try:
            import FinanceDataReader as fdr
            df = fdr.StockListing("KRX")
            if df is not None and not df.empty:
                cols = {c.lower(): c for c in df.columns}
                sym_col = cols.get("symbol") or cols.get("code") or cols.get("ticker")
                name_col = cols.get("name")
                if sym_col and name_col:
                    row = df[df[sym_col].astype(str).str.zfill(6) == ticker]
                    if not row.empty:
                        name = str(row.iloc[0][name_col])
        except Exception as e:
            log.debug("[resolver] KR FDR 조회 실패 %s: %s", ticker, e)

    # 3) FinanceDataReader ETF/KR 목록 fallback
    if not name:
        try:
            import FinanceDataReader as fdr
            df = fdr.StockListing("ETF/KR")
            if df is not None and not df.empty:
                cols = {c.lower(): c for c in df.columns}
                sym_col = cols.get("symbol") or cols.get("code") or cols.get("ticker")
                name_col = cols.get("name")
                if sym_col and name_col:
                    row = df[df[sym_col].astype(str) == ticker]
                    if not row.empty:
                        name = str(row.iloc[0][name_col])
        except Exception as e:
            log.debug("[resolver] KR FDR ETF/KR 조회 실패 %s: %s", ticker, e)

    # 4) yfinance .KS fallback (영숫자 혼합 코드 등 KRX 특수 ticker 대응)
    if not name:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker + ".KS").info
            name = info.get("longName") or info.get("shortName")
        except Exception as e:
            log.debug("[resolver] KR yfinance .KS 조회 실패 %s: %s", ticker, e)

    if not name:
        log.info("[resolver] KR ticker 정보 없음: %s", ticker)
        return None

    # 사용자가 메일로 요청하는 KR 종목은 ETF_KR 로 처리
    group_name = "ETF_KR"

    return TickerInfo(
        ticker=ticker,
        name=name,
        market="KR",
        group_name=group_name,
        currency="KRW",
    )


def _resolve_us(ticker: str) -> TickerInfo | None:
    """US 종목 이름 조회. ETF 여부 상관없이 ETF_US 로 처리."""
    name: str | None = None
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        # fast_info 에는 longName 이 없을 수 있음
        name = getattr(info, "exchange", None) and ticker  # 존재하면 일단 확인용
        # 정식 이름 시도
        full_info = yf.Ticker(ticker).info
        name = (
            full_info.get("longName")
            or full_info.get("shortName")
            or full_info.get("symbol")
        )
    except Exception as e:
        log.debug("[resolver] US yfinance 조회 실패 %s: %s", ticker, e)

    if not name:
        log.info("[resolver] US ticker 정보 없음: %s", ticker)
        return None

    return TickerInfo(
        ticker=ticker,
        name=name,
        market="US",
        group_name="ETF_US",
        currency="USD",
    )
