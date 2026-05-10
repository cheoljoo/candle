"""type2_1: plus_days 연속 + 유지 시 매수, minus_days 연속 - 유지 시 매도. 10주 단위.

전환 후 N일 연속 같은 방향이면 신호 발생 (한 번만 발화 / 다음 전환 전까지 재발화 X).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import base


def _init_streak(daily: pd.DataFrame, from_date: date | None,
                 lookback_rows: int) -> tuple[str | None, int, bool]:
    """start 이전 lookback_rows 개 row 로 streak 초기 상태 계산 (거래 기록 없음)."""
    if from_date is None:
        return None, 0, False
    ctx = base.slice_period(daily, None, from_date)
    if not ctx.empty:
        ctx = ctx.iloc[-min(lookback_rows, len(ctx)):]  # 마지막 N개만
    else:
        return None, 0, False

    streak_sign: str | None = None
    streak_len = 0
    fired = False
    for _, row in ctx.iterrows():
        sign = row.get("ma10m_updown")
        if pd.isna(sign):
            sign = None
        if sign != streak_sign:
            streak_sign = sign
            streak_len = 1
            fired = False
        else:
            streak_len += 1
    return streak_sign, streak_len, fired


def run_one(ticker: str, daily: pd.DataFrame, qty: int,
            plus_days: int, minus_days: int,
            start: date | None, end: date | None,
            portfolio: base.Portfolio | None = None) -> base.Portfolio:
    p = portfolio if portfolio is not None else \
        base.Portfolio(ticker=ticker, type_name="type2_1", initial_cash=None)
    df = base.slice_period(daily, start, end)
    if df.empty:
        return p

    # 재개 시: start 이전 데이터로 streak 상태 초기화 (거래 기록 X)
    streak_sign, streak_len, fired_in_streak = _init_streak(
        daily, start, max(plus_days, minus_days) * 2
    )

    for _, row in df.iterrows():
        sign = row.get("ma10m_updown")
        if pd.isna(sign):
            sign = None
        if sign != streak_sign:
            streak_sign = sign
            streak_len = 1
            fired_in_streak = False
        else:
            streak_len += 1

        close = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        if pd.isna(close):
            continue

        if not fired_in_streak and sign == "+" and streak_len >= plus_days:
            p.buy(str(row["date"]), float(close), float(qty))
            fired_in_streak = True
        elif not fired_in_streak and sign == "-" and streak_len >= minus_days:
            p.sell(str(row["date"]), float(close), float(qty))
            fired_in_streak = True

    last = df.iloc[-1]
    last_close = pd.to_numeric(pd.Series([last["close"]]), errors="coerce").iloc[0]
    if not pd.isna(last_close) and p.qty > 0:
        p.mark_to_market(str(last["date"]), float(last_close))
    return p
