"""type2_2: plus_days/minus_days 신호 + 가용 현금 전액 매수 / 전량 매도."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import base
from .type2_1 import _init_streak


def run_one(ticker: str, daily: pd.DataFrame, initial_cash: float,
            plus_days: int, minus_days: int,
            start: date | None, end: date | None,
            portfolio: base.Portfolio | None = None) -> base.Portfolio:
    p = portfolio if portfolio is not None else \
        base.Portfolio(ticker=ticker, type_name="type2_2", initial_cash=initial_cash)
    df = base.slice_period(daily, start, end)
    if df.empty:
        return p

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
            p.buy(str(row["date"]), float(close), qty=None, reason=f"+{plus_days}일 연속 유지")
            fired_in_streak = True
        elif not fired_in_streak and sign == "-" and streak_len >= minus_days:
            p.sell(str(row["date"]), float(close), all_out=True, reason=f"-{minus_days}일 연속 유지")
            fired_in_streak = True

    last = df.iloc[-1]
    last_close = pd.to_numeric(pd.Series([last["close"]]), errors="coerce").iloc[0]
    if not pd.isna(last_close):
        p.mark_to_market(str(last["date"]), float(last_close))
    return p
