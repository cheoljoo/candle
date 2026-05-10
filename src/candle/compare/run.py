"""Backtest type 간 비교 (req.md §1.1.3).

입력  : output/backtest/{type}/_summary.csv 들 + _all.csv (마지막 거래일 보유/현금)
출력  : output/compare/strategy_summary.csv  — 전략 단위 총자산/현금/.../수익률
        output/compare/per_ticker.csv        — 종목 × 전략 cross 비교 (수익률 정렬)
        output/compare/best_strategy.csv     — 종목별 최고전략 + 최고전략_매수일_시총순위
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

from .. import config
from ..io_report import announce, tprint
from ..storage import csv_io, paths

log = logging.getLogger(__name__)

CASH_TRACKING_TYPES = {"type1_2", "type2_2", "type2_2b", "type3"}


def run(cfg: config.Config, type_names: Iterable[str],
        debug: bool = False, period: str | None = None) -> dict[str, int]:
    _bt  = f"output/backtest/{period}/{{type}}" if period else "output/backtest/{type}"
    _cmp = f"output/compare/{period}"           if period else "output/compare"
    _label_info = f"label={period}" if period else "label 없음 (flat)"
    _label = period or "(기본)"
    announce(
        f"compare --types {','.join(type_names)}" + (f" --label {period}" if period else ""),
        inputs=[
            (f"{_bt}/_summary.csv",
             f"각 backtest type의 ticker별 수익률 요약 [{_label_info}]"),
            (f"{_bt}/_all.csv",
             "각 type의 거래 ledger — 매수금액 합산·최고전략 매수일 식별에 사용"),
            ("data/instruments.csv + data/daily/{KR|US}/{ticker}.csv",
             "rank_in_group lookup — 최고전략 매수일의 시총 순위 계산용"),
            ("output/analyze/{date}/summary.csv (가장 최근 분석일)",
             "평가일 거래량 / 20일평균 / 거래량배수 panel 작성용"),
        ],
        outputs=[
            (f"{_cmp}/strategy_summary.csv",
             "전략×그룹 단위 요약 — strategy,group,currency,tickers,총자산,현금,보유주식수,초기자본,손익,수익률,매수횟수,매도횟수 (TOTAL=그룹합계)"),
            (f"{_cmp}/per_ticker.csv",
             "종목 × 전략 cross — 각 ticker의 type별 수익률(%) + avg_return 정렬"),
            (f"{_cmp}/best_strategy.csv",
             "ticker별 최고전략 + 최고전략_마지막매수일 + 최고전략_매수일_시총순위 + 최종 현금/보유"),
            (f"{_cmp}/evaluation_volume.csv",
             "평가일 ticker별 거래량 panel — date,ticker,name,group_name,volume,vol20_avg,vol_ratio"),
        ],
    )
    out_dir = paths.compare_dir(cfg.output_dir, period)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_t0 = time.perf_counter()
    tprint(f"[compare] [{_label}] 시작 — period={period}", flush=True)

    bt_dir = paths.backtest_root(cfg.output_dir, period)
    type_list = list(type_names)
    n_types = len(type_list)
    summaries: list[pd.DataFrame] = []
    trade_frames: list[pd.DataFrame] = []
    for idx, t in enumerate(type_list, start=1):
        sp = bt_dir / t / "_summary.csv"
        ap = bt_dir / t / "_all.csv"
        tprint(f"[compare] type={t} 로딩 중... ({idx}/{n_types})", flush=True)
        if debug:
            print(f"[compare][debug] type={t} load summary={sp} all={ap}", flush=True)
        t0 = time.perf_counter()
        sdf = csv_io.read(sp)
        adf = csv_io.read(ap)
        if not sdf.empty:
            summaries.append(sdf)
        if not adf.empty:
            trade_frames.append(adf)
        elapsed = time.perf_counter() - t0
        tprint(f"[compare] type={t} 완료 — rows={len(sdf)}, elapsed={elapsed:.1f}s", flush=True)
        if debug:
            print(f"[compare][debug] type={t} loaded ({elapsed:.2f}s) — summary_rows={len(sdf)} trade_rows={len(adf)}", flush=True)
    if not summaries:
        log.warning("backtest summary가 없음. backtest 먼저 실행")
        return {"strategies": 0}

    summary_df = pd.concat(summaries, ignore_index=True)
    trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()

    # 1) 전략 단위 (currency별로 합산: KRW/USD 분리)
    tprint("[compare] step 1/4 strategy_summary 계산 중...", flush=True)
    if debug:
        print("[compare][debug] step 1/4 strategy_summary", flush=True)
    _step_t0 = time.perf_counter()
    strategy_rows = _strategy_summary(cfg, summary_df, trades_df)
    strategy_csv = pd.DataFrame(strategy_rows)
    csv_io.atomic_write(strategy_csv, out_dir / "strategy_summary.csv")
    _print_strategy(strategy_csv)
    tprint(f"[compare] step 1/4 완료 — elapsed={time.perf_counter()-_step_t0:.1f}s", flush=True)

    # 2) 종목 × 전략 cross
    tprint("[compare] step 2/4 per_ticker 계산 중...", flush=True)
    if debug:
        print("[compare][debug] step 2/4 per_ticker", flush=True)
    _step_t0 = time.perf_counter()
    pt = _per_ticker(summary_df)
    csv_io.atomic_write(pt, out_dir / "per_ticker.csv")
    tprint(f"[compare] step 2/4 완료 — elapsed={time.perf_counter()-_step_t0:.1f}s", flush=True)

    # 3) 종목별 최고전략 + 최고전략 매수일 시총순위
    tprint("[compare] step 3/4 best_strategy 계산 중...", flush=True)
    if debug:
        print("[compare][debug] step 3/4 best_strategy (rank lookup 포함)", flush=True)
    _step_t0 = time.perf_counter()
    best = _best_strategy(cfg, summary_df, trades_df, debug=debug)
    csv_io.atomic_write(best, out_dir / "best_strategy.csv")
    tprint(f"[compare] step 3/4 완료 — elapsed={time.perf_counter()-_step_t0:.1f}s", flush=True)

    # 4) 평가일 거래량 / 20일평균 / 거래량배수 — analyze summary 활용
    tprint("[compare] step 4/4 evaluation_volume 계산 중...", flush=True)
    if debug:
        print("[compare][debug] step 4/4 evaluation_volume", flush=True)
    _step_t0 = time.perf_counter()
    vol = _volume_panel(cfg)
    if not vol.empty:
        csv_io.atomic_write(vol, out_dir / "evaluation_volume.csv")
    tprint(f"[compare] step 4/4 완료 — elapsed={time.perf_counter()-_step_t0:.1f}s", flush=True)

    total_elapsed = time.perf_counter() - run_t0
    tprint(f"[compare] 완료 — elapsed={total_elapsed:.1f}s", flush=True)

    return {
        "strategies": int(strategy_csv["strategy"].nunique() if "strategy" in strategy_csv else len(strategy_csv)),
        "tickers": int(pt["ticker"].nunique()) if not pt.empty else 0,
    }


def _strategy_summary(cfg: config.Config, summary_df: pd.DataFrame,
                      trades_df: pd.DataFrame) -> list[dict]:
    """전략 × 그룹 단위 집계 + TOTAL 행.

    group_name 은 instruments.csv 에서 lookup.
    type1_1, type2_1: 고정수량(현금추적X). 수익률 = (보유가치 - 매수금액) / 매수금액 * 100.
    type1_2, type2_2, type3: 현금추적. 수익률 = (현금+보유가치 - 초기자본) / 초기자본 * 100.
    """
    rows: list[dict] = []
    initial_cap = cfg.strategies["initial_capital"]

    # group_name lookup: ticker → (group_name, currency)
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    ticker_group: dict[str, str] = {}
    if not inst.empty:
        for _, r in inst.iterrows():
            ticker_group[str(r["ticker"])] = str(r["group_name"])

    # summary_df 에 group_name 추가
    df = summary_df.copy()
    df["group_name"] = df["ticker"].astype(str).map(ticker_group).fillna("UNKNOWN")

    def _calc_group(type_name: str, grp: pd.DataFrame, currency: str) -> dict:
        n_tickers = len(grp)
        buy_cnt = int(grp["buy_count"].sum())
        sell_cnt = int(grp["sell_count"].sum())
        holding_qty = float(grp["final_holding_qty"].sum())
        holding_value = float(grp["final_holding_value"].sum())

        if type_name in CASH_TRACKING_TYPES:
            cash = grp["final_cash"].fillna(0).astype(float).sum()
            total_asset = holding_value + cash
            base_unit = float(initial_cap[currency])
            if type_name == "type3":
                initial_capital = base_unit * float(grp["buy_count"].sum())
            else:
                initial_capital = base_unit * n_tickers
            pnl = total_asset - initial_capital
            ret_pct = (pnl / initial_capital * 100.0) if initial_capital else 0.0
        else:
            cash = None
            total_asset = holding_value
            buy_amount = _sum_buy_amount(trades_df, type_name, currency=currency,
                                          tickers=set(grp["ticker"].astype(str)))
            initial_capital = buy_amount
            pnl = total_asset - buy_amount
            ret_pct = (pnl / buy_amount * 100.0) if buy_amount else 0.0

        return {
            "tickers": n_tickers,
            "총자산": round(total_asset, 4),
            "현금": (round(float(cash), 4) if cash is not None else None),
            "보유주식수": holding_qty,
            "초기자본": round(initial_capital, 4),
            "손익": round(pnl, 4),
            "수익률": round(ret_pct, 4),
            "매수횟수": buy_cnt,
            "매도횟수": sell_cnt,
        }

    # 그룹별 집계
    for (type_name, group_name), grp in df.groupby(["type", "group_name"]):
        # currency 는 그룹 내 동일 (KR→KRW, US→USD)
        currency = str(grp["currency"].iloc[0]) if "currency" in grp.columns else "???"
        row = _calc_group(type_name, grp, currency)
        rows.append({"strategy": type_name, "group": group_name,
                     "currency": currency, **row})

    # TOTAL 행: 통화별 합산 (KRW / USD 각각)
    for (type_name, currency), grp in df.groupby(["type", "currency"]):
        row = _calc_group(type_name, grp, currency)
        rows.append({"strategy": type_name, "group": f"TOTAL ({currency})",
                     "currency": currency, **row})

    # 정렬: strategy 순 → group(TOTAL 마지막)
    rows.sort(key=lambda r: (r["strategy"],
                              1 if r["group"].startswith("TOTAL") else 0,
                              r["group"]))
    return rows


def _sum_buy_amount(trades_df: pd.DataFrame, type_name: str, currency: str,
                    tickers: set[str]) -> float:
    if trades_df.empty:
        return 0.0
    df = trades_df[(trades_df["type"] == type_name) & (trades_df["side"] == "buy")]
    df = df[df["ticker"].astype(str).isin(tickers)]
    return float(pd.to_numeric(df["amount"], errors="coerce").fillna(0).sum())


def _per_ticker(summary_df: pd.DataFrame) -> pd.DataFrame:
    """ticker × strategy cross. 각 셀 = 수익률(%)."""
    if summary_df.empty:
        return pd.DataFrame()
    pivot = summary_df.pivot_table(
        index=["ticker", "name", "currency"],
        columns="type",
        values="return_pct",
        aggfunc="first",
    ).reset_index()
    # 수익률 평균 칼럼 + 정렬
    type_cols = [c for c in pivot.columns if c not in ("ticker", "name", "currency")]
    pivot["avg_return"] = pivot[type_cols].mean(axis=1, numeric_only=True)
    pivot = pivot.sort_values("avg_return", ascending=False).reset_index(drop=True)
    return pivot


def _best_strategy(cfg: config.Config, summary_df: pd.DataFrame,
                   trades_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """ticker별로 수익률 최고인 전략과 그 전략의 마지막 매수일 시총순위."""
    if summary_df.empty:
        return pd.DataFrame()

    idx = summary_df.groupby("ticker")["return_pct"].idxmax()
    best = summary_df.loc[idx].reset_index(drop=True).copy()
    best = best.rename(columns={"type": "최고전략", "return_pct": "최고수익률"})

    tprint("[compare] _best_strategy: rank lookup 구성 중...", flush=True)
    rank_lookup = _build_rank_lookup(cfg, debug=debug)
    tprint(f"[compare] _best_strategy: rank lookup 완료 ({len(rank_lookup)}개 ticker)", flush=True)

    last_buy_dates: list[str | None] = []
    last_buy_ranks: list[int | None] = []
    n_best = len(best)
    for i, (_, r) in enumerate(best.iterrows(), start=1):
        if i % 50 == 0 or i == n_best:
            pct = i * 100 // n_best
            tprint(f"[compare] best_strategy ticker {i}/{n_best} ({pct}%)", flush=True)
        tk = str(r["ticker"])
        strat = str(r["최고전략"])
        last_buy_date = _find_last_buy_date(trades_df, strat, tk)
        last_buy_dates.append(last_buy_date)
        if last_buy_date and (tk in rank_lookup):
            last_buy_ranks.append(rank_lookup[tk].get(last_buy_date))
        else:
            last_buy_ranks.append(None)
    best["최고전략_마지막매수일"] = last_buy_dates
    best["최고전략_매수일_시총순위"] = last_buy_ranks
    keep = ["ticker", "name", "currency", "최고전략", "최고수익률",
            "최고전략_마지막매수일", "최고전략_매수일_시총순위",
            "buy_count", "sell_count", "final_holding_qty", "final_holding_value", "final_cash"]
    keep = [c for c in keep if c in best.columns]
    return best[keep].sort_values("최고수익률", ascending=False).reset_index(drop=True)


def _find_last_buy_date(trades_df: pd.DataFrame, type_name: str, ticker: str) -> str | None:
    if trades_df.empty:
        return None
    df = trades_df[(trades_df["type"] == type_name) &
                   (trades_df["ticker"].astype(str) == ticker) &
                   (trades_df["side"] == "buy")]
    if df.empty:
        return None
    return str(df["date"].max())


def _build_rank_lookup(cfg: config.Config, debug: bool = False) -> dict[str, dict[str, int]]:
    """ticker → {date: rank_in_group} 매핑. 일봉 csv의 rank_in_group 컬럼에서."""
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {}
    total = len(inst)
    out: dict[str, dict[str, int]] = {}
    for i, (_, row) in enumerate(inst.iterrows(), start=1):
        if i % 50 == 0 or i == total:
            pct = i * 100 // total
            tprint(f"[compare] rank lookup {i}/{total} ({pct}%)", flush=True)
        tk = str(row["ticker"])
        mkt = str(row["market"])
        if debug:
            print(f"[compare][debug] rank lookup {i}/{total} {mkt}/{tk}", flush=True)
        df = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, tk))
        if df.empty or "rank_in_group" not in df.columns:
            continue
        rdf = df[["date", "rank_in_group"]].dropna()
        if rdf.empty:
            continue
        out[tk] = {str(d): int(r) for d, r in zip(rdf["date"], rdf["rank_in_group"])}
    return out


def _volume_panel(cfg: config.Config) -> pd.DataFrame:
    """analyze summary가 있으면 평가일 거래량 / vol20 / vol_ratio 모음."""
    analyze_dir = cfg.output_dir / "analyze"
    if not analyze_dir.exists():
        return pd.DataFrame()
    sub = sorted(analyze_dir.iterdir(), key=lambda p: p.name)
    if not sub:
        return pd.DataFrame()
    last = sub[-1] / "summary.csv"
    if not last.exists():
        return pd.DataFrame()
    df = csv_io.read(last)
    keep = [c for c in ["date", "ticker", "name", "group_name", "volume", "vol20_avg", "vol_ratio"]
            if c in df.columns]
    return df[keep] if keep else pd.DataFrame()


def _print_strategy(df: pd.DataFrame) -> None:
    if df.empty:
        return
    tprint("\n=== 전략별 그룹별 요약 ===")
    cols = [c for c in ["strategy", "group", "tickers", "수익률", "손익", "초기자본", "매수횟수", "매도횟수"]
            if c in df.columns]
    print(df[cols].to_string(index=False))  # 표 데이터는 timestamp 불필요
