"""KR fetch — yfinance 우선(.KS → .KQ), 실패 시 pykrx fallback."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

# yfinance 에서 KR 종목 접미어: KOSPI = .KS, KOSDAQ = .KQ
_KS = ".KS"
_KQ = ".KQ"


# ── yfinance (primary) ───────────────────────────────────────────────
def fetch_daily_yf(ticker: str, start: date, end: date) -> pd.DataFrame:
    """.KS → .KQ 순으로 yfinance 시도. 둘 다 빈 경우 empty DataFrame."""
    import yfinance as yf

    if start > end:
        return pd.DataFrame()

    yf_end = (end + timedelta(days=1)).isoformat()
    for suffix in (_KS, _KQ):
        yf_tk = ticker + suffix
        try:
            raw = yf.download(
                yf_tk,
                start=start.isoformat(),
                end=yf_end,
                progress=False,
                auto_adjust=False,
                actions=False,
            )
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        df = _normalize(raw)
        if df.empty:
            continue
        _attach_fast_info(df, yf_tk)
        return df
    return pd.DataFrame()


def to_yf_tickers(tickers: list[str], suffix: str) -> list[str]:
    """["005930"] → ["005930.KS"] 변환."""
    return [t + suffix for t in tickers]


def strip_yf_suffix(result: dict[str, pd.DataFrame], suffix: str) -> dict[str, pd.DataFrame]:
    """{"005930.KS": df} → {"005930": df} 역변환."""
    slen = len(suffix)
    return {k[:-slen]: v for k, v in result.items() if k.endswith(suffix)}


# ── pykrx (fallback) ─────────────────────────────────────────────────
def fetch_daily_pykrx(ticker: str, start: date, end: date) -> pd.DataFrame:
    """pykrx OHLCV + PER/PBR + 시총/유통주식수 (일별 히스토리컬)."""
    from pykrx import stock
    from ..universe._quiet import quiet_pykrx

    if start > end:
        return _empty_df()

    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    with quiet_pykrx():
        ohlcv = stock.get_market_ohlcv(s, e, ticker)
    if ohlcv is None or ohlcv.empty:
        return _empty_df()

    ohlcv = ohlcv.reset_index().rename(columns={
        "날짜": "date", "시가": "open", "고가": "high", "저가": "low",
        "종가": "close", "거래량": "volume",
    })
    ohlcv["date"] = pd.to_datetime(ohlcv["date"]).dt.strftime("%Y-%m-%d")

    try:
        with quiet_pykrx():
            fund = stock.get_market_fundamental(s, e, ticker).reset_index()
        fund = fund.rename(columns={"날짜": "date", "PER": "per", "PBR": "pbr"})
        fund["date"] = pd.to_datetime(fund["date"]).dt.strftime("%Y-%m-%d")
        fund = fund[["date", "per", "pbr"]]
    except Exception:
        fund = pd.DataFrame(columns=["date", "per", "pbr"])

    try:
        with quiet_pykrx():
            cap = stock.get_market_cap(s, e, ticker).reset_index()
        cap = cap.rename(columns={
            "날짜": "date", "시가총액": "market_cap", "상장주식수": "shares_out",
        })
        cap["date"] = pd.to_datetime(cap["date"]).dt.strftime("%Y-%m-%d")
        cap = cap[["date", "market_cap", "shares_out"]]
    except Exception:
        cap = pd.DataFrame(columns=["date", "market_cap", "shares_out"])

    out = ohlcv[["date", "open", "high", "low", "close", "volume"]]
    out = out.merge(fund, on="date", how="left").merge(cap, on="date", how="left")
    return out.reset_index(drop=True)


def fetch_etf_daily_pykrx(ticker: str, start: date, end: date) -> pd.DataFrame:
    """pykrx KR ETF OHLCV (펀더멘털 없음)."""
    from pykrx import stock
    from ..universe._quiet import quiet_pykrx

    if start > end:
        return _empty_df()

    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    try:
        with quiet_pykrx():
            ohlcv = stock.get_etf_ohlcv(s, e, ticker).reset_index()
    except Exception:
        ohlcv = pd.DataFrame()

    if ohlcv.empty:
        try:
            with quiet_pykrx():
                ohlcv = stock.get_market_ohlcv(s, e, ticker).reset_index()
        except Exception:
            ohlcv = pd.DataFrame()

    if ohlcv.empty:
        return _empty_df()

    ohlcv = ohlcv.rename(columns={
        "날짜": "date", "시가": "open", "고가": "high", "저가": "low",
        "종가": "close", "거래량": "volume", "NAV": "_nav",
    })
    ohlcv["date"] = pd.to_datetime(ohlcv["date"]).dt.strftime("%Y-%m-%d")
    keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in ohlcv.columns]
    out = ohlcv[keep].copy()
    for col in ["per", "pbr", "shares_out", "market_cap"]:
        out[col] = pd.NA
    return out.reset_index(drop=True)


# ── 공개 API (yfinance 우선 + pykrx fallback) ─────────────────────────
def fetch_daily(ticker: str, start: date, end: date) -> pd.DataFrame:
    """yfinance 먼저(.KS→.KQ), 실패하면 pykrx."""
    df = fetch_daily_yf(ticker, start, end)
    if not df.empty:
        return df
    return fetch_daily_pykrx(ticker, start, end)


def fetch_etf_daily(ticker: str, start: date, end: date) -> pd.DataFrame:
    """yfinance 먼저(.KS→.KQ), 실패하면 pykrx."""
    df = fetch_daily_yf(ticker, start, end)
    if not df.empty:
        return df
    return fetch_etf_daily_pykrx(ticker, start, end)


# ── 내부 유틸 ────────────────────────────────────────────────────────
def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "date", "open", "high", "low", "close", "volume",
        "per", "pbr", "shares_out", "market_cap",
    ])


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    if "close" in df.columns:
        df = df.dropna(subset=["close"])
    keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].reset_index(drop=True)


def _attach_fast_info(df: pd.DataFrame, yf_tk: str) -> None:
    """마지막 row에 PER/shares_out/market_cap 스냅샷 추가 (in-place)."""
    import yfinance as yf
    df["per"] = pd.NA
    df["pbr"] = pd.NA
    df["shares_out"] = pd.NA
    df["market_cap"] = pd.NA
    if df.empty:
        return
    try:
        info = yf.Ticker(yf_tk).fast_info
        def _g(k, alt=None):
            v = getattr(info, k, None)
            if v is None and alt:
                v = getattr(info, alt, None)
            return v
        per = _g("trailing_pe")
        so = _g("shares")
        mc = _g("market_cap", "marketCap")
        last = df.index[-1]
        if per is not None:
            df.at[last, "per"] = per
        if so is not None:
            df.at[last, "shares_out"] = so
        if mc is not None:
            df.at[last, "market_cap"] = mc
    except Exception:
        pass
