"""변곡점 (종가가 MA10M crossover) 컬럼 채우기."""
from __future__ import annotations

import pandas as pd


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """ma10m_updown이 채워진 DataFrame을 받아 inflection 컬럼 추가."""
    if df.empty or "ma10m_updown" not in df.columns:
        return df.assign(inflection=pd.NA)

    out = df.copy()
    prev = out["ma10m_updown"].shift(1)
    cur = out["ma10m_updown"]

    def _flag(p, c):
        if pd.isna(p) or pd.isna(c) or p == c:
            return pd.NA
        if p == "-" and c == "+":
            return "-→+"
        if p == "+" and c == "-":
            return "+→-"
        return pd.NA

    out["inflection"] = [_flag(p, c) for p, c in zip(prev, cur)]
    return out
