"""type1_2: 변곡점 신호 + 가용 현금 전액 매수 / 전량 매도."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import base


def run_one(ticker: str, daily: pd.DataFrame, initial_cash: float,
            start: date | None, end: date | None,
            portfolio: base.Portfolio | None = None) -> base.Portfolio:
    p = portfolio if portfolio is not None else \
        base.Portfolio(ticker=ticker, type_name="type1_2", initial_cash=initial_cash)
    df = base.slice_period(daily, start, end)
    if df.empty:
        return p
    for _, row in df.iterrows():
        infl = row.get("inflection")
        if pd.isna(infl):
            infl = None
        close = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        if pd.isna(close):
            continue
        if infl == "-→+":
            p.buy(str(row["date"]), float(close), qty=None)
        elif infl == "+→-":
            p.sell(str(row["date"]), float(close), all_out=True)
    last = df.iloc[-1]
    last_close = pd.to_numeric(pd.Series([last["close"]]), errors="coerce").iloc[0]
    if not pd.isna(last_close):
        p.mark_to_market(str(last["date"]), float(last_close))
    return p
