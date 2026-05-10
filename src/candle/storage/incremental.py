"""ticker별 일봉 CSV의 마지막 date 기반 증분 fetch."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from . import csv_io


def last_date(daily_path: Path) -> date | None:
    df = csv_io.read(daily_path)
    if df.empty or "date" not in df.columns:
        return None
    s = pd.to_datetime(df["date"], errors="coerce").dropna()
    if s.empty:
        return None
    return s.max().date()


def fetch_window(
    daily_path: Path,
    default_history_days: int,
    today: date,
    from_date: Optional[date] = None,
    history_start: Optional[date] = None,
) -> tuple[date, date]:
    """fetch가 받아와야 하는 [from, to] 구간.

    우선순위:
      1. from_date     — CLI --from 강제 지정 (기존 파일 있어도 이 날짜부터, 백필용)
      2. last+1        — 기존 파일의 마지막 date 다음 날 (일반 증분)
      3. history_start — config history_start (신규 파일에만)
      4. today - default_history_days — 신규 파일 fallback
    """
    last = last_date(daily_path)
    if from_date is not None:
        start = from_date
    elif last is not None:
        start = last + timedelta(days=1)
    elif history_start is not None:
        start = history_start
    else:
        start = today - timedelta(days=default_history_days)
    return start, today
