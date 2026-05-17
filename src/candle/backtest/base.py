"""Backtest 공통 — 포지션·현금·trade ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

import pandas as pd

TRADE_COLUMNS = [
    "type", "date", "ticker", "side",
    "price", "qty", "amount",
    "holding_qty", "holding_value", "cash", "return_pct", "buy_sell_return_pct",
]


@dataclass
class Portfolio:
    """단일 종목 포트폴리오. 신호 기반 매매 전략 공용."""
    ticker: str
    type_name: str
    initial_cash: float | None = None   # None이면 현금 추적 비활성 (type1_1, type2_1 등 고정수량)
    cash: float = 0.0
    qty: float = 0.0
    avg_cost: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    trades: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.initial_cash is not None:
            self.cash = float(self.initial_cash)
        self._last_buy_total: float | None = None

    def _record(self, dt: str, side: str, price: float, qty: float,
                buy_sell_return_pct: float | None = None):
        amount = price * qty
        self.trades.append({
            "type": self.type_name,
            "date": dt,
            "ticker": self.ticker,
            "side": side,
            "price": float(price),
            "qty": float(qty),
            "amount": float(amount),
            "holding_qty": float(self.qty),
            "holding_value": float(self.qty * price),
            "cash": float(self.cash) if self.initial_cash is not None else None,
            "return_pct": self._current_return_pct(price),
            "buy_sell_return_pct": buy_sell_return_pct,
        })

    def _current_return_pct(self, price: float) -> float | None:
        if self.initial_cash is None:
            # 고정수량 모드는 평균단가 기준 미실현 수익률
            if self.qty <= 0 or self.avg_cost <= 0:
                return None
            return float((price - self.avg_cost) / self.avg_cost * 100.0)
        # 현금추적 모드는 초기자본 대비 총자산 수익률
        total = self.cash + self.qty * price
        return float((total - self.initial_cash) / self.initial_cash * 100.0)

    def buy(self, dt: str, price: float, qty: float | None = None):
        """qty=None이면 현금 전액으로 가능한 만큼 매수 (type1_2, type2_2 용)."""
        if qty is None:
            if self.cash <= 0 or price <= 0:
                return
            qty = self.cash // price
            if qty <= 0:
                return
        amount = price * qty
        if self.initial_cash is not None:
            if self.cash < amount:
                return
            self.cash -= amount
        # 평균단가 갱신
        new_qty = self.qty + qty
        if new_qty > 0:
            self.avg_cost = (self.avg_cost * self.qty + price * qty) / new_qty
        self.qty = new_qty
        self.buy_count += 1
        # 다음 sell의 buy_sell_return_pct 계산을 위해 buy 시점 총자산 기록
        if self.initial_cash is not None:
            self._last_buy_total = float(self.qty * price + self.cash)
        self._record(dt, "buy", price, qty)

    def sell(self, dt: str, price: float, qty: float | None = None, all_out: bool = False):
        if all_out or qty is None:
            qty = self.qty
        if qty <= 0 or self.qty <= 0:
            return
        qty = min(qty, self.qty)
        amount = price * qty
        if self.initial_cash is not None:
            self.cash += amount
        self.qty -= qty
        if self.qty == 0:
            self.avg_cost = 0.0
        self.sell_count += 1
        # Buy→Sell 사이클 수익률 계산
        buy_sell_ret: float | None = None
        if (self.initial_cash is not None
                and self._last_buy_total is not None
                and self._last_buy_total > 0):
            sell_total = float(self.qty * price + self.cash)
            buy_sell_ret = (sell_total - self._last_buy_total) / self._last_buy_total * 100.0
            self._last_buy_total = None
        self._record(dt, "sell", price, qty, buy_sell_return_pct=buy_sell_ret)

    def mark_to_market(self, dt: str, price: float):
        """to-date 도달 시 보유분 종가 평가 (실제 매도 아님)."""
        self._record(dt, "mark_to_market", price, 0.0)

    def total_value(self, last_price: float) -> float:
        if self.initial_cash is None:
            return float(self.qty * last_price)
        return float(self.cash + self.qty * last_price)

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(columns=TRADE_COLUMNS)
        return pd.DataFrame(self.trades)[TRADE_COLUMNS]

    @classmethod
    def from_trades(cls, ticker: str, type_name: str,
                    initial_cash: float | None,
                    trades_df: "pd.DataFrame") -> "Portfolio":
        """기존 trades ledger 마지막 row 에서 Portfolio 상태를 복원.

        복원 항목: qty, cash, avg_cost, buy_count, sell_count.
        trades 는 비워 둔다 (새 거래만 append 할 것이므로).
        """
        p = cls(ticker=ticker, type_name=type_name, initial_cash=None)
        p.initial_cash = float(initial_cash) if initial_cash is not None else None

        if trades_df is None or trades_df.empty:
            if initial_cash is not None:
                p.cash = float(initial_cash)
            return p

        last = trades_df.iloc[-1]
        p.qty = float(pd.to_numeric(pd.Series([last.get("holding_qty")]),
                                    errors="coerce").iloc[0] or 0.0)
        if initial_cash is not None:
            p.cash = float(pd.to_numeric(pd.Series([last.get("cash")]),
                                         errors="coerce").fillna(initial_cash).iloc[0])
        p.buy_count  = int((trades_df["side"] == "buy").sum())
        p.sell_count = int((trades_df["side"] == "sell").sum())

        # avg_cost: 마지막 매도 이후 매수들의 가중평균
        sells = trades_df[trades_df["side"] == "sell"]
        last_sell_pos = sells.index[-1] if not sells.empty else -1
        buys_after = trades_df[
            (trades_df.index > last_sell_pos) & (trades_df["side"] == "buy")
        ]
        if not buys_after.empty and p.qty > 0:
            bqty = pd.to_numeric(buys_after["qty"],    errors="coerce").sum()
            bamt = pd.to_numeric(buys_after["amount"], errors="coerce").sum()
            p.avg_cost = float(bamt / bqty) if bqty > 0 else 0.0
        # _last_buy_total 복원: 미결 buy 포지션이 있으면 마지막 buy 행의 holding_value + cash
        if p.qty > 0 and not buys_after.empty and p.initial_cash is not None:
            last_buy_row = buys_after.iloc[-1]
            hv = float(pd.to_numeric(pd.Series([last_buy_row.get("holding_value")]),
                                     errors="coerce").fillna(0).iloc[0])
            ca = float(pd.to_numeric(pd.Series([last_buy_row.get("cash")]),
                                     errors="coerce").fillna(0).iloc[0])
            total = hv + ca
            if total > 0:
                p._last_buy_total = total
        return p


def slice_period(daily: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    if daily.empty:
        return daily
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)
