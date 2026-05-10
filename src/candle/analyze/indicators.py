"""이동평균 + UPDOWN 지표."""
from __future__ import annotations

import pandas as pd

# 10개월 ≈ 거래일 200일 (월 평균 21 거래일 × 10 ≈ 210, 보수적으로 200)
MA10M_WINDOW = 200


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """date 오름차순 일봉 DataFrame을 받아 ma10d/ma50d/ma10m/ma10m_updown 채워 반환."""
    if df.empty:
        return df.assign(ma10d=pd.NA, ma50d=pd.NA, ma10m=pd.NA, ma10m_updown=pd.NA)

    out = df.sort_values("date").reset_index(drop=True).copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    out["ma10d"] = close.rolling(window=10, min_periods=10).mean()
    out["ma50d"] = close.rolling(window=50, min_periods=50).mean()
    out["ma10m"] = close.rolling(window=MA10M_WINDOW, min_periods=MA10M_WINDOW).mean()

    def _sign(c, m):
        if pd.isna(c) or pd.isna(m):
            return pd.NA
        return "+" if c >= m else "-"

    out["ma10m_updown"] = [
        _sign(c, m) for c, m in zip(close, out["ma10m"])
    ]
    return out
