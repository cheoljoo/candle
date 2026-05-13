"""Analyze 진입 — daily/*.csv를 읽어 지표/변곡점/순위를 채우고 다시 저장 + 요약 csv.

증분(incremental) 처리 — data/analyze_meta.csv 에 종목별 (analyzed_from, analyzed_to) 기록:
- from/to 모두 동일   → skip
- from 이 당겨짐(백필) → new_start=0 전체 재계산
- to 만 늘어남(증분)   → prev_to 다음 row 부터만 계산
- meta 없음(첫 실행)   → _first_unanalyzed_row 로 판단 후 meta 초기화
- --refresh            → skip 완전 무시, new_start=0 강제
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from ..io_report import announce
from ..storage import csv_io, paths
from . import indicators, inflection, ranking

log = logging.getLogger(__name__)

DAILY_FULL_COLUMNS = [
    "date", "open", "high", "low", "close", "volume",
    "per", "pbr", "shares_out", "market_cap",
    "ma10d", "ma50d", "ma10m", "ma10m_updown", "inflection", "rank_in_group",
]

LOOKBACK = 220  # MA10M window(200) + inflection shift 여유

# meta CSV 컬럼
_META_COLS = ["ticker", "market", "analyzed_from", "analyzed_to"]


def run(cfg: config.Config, market: str, today: date,
        debug: bool = False, refresh: bool = False) -> dict[str, int]:
    announce(
        f"analyze --market {market}",
        inputs=[
            ("data/instruments.csv", "분석 대상 ticker 목록"),
            ("data/daily/{KR|US}/{ticker}.csv",
             "fetch가 적재한 일봉 — 지표·변곡점·순위 컬럼은 비어있는 상태"),
            ("data/analyze_meta.csv",
             "종목별 직전 분석 범위 (analyzed_from/to) — 증분 판단에 사용"),
        ],
        outputs=[
            ("data/daily/{KR|US}/{ticker}.csv (in-place 갱신)",
             "지표 추가 — ma10d, ma50d, ma10m, ma10m_updown(+/-), inflection(-→+/+→-), rank_in_group"),
            ("data/analyze_meta.csv (갱신)",
             "분석 완료 후 각 ticker 의 analyzed_from/to 업데이트"),
            (f"output/analyze/{today.isoformat()}/summary.csv",
             "기준일 마지막 거래일 요약 — close/MA/UPDOWN/inflection/rank/PER/PBR/거래량+vol20+vol_ratio"),
        ],
    )
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {"analyzed": 0, "skipped": 0}

    if market != "all":
        inst = inst[inst["market"] == market.upper()]

    # ── 1) meta 로드 ──────────────────────────────────────────────────
    meta = _load_meta(cfg.data_dir)
    # 이번 run 에서 갱신된 항목만 별도 수집 → 마지막에 merge 저장
    updated_meta: dict[tuple[str, str], tuple[str, str]] = {}

    # ── 2) 그룹별 시총 순위 사전 계산 ───────────────────────────────────
    rank_map: dict[tuple[str, str], pd.DataFrame] = {}
    if debug:
        print(f"[analyze][debug] 그룹별 시총 순위 사전 계산 시작 (market={market})")
    for (g, m), _ in inst.groupby(["group_name", "market"]):
        if g.startswith("ETF"):
            if debug:
                print(f"[analyze][debug] group={g}/{m} skip (ETF)")
            continue
        if debug:
            print(f"[analyze][debug] ranking compute group={g}/{m} start")
        rt0 = time.perf_counter()
        r = ranking.compute_for_group(cfg, str(g), str(m))
        for t, df_r in r.items():
            rank_map[(t, str(m))] = df_r
        if debug:
            print(f"[analyze][debug] ranking compute group={g}/{m} end ({time.perf_counter()-rt0:.2f}s) — tickers={len(r)}")

    # ── 3) ticker별 증분 지표/변곡점 채우기 ─────────────────────────────
    analyzed = 0
    skipped = 0
    summary_rows: list[dict] = []
    total = len(inst)
    if debug:
        print(f"[analyze][debug] ticker 분석 시작: {total}개")

    for i, (_, row) in enumerate(inst.iterrows(), start=1):
        ticker = str(row["ticker"])
        mkt   = str(row["market"])
        group = str(row["group_name"])
        path  = paths.daily_csv(cfg.data_dir, mkt, ticker)

        if debug:
            print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) start", flush=True)
        t0 = time.perf_counter()

        df = csv_io.read(path)
        if df.empty:
            if debug:
                print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) end ({time.perf_counter()-t0:.2f}s) — empty daily", flush=True)
            continue

        fetch_from = str(df.iloc[0]["date"])
        fetch_to   = str(df.iloc[-1]["date"])
        prev       = meta.get((ticker, mkt))  # (analyzed_from, analyzed_to) | None

        # ── skip / new_start 결정 ────────────────────────────────────
        reason = ""
        if refresh:
            new_start = 0
            reason = f"REFRESH (전체 {len(df)}행)"

        elif prev is None:
            # meta 없음 → _first_unanalyzed_row 로 초기화
            new_start = _first_unanalyzed_row(df)
            if new_start >= len(df):
                # 이미 전부 분석됨 — meta 초기화 후 skip
                updated_meta[(ticker, mkt)] = (fetch_from, fetch_to)
                skipped += 1
                summary_rows.append(_build_summary_row(df, row))
                if debug:
                    print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) SKIP({time.perf_counter()-t0:.2f}s) — meta 초기화(이미분석완료)", flush=True)
                continue
            reason = f"meta없음→new_start={new_start}"

        elif prev[0] == fetch_from and prev[1] == fetch_to:
            # from/to 모두 동일 → 완전 skip
            updated_meta[(ticker, mkt)] = prev
            skipped += 1
            summary_rows.append(_build_summary_row(df, row))
            if debug:
                print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) SKIP({time.perf_counter()-t0:.2f}s) — from={fetch_from} to={fetch_to} 변동없음", flush=True)
            continue

        elif prev[0] != fetch_from:
            # from 이 당겨짐(백필) → 전체 재계산
            new_start = 0
            reason = f"from 변경({prev[0]}→{fetch_from})"

        else:
            # to 만 늘어남 → prev_to 다음 row부터
            later = df[df["date"].astype(str) > prev[1]]
            if later.empty:
                updated_meta[(ticker, mkt)] = prev
                skipped += 1
                summary_rows.append(_build_summary_row(df, row))
                continue
            new_start = int(later.index[0])
            reason = f"to 변경({prev[1]}→{fetch_to})"

        n_new = len(df) - new_start

        if debug:
            print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) {reason} — new={n_new}행", flush=True)

        # ── 증분 지표 계산 ────────────────────────────────────────────
        ctx_start = max(0, new_start - LOOKBACK)
        working   = df.iloc[ctx_start:].reset_index(drop=True)
        computed  = indicators.compute(working)
        computed  = inflection.compute(computed)
        n_context = new_start - ctx_start
        new_comp  = computed.iloc[n_context:].reset_index(drop=True)

        out = df.copy()
        for col in ["ma10d", "ma50d", "ma10m", "ma10m_updown", "inflection"]:
            if col not in out.columns:
                out[col] = pd.NA
            if col in new_comp.columns:
                col_idx = out.columns.get_loc(col)
                col_dtype = out.dtypes.iloc[col_idx]
                if pd.api.types.is_float_dtype(col_dtype):
                    # float 컬럼: pd.NA → np.nan 으로 변환해 dtype 불일치 경고 방지
                    vals: np.ndarray = new_comp[col].to_numpy(dtype=float, na_value=np.nan)
                else:
                    # object/string 컬럼: 그대로 object array
                    vals = new_comp[col].to_numpy(dtype=object)
                out.iloc[new_start:new_start + n_new, col_idx] = vals

        # ── rank merge (새 날짜만) ────────────────────────────────────
        if "rank_in_group" not in out.columns:
            out["rank_in_group"] = pd.NA
        rdf = rank_map.get((ticker, mkt))
        if rdf is not None and not rdf.empty:
            new_dates = set(out.iloc[new_start:]["date"].astype(str))
            rdf_new   = rdf[rdf["date"].astype(str).isin(new_dates)]
            if not rdf_new.empty:
                rank_dict = dict(zip(rdf_new["date"].astype(str), rdf_new["rank_in_group"]))
                out.loc[out.index[new_start:], "rank_in_group"] = (
                    out.iloc[new_start:]["date"].astype(str).map(rank_dict)
                )

        # ── 컬럼 정렬 + 저장 ─────────────────────────────────────────
        for c in DAILY_FULL_COLUMNS:
            if c not in out.columns:
                out[c] = pd.NA
        out = out[DAILY_FULL_COLUMNS]

        csv_io.atomic_write(out, path)
        analyzed += 1
        updated_meta[(ticker, mkt)] = (fetch_from, fetch_to)
        summary_rows.append(_build_summary_row(out, row))

        if debug:
            print(f"[analyze][debug] ({i}/{total}) {mkt}/{ticker} ({group}) end ({time.perf_counter()-t0:.2f}s) — rows={len(out)} last={fetch_to}", flush=True)

    # ── 4) meta 저장 (기존 + 이번 run 갱신분 merge) ──────────────────
    final_meta = {**meta, **updated_meta}
    _save_meta(cfg.data_dir, final_meta)

    # ── 5) 요약 csv 출력 ──────────────────────────────────────────────
    if summary_rows:
        sdf = pd.DataFrame(summary_rows)
        out_dir = paths.analyze_dir(cfg.output_dir, today.isoformat())
        out_dir.mkdir(parents=True, exist_ok=True)
        keep = ["date", "ticker", "name", "group_name", "close",
                "ma10d", "ma50d", "ma10m", "ma10m_updown", "inflection",
                "rank_in_group", "per", "pbr", "volume", "vol20_avg", "vol_ratio"]
        keep = [c for c in keep if c in sdf.columns]
        csv_io.atomic_write(sdf[keep], out_dir / "summary.csv")

    return {"analyzed": analyzed, "skipped": skipped}


# ── meta I/O ────────────────────────────────────────────────────────────
_MetaKey = tuple[str, str]          # (ticker, market)
_MetaVal = tuple[str, str]          # (analyzed_from, analyzed_to)


def _meta_path(data_dir: Path) -> Path:
    return data_dir / "analyze_meta.csv"


def _load_meta(data_dir: Path) -> dict[_MetaKey, _MetaVal]:
    p = _meta_path(data_dir)
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
        return {
            (str(r["ticker"]), str(r["market"])): (str(r["analyzed_from"]), str(r["analyzed_to"]))
            for _, r in df.iterrows()
        }
    except Exception as e:
        log.warning(f"analyze_meta.csv 로드 실패: {e}")
        return {}


def _save_meta(data_dir: Path, meta: dict[_MetaKey, _MetaVal]) -> None:
    rows = [{"ticker": k[0], "market": k[1],
             "analyzed_from": v[0], "analyzed_to": v[1]}
            for k, v in meta.items()]
    df = pd.DataFrame(rows, columns=_META_COLS)
    df = df.sort_values(["market", "ticker"]).reset_index(drop=True)
    csv_io.atomic_write(df, _meta_path(data_dir))


# ── 헬퍼 ────────────────────────────────────────────────────────────────
def _first_unanalyzed_row(df: pd.DataFrame) -> int:
    """ma10d 가 NA 인 첫 번째 row 의 iloc 위치. 전부 채워지면 len(df)."""
    if "ma10d" not in df.columns:
        return 0
    na_mask = df["ma10d"].isna()
    if not na_mask.any():
        return len(df)
    return int(na_mask.to_numpy().argmax())


def _build_summary_row(df: pd.DataFrame, inst_row: pd.Series) -> dict:
    last = df.iloc[-1].to_dict()
    last["ticker"]     = str(inst_row["ticker"])
    last["name"]       = str(inst_row["name"])
    last["group_name"] = str(inst_row["group_name"])
    v    = pd.to_numeric(df["volume"], errors="coerce")
    vol20 = v.rolling(20, min_periods=20).mean()
    last["vol20_avg"] = float(vol20.iloc[-1]) if not pd.isna(vol20.iloc[-1]) else None
    last["vol_ratio"] = (
        float(v.iloc[-1] / vol20.iloc[-1])
        if not pd.isna(vol20.iloc[-1]) and vol20.iloc[-1] else None
    )
    return last
