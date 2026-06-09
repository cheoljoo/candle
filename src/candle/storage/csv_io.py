"""CSV read / atomic write / append-with-dedup helpers."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    # KR ticker('000120' 등)는 선행 0 때문에 pandas 가 int 로 읽을 수 있음.
    # ticker 컬럼이 있으면 항상 str 로 강제.
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str)
    return df


def atomic_write(df: pd.DataFrame, path: Path) -> None:
    """원자적 CSV 쓰기. 같은 디렉터리에 .tmp → os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def upsert_by_keys(
    path: Path,
    new_df: pd.DataFrame,
    key_cols: list[str],
    sort_cols: list[str] | None = None,
    overwrite: bool = False,
) -> pd.DataFrame:
    """기존 CSV에 new_df를 합쳐 dedup후 atomic write.

    overwrite=False (default): 같은 key가 이미 있으면 기존값 유지 (fetch용).
    overwrite=True: 같은 key가 있으면 new_df 값으로 덮어씀 (analyze용).
    """
    if new_df.empty:
        return read(path)

    existing = read(path)
    if existing.empty:
        merged = new_df.copy()
    elif overwrite:
        # new_df의 key와 겹치는 기존행 제거 후 합치기
        merge_keys = existing[key_cols].merge(new_df[key_cols], on=key_cols, how="inner")
        if not merge_keys.empty:
            existing = existing.merge(
                merge_keys.assign(_drop=True), on=key_cols, how="left"
            )
            existing = existing[existing["_drop"].isna()].drop(columns=["_drop"])
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=key_cols, keep="first")

    if sort_cols:
        merged = merged.sort_values(sort_cols).reset_index(drop=True)
    atomic_write(merged, path)
    return merged
