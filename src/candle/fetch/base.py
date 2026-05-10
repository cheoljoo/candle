"""일봉 + 이벤트 공통 스키마."""
from __future__ import annotations

DAILY_COLUMNS = [
    "date",
    "open", "high", "low", "close",
    "volume",
    "per", "pbr",
    "shares_out", "market_cap",
]

DIVIDEND_COLUMNS = ["ticker", "event_date", "amount", "yield_pct", "payout_ratio"]
