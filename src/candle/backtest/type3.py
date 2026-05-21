"""type3: 신호 무시. 90일마다 동일 금액 적립식 매수, 매도 없음."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import base


def run_one(ticker: str, daily: pd.DataFrame,
            installment_amount: float, interval_days: int,
            start: date | None, end: date | None,
            portfolio: base.Portfolio | None = None,
            last_buy_date: str | None = None) -> base.Portfolio:
    """매번 installment_amount 만큼의 현금을 추가 입금하고 그 날의 종가로 가능한 만큼 매수.

    portfolio/last_buy_date 가 주어지면 증분 재개 모드.
    """
    p = portfolio if portfolio is not None else \
        base.Portfolio(ticker=ticker, type_name="type3", initial_cash=0.0)
    df = base.slice_period(daily, start, end)
    if df.empty:
        return p

    df = df.reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if last_buy_date is not None:
        # 재개: 마지막 매수일 + interval_days 부터 다음 매수
        next_buy_dt = pd.Timestamp(last_buy_date) + timedelta(days=interval_days)
    else:
        first_dt = df["date"].iloc[0]
        next_buy_dt = first_dt
    last_idx = len(df) - 1

    for i, row in df.iterrows():
        dt = row["date"]
        if dt is pd.NaT:
            continue
        if dt < next_buy_dt:
            continue
        # 적립일 도달 → 입금 후 매수
        close = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        if pd.isna(close):
            next_buy_dt = dt + timedelta(days=interval_days)
            continue
        p.cash += installment_amount  # 입금
        # initial_cash 누적 추적: 입금된 총액으로 갱신 (수익률 분모)
        if p.initial_cash is None:
            p.initial_cash = 0.0
        p.initial_cash = float(p.initial_cash) + installment_amount
        p.buy(dt.strftime("%Y-%m-%d"), float(close), qty=None, reason=f"DCA {interval_days}일 주기")
        next_buy_dt = dt + timedelta(days=interval_days)

    last = df.iloc[-1]
    last_close = pd.to_numeric(pd.Series([last["close"]]), errors="coerce").iloc[0]
    if not pd.isna(last_close):
        p.mark_to_market(last["date"].strftime("%Y-%m-%d"), float(last_close))
    return p
