"""그룹 내 시총 순위 (ETF 제외)."""
from __future__ import annotations

import pandas as pd

from .. import config
from ..storage import csv_io, paths


def compute_for_group(cfg: config.Config, group_name: str, market: str) -> dict[str, pd.DataFrame]:
    """그룹 내 모든 ticker의 일별 (date, market_cap)을 모아 그룹 내 순위 산출.

    반환: ticker → DataFrame(date, rank_in_group)
    """
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {}
    members = inst[(inst["group_name"] == group_name) & (inst["market"] == market)]["ticker"].tolist()
    if not members:
        return {}

    frames: list[pd.DataFrame] = []
    for t in members:
        p = paths.daily_csv(cfg.data_dir, market, str(t))
        df = csv_io.read(p)
        if df.empty or "market_cap" not in df.columns:
            continue
        f = df[["date", "market_cap"]].copy()
        f["ticker"] = t
        frames.append(f)
    if not frames:
        return {}

    all_df = pd.concat(frames, ignore_index=True)
    all_df["market_cap"] = pd.to_numeric(all_df["market_cap"], errors="coerce")
    all_df = all_df.dropna(subset=["market_cap"])
    if all_df.empty:
        return {}

    all_df["rank_in_group"] = (
        all_df.groupby("date")["market_cap"]
        .rank(method="dense", ascending=False)
        .astype("Int64")
    )

    out: dict[str, pd.DataFrame] = {}
    for t, g in all_df.groupby("ticker"):
        out[str(t)] = g[["date", "rank_in_group"]].reset_index(drop=True)
    return out
