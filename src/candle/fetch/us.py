"""US fetch — yfinance."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def fetch_daily(ticker: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf

    if start > end:
        return pd.DataFrame(columns=[
            "date", "open", "high", "low", "close", "volume",
            "per", "pbr", "shares_out", "market_cap",
        ])

    # yfinance end는 exclusive. +1.
    yf_end = (end + timedelta(days=1)).isoformat()
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=yf_end,
        progress=False,
        auto_adjust=False,
        actions=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "date", "open", "high", "low", "close", "volume",
            "per", "pbr", "shares_out", "market_cap",
        ])

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # PER/PBR/시총: yfinance는 historical 펀더멘털을 깔끔히 안 줌.
    # 현재 스냅샷만 채우고, 일별로는 NaN. (req.md "오늘 현재값만 필요한 값" 케이스)
    try:
        info = yf.Ticker(ticker).fast_info
        per = getattr(info, "trailing_pe", None) or info.get("trailingPe", None) if hasattr(info, "get") else None
        market_cap = info.get("market_cap", None) if hasattr(info, "get") else getattr(info, "market_cap", None)
        shares_out = info.get("shares", None) if hasattr(info, "get") else getattr(info, "shares", None)
    except Exception:
        per, market_cap, shares_out = None, None, None

    df["per"] = pd.NA
    df["pbr"] = pd.NA
    df["shares_out"] = pd.NA
    df["market_cap"] = pd.NA
    if not df.empty and (per is not None or market_cap is not None):
        last_idx = df.index[-1]
        if per is not None:
            df.at[last_idx, "per"] = per
        if shares_out is not None:
            df.at[last_idx, "shares_out"] = shares_out
        if market_cap is not None:
            df.at[last_idx, "market_cap"] = market_cap

    return df[["date", "open", "high", "low", "close", "volume",
               "per", "pbr", "shares_out", "market_cap"]].reset_index(drop=True)


def fetch_daily_batch(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """여러 ticker 를 yfinance 한 번의 batch download 로 받아 ticker→OHLCV df 반환.

    펀더멘털(per/shares/market_cap)은 채우지 않음 — 상위에서 fast_info 로 별도 보강.
    """
    import yfinance as yf

    if not tickers or start > end:
        return {}

    yf_end = (end + timedelta(days=1)).isoformat()
    df = yf.download(
        tickers,
        start=start.isoformat(),
        end=yf_end,
        progress=False,
        auto_adjust=False,
        actions=False,
        group_by="ticker",
        threads=True,
    )
    if df is None or df.empty:
        return {t: pd.DataFrame() for t in tickers}

    out: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1:
        out[tickers[0]] = _normalize_ohlcv(df)
        return out

    top_levels = set(df.columns.get_level_values(0)) if isinstance(df.columns, pd.MultiIndex) else set()
    for tk in tickers:
        if tk in top_levels:
            out[tk] = _normalize_ohlcv(df[tk])
        else:
            out[tk] = pd.DataFrame()
    return out


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["close"]) if "close" in df.columns else df
    keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].reset_index(drop=True)


def fetch_fast_info(ticker: str) -> tuple[float | None, float | None, float | None]:
    """(per, shares_out, market_cap) — yfinance fast_info 스냅샷."""
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).fast_info
    except Exception:
        return None, None, None

    def _get(key: str, alt: str | None = None):
        v = None
        if hasattr(info, "get"):
            v = info.get(key, None)
            if v is None and alt:
                v = info.get(alt, None)
        if v is None:
            v = getattr(info, key, None)
            if v is None and alt:
                v = getattr(info, alt, None)
        return v

    return _get("trailingPe", "trailing_pe"), _get("shares"), _get("market_cap", "marketCap")


def fetch_dividends(ticker: str) -> pd.DataFrame:
    import yfinance as yf
    try:
        s = yf.Ticker(ticker).dividends
    except Exception:
        return pd.DataFrame(columns=["ticker", "event_date", "amount", "yield_pct", "payout_ratio"])
    if s is None or s.empty:
        return pd.DataFrame(columns=["ticker", "event_date", "amount", "yield_pct", "payout_ratio"])
    df = s.reset_index()
    df.columns = ["event_date", "amount"]
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = ticker
    df["yield_pct"] = pd.NA
    df["payout_ratio"] = pd.NA
    return df[["ticker", "event_date", "amount", "yield_pct", "payout_ratio"]]
