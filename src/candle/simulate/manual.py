"""Manual decisions — 사용자가 편집하는 CSV에서 읽음.

`output/simulate/manual_input.csv` 를 만들고 행을 추가하면 simulate 진입 시 읽힘.
체결은 `다음 거래일 시작가`에 일어나므로 date 는 의사결정 날짜이지 체결일이 아님.

스키마:
date,ticker,action,qty,reason
2026-05-08,005930,buy,5,"분할매수 — PBR 낮아서"
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .. import config


def manual_input_path(cfg: config.Config) -> Path:
    return cfg.output_dir / "simulate" / "manual_input.csv"


def load(cfg: config.Config, on_date: date) -> pd.DataFrame:
    p = manual_input_path(cfg)
    if not p.exists():
        return pd.DataFrame(columns=["date", "ticker", "action", "qty", "reason"])
    df = pd.read_csv(p)
    if df.empty:
        return df
    df = df[df["date"] == on_date.isoformat()].copy()
    return df.reset_index(drop=True)


def ensure_template(cfg: config.Config) -> Path:
    p = manual_input_path(cfg)
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("date,ticker,action,qty,reason\n", encoding="utf-8")
    return p
