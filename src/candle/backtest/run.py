"""Backtest 진입 — 타입별로 모든 ticker를 돌려 종목별 csv + 통합 csv.

증분(incremental) 처리 — output/backtest/{label}/_meta.csv 에 type별·ticker별
(backtest_from, backtest_to) 기록:
- from/to 동일 → skip
- from 이 당겨짐  → 전체 재계산
- to 만 늘어남   → 직전 Portfolio 상태 복원 후 새 구간만 계산 → 기존 CSV 에 append

type2_2_opt 증분 처리:
- output/backtest/{label}/type2_2_opt/_opt_params.json 에 ticker별 (plus_days, minus_days) 저장
- 파라미터 변경 감지 시 해당 ticker 전체 재계산 (full), 동일 시 증분(resume) 적용

성능 최적화 (3종):
1. daily CSV 사전 캐시 — type 루프 전에 한 번만 로드 (N type × M ticker 읽기 → M회)
2. ticker 병렬 처리  — ThreadPoolExecutor 로 type 내 ticker 병렬 실행
3. trades CSV 캐시   — type 시작 시 기존 trades 일괄 로드 (resume/skip per-ticker 읽기 제거)
"""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .. import config
from ..io_report import announce, tprint
from ..storage import csv_io, paths
from . import type0_2, type1_1, type1_2, type2_1, type2_2, type2_2_opt, type3, base

log = logging.getLogger(__name__)

ALL = ["type0_2", "type1_1", "type1_2", "type2_1", "type2_2", "type2_1b", "type2_2b", "type2_2_opt", "type3"]

# ── 증분 meta I/O ─────────────────────────────────────────────────────────
_META_FILE = "_meta.csv"
_META_COLS  = ["type", "ticker", "backtest_from", "backtest_to"]


def _load_meta(out_root: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(type, ticker) → (backtest_from, backtest_to)."""
    p = out_root / _META_FILE
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
        return {
            (r["type"], r["ticker"]): (r["backtest_from"], r["backtest_to"])
            for _, r in df.iterrows()
        }
    except Exception as e:
        log.warning(f"backtest meta 로드 실패: {e}")
        return {}


def _save_meta(out_root: Path, meta: dict[tuple[str, str], tuple[str, str]]) -> None:
    rows = [{"type": k[0], "ticker": k[1],
             "backtest_from": v[0], "backtest_to": v[1]}
            for k, v in meta.items()]
    df = pd.DataFrame(rows, columns=_META_COLS).sort_values(["type", "ticker"])
    csv_io.atomic_write(df, out_root / _META_FILE)


# ── type2_2_opt 최적화 파라미터 I/O ───────────────────────────────────────
_OPT_PARAMS_FILE = "_opt_params.json"


def _load_opt_params_used(out_dir: Path) -> dict[str, tuple[int, int]]:
    """type2_2_opt 가 지난 번 사용한 (plus_days, minus_days) 로드."""
    p = out_dir / _OPT_PARAMS_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {tk: (int(v["plus_days"]), int(v["minus_days"])) for tk, v in data.items()}
    except Exception as e:
        log.warning(f"_opt_params.json 로드 실패: {e}")
        return {}


def _save_opt_params_used(out_dir: Path,
                          params: dict[str, tuple[int, int]]) -> None:
    data = {tk: {"plus_days": pd_val, "minus_days": md_val}
            for tk, (pd_val, md_val) in params.items()}
    (out_dir / _OPT_PARAMS_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_opt_params_current(cfg: config.Config,
                              inst: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """output/optimize/per_ticker/{group}/_summary.json 에서 종목별 최적 파라미터 로드."""
    s = cfg.strategies.get("type2_2_opt", {})
    fallback_p = int(s.get("fallback_plus_days", 33))
    fallback_m = int(s.get("fallback_minus_days", 5))

    opt_root = cfg.output_dir / "optimize" / "per_ticker"
    group_cache: dict[str, dict] = {}

    result: dict[str, tuple[int, int]] = {}
    for _, row in inst.iterrows():
        ticker     = str(row["ticker"])
        group_name = str(row.get("group_name", ""))
        if group_name not in group_cache:
            summary_path = opt_root / group_name / "_summary.json"
            if summary_path.exists():
                try:
                    group_cache[group_name] = json.loads(
                        summary_path.read_text(encoding="utf-8"))
                except Exception as e:
                    log.warning(f"opt _summary.json 로드 실패 ({group_name}): {e}")
                    group_cache[group_name] = {}
            else:
                group_cache[group_name] = {}

        entry = group_cache[group_name].get(ticker, {})
        result[ticker] = (
            int(entry.get("plus_days",  fallback_p)),
            int(entry.get("minus_days", fallback_m)),
        )
    return result


def _initial_cash(cfg: config.Config, currency: str) -> float:
    return float(cfg.strategies["initial_capital"][currency])


# ── 성능 최적화: 캐시 로드 ─────────────────────────────────────────────────

def _load_daily_cache(cfg, inst: pd.DataFrame, label: str) -> dict[str, pd.DataFrame]:
    """type 루프 전에 모든 ticker daily CSV를 한 번만 로드 (Optimization 1)."""
    total = len(inst)
    t0 = time.perf_counter()
    tprint(f"[backtest] {label}daily CSV 캐시 로드 중 ({total}개)...", flush=True)
    cache: dict[str, pd.DataFrame] = {}
    for _, row in inst.iterrows():
        ticker = str(row["ticker"])
        mkt    = str(row["market"])
        df = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, ticker))
        if not df.empty:
            cache[ticker] = df
    tprint(
        f"[backtest] {label}daily CSV 캐시 완료 — {len(cache)}/{total}개"
        f" ({time.perf_counter()-t0:.1f}s)",
        flush=True,
    )
    return cache


def _load_trades_cache(out_dir: Path, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """type 시작 시 기존 ticker trades CSV를 일괄 로드 (Optimization 3)."""
    cache: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        p = out_dir / f"{ticker}.csv"
        if p.exists():
            df = csv_io.read(p)
            if not df.empty:
                cache[ticker] = df
    return cache


# ── 단일 ticker 처리 결과 ────────────────────────────────────────────────

@dataclass
class _TickerResult:
    skipped: bool = False
    summary: dict | None = None
    trades: pd.DataFrame | None = None
    meta_key: tuple | None = None
    meta_val: tuple | None = None
    opt_param: tuple | None = None


def _process_ticker(
    *,
    row,
    i: int,
    total: int,
    type_name: str,
    out_dir: Path,
    daily: pd.DataFrame,
    existing_trades: pd.DataFrame | None,
    meta: dict,
    cfg,
    start: date | None,
    end: date | None,
    debug: bool,
    label: str,
    cur_opt_params: dict,
    prev_opt_params: dict,
) -> _TickerResult:
    """단일 ticker backtest — thread-safe (각 ticker 고유 파일에만 쓰기) (Optimization 2)."""
    ticker   = str(row["ticker"])
    currency = str(row["currency"])
    trades_path = out_dir / f"{ticker}.csv"
    result = _TickerResult()
    t0 = time.perf_counter()

    eff_from = start.isoformat() if start else str(daily.iloc[0]["date"])
    eff_to   = end.isoformat()   if end   else str(daily.iloc[-1]["date"])
    prev     = meta.get((type_name, ticker))

    mode = "full"
    if prev is not None:
        if prev[0] == eff_from and prev[1] == eff_to:
            mode = "skip"
        elif prev[0] == eff_from and prev[1] < eff_to:
            mode = "resume"

    if type_name == "type2_2_opt" and mode != "full":
        opt_cur  = cur_opt_params.get(ticker)
        opt_prev = prev_opt_params.get(ticker)
        if opt_cur is not None and opt_cur != opt_prev:
            mode = "full"
            if debug:
                print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker}"
                      f" opt params changed {opt_prev}→{opt_cur}, force full", flush=True)

    _opt_p     = cur_opt_params.get(ticker) if type_name == "type2_2_opt" else None
    _opt_plus  = _opt_p[0] if _opt_p else None
    _opt_minus = _opt_p[1] if _opt_p else None

    try:
        if mode == "skip":
            result.skipped = True
            existing = existing_trades
            if existing is not None and not existing.empty:
                last_row = existing.iloc[-1]
                result.summary = _summary_row(type_name, ticker, row, currency,
                                              _count(existing, "buy"),
                                              _count(existing, "sell"), last_row)
                result.trades = existing
            result.meta_key = (type_name, ticker)
            result.meta_val = prev
            if type_name == "type2_2_opt" and ticker in cur_opt_params:
                result.opt_param = cur_opt_params[ticker]
            if debug:
                print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker}"
                      f" SKIP — from={eff_from} to={eff_to}", flush=True)

        elif mode == "resume":
            existing = existing_trades
            if existing is None or existing.empty:
                # 기존 trades 없음 → full fallback
                pf = _dispatch(type_name, ticker, daily, currency, cfg, start, end,
                               opt_plus_days=_opt_plus, opt_minus_days=_opt_minus)
                if pf is None:
                    return result
                new_trades = pf.trades_df()
                if new_trades.empty:
                    return result
                csv_io.atomic_write(new_trades, trades_path)
                result.summary = _summary_row(type_name, ticker, row, currency,
                                              pf.buy_count, pf.sell_count, new_trades.iloc[-1])
                result.trades  = new_trades
                result.meta_key = (type_name, ticker)
                result.meta_val = (eff_from, eff_to)
            else:
                pf, new_start = _resume(type_name, ticker, daily, currency, cfg,
                                        existing, prev[1], end,
                                        opt_plus_days=_opt_plus, opt_minus_days=_opt_minus)
                new_trades = pf.trades_df()
                if new_trades.empty:
                    result.meta_key = (type_name, ticker)
                    result.meta_val = (eff_from, eff_to)
                    result.summary  = _summary_row(type_name, ticker, row, currency,
                                                   _count(existing, "buy"),
                                                   _count(existing, "sell"), existing.iloc[-1])
                    result.trades   = existing
                    if debug:
                        print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker}"
                              f" resume — 새 거래 없음 ({time.perf_counter()-t0:.2f}s)", flush=True)
                else:
                    base_trades = existing[existing["side"] != "mark_to_market"].copy()
                    combined = pd.concat([base_trades, new_trades], ignore_index=True)
                    csv_io.atomic_write(combined, trades_path)
                    result.summary  = _summary_row(type_name, ticker, row, currency,
                                                   _count(combined, "buy"),
                                                   _count(combined, "sell"), combined.iloc[-1])
                    result.trades   = combined
                    result.meta_key = (type_name, ticker)
                    result.meta_val = (eff_from, eff_to)
                    if debug:
                        print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker}"
                              f" resume +{len(new_trades)}건 ({time.perf_counter()-t0:.2f}s)", flush=True)
            if type_name == "type2_2_opt" and ticker in cur_opt_params:
                result.opt_param = cur_opt_params[ticker]

        else:  # full
            pf = _dispatch(type_name, ticker, daily, currency, cfg, start, end,
                           opt_plus_days=_opt_plus, opt_minus_days=_opt_minus)
            if pf is None:
                return result
            new_trades = pf.trades_df()
            if new_trades.empty:
                return result
            csv_io.atomic_write(new_trades, trades_path)
            result.summary  = _summary_row(type_name, ticker, row, currency,
                                           pf.buy_count, pf.sell_count, new_trades.iloc[-1])
            result.trades   = new_trades
            result.meta_key = (type_name, ticker)
            result.meta_val = (eff_from, eff_to)
            if type_name == "type2_2_opt" and ticker in cur_opt_params:
                result.opt_param = cur_opt_params[ticker]
            if debug:
                print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker}"
                      f" full {len(new_trades)}건 ({time.perf_counter()-t0:.2f}s)", flush=True)

    except Exception as e:
        log.warning(f"backtest {type_name} {ticker} 실패: {e}")
        if debug:
            print(f"[backtest][debug] [{type_name}] ({i}/{total}) {ticker} FAIL: {e}", flush=True)

    return result


def run(cfg: config.Config, type_names: list[str], market: str,
        start: date | None, end: date | None,
        debug: bool = False, period: str | None = None) -> dict[str, dict]:
    _bt = f"output/backtest/{period}/{{type}}" if period else "output/backtest/{type}"
    _period_info = (
        f"기간: {start.isoformat() if start else '전체'} ~ {end.isoformat() if end else '오늘'}"
        + (f"  (label={period})" if period else "")
    )
    announce(
        f"backtest --types {','.join(type_names)} --market {market}",
        inputs=[
            ("config/strategies.yml",
             "각 type 파라미터 — qty, plus_days/minus_days, 초기자본(KRW/USD), interval_days"),
            ("data/instruments.csv",
             "backtest 대상 ticker 목록"),
            ("data/daily/{KR|US}/{ticker}.csv",
             f"분석된 일봉 — inflection, ma10m_updown 신호 컬럼 사용  [{_period_info}]"),
        ],
        outputs=[
            (f"{_bt}/{{ticker}}.csv",
             "종목별 거래 ledger — type,date,ticker,side(buy/sell/mark_to_market),price,qty,amount,holding_qty,holding_value,cash,return_pct"),
            (f"{_bt}/_all.csv",
             "type 단위 모든 ticker 합본 (동일 스키마)"),
            (f"{_bt}/_summary.csv",
             "ticker별 최종 수익률 요약 — type,ticker,name,currency,buy_count,sell_count,final_holding_qty,final_holding_value,final_cash,return_pct"),
        ],
    )
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {}
    if market != "all":
        inst = inst[inst["market"] == market.upper()]

    results: dict[str, dict] = {}
    total = len(inst)
    n_types = len(type_names)
    _label = f"[{period}] " if period else ""
    _progress_step = max(1, min(10, total // 10))
    n_workers = min(8, os.cpu_count() or 4)

    bt_root = paths.backtest_root(cfg.output_dir, period)
    bt_root.mkdir(parents=True, exist_ok=True)
    meta = _load_meta(bt_root)
    updated_meta: dict[tuple[str, str], tuple[str, str]] = {}

    # ── Optimization 1: daily CSV 사전 캐시 (전체 type 공통, 한 번만 읽기) ──
    daily_cache = _load_daily_cache(cfg, inst, _label)
    # daily 데이터가 있는 ticker + 원본 row 를 순서대로 보존
    ticker_rows: list[tuple[int, object]] = [
        (enum_i, row)
        for enum_i, (_, row) in enumerate(inst.iterrows(), start=1)
        if str(row["ticker"]) in daily_cache
    ]
    ticker_list = [str(row["ticker"]) for _, row in ticker_rows]

    for type_idx, type_name in enumerate(type_names, start=1):
        out_dir = paths.backtest_dir(cfg.output_dir, type_name, period)
        out_dir.mkdir(parents=True, exist_ok=True)
        type_t0 = time.perf_counter()
        skipped_count = 0

        tprint(f"[backtest] {_label}type={type_name} ({type_idx}/{n_types}) 시작 — {total}개 ticker", flush=True)

        cur_opt_params: dict[str, tuple[int, int]] = {}
        prev_opt_params: dict[str, tuple[int, int]] = {}
        updated_opt_params: dict[str, tuple[int, int]] = {}
        if type_name == "type2_2_opt":
            cur_opt_params  = _load_opt_params_current(cfg, inst)
            prev_opt_params = _load_opt_params_used(out_dir)
            tprint(f"[backtest] {_label}type2_2_opt — "
                   f"opt 파라미터 로드 완료 ({len(cur_opt_params)}개 종목)", flush=True)

        # ── Optimization 3: 기존 trades CSV 사전 캐시 (이 type 전체) ────────
        trades_cache = _load_trades_cache(out_dir, ticker_list)

        # ── Optimization 2: ticker 병렬 처리 ─────────────────────────────
        all_trades: list[pd.DataFrame] = []
        per_ticker_summary: list[dict] = []
        done_count = 0
        n_submitted = len(ticker_rows)

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures: dict = {
                executor.submit(
                    _process_ticker,
                    row=row,
                    i=enum_i,
                    total=total,
                    type_name=type_name,
                    out_dir=out_dir,
                    daily=daily_cache[str(row["ticker"])],
                    existing_trades=trades_cache.get(str(row["ticker"])),
                    meta=meta,
                    cfg=cfg,
                    start=start,
                    end=end,
                    debug=debug,
                    label=_label,
                    cur_opt_params=cur_opt_params,
                    prev_opt_params=prev_opt_params,
                ): str(row["ticker"])
                for enum_i, row in ticker_rows
            }

            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    res: _TickerResult = fut.result()
                    if res.summary is not None:
                        per_ticker_summary.append(res.summary)
                    if res.trades is not None:
                        all_trades.append(res.trades)
                    if res.meta_key is not None:
                        updated_meta[res.meta_key] = res.meta_val
                    if res.opt_param is not None:
                        updated_opt_params[ticker] = res.opt_param
                    if res.skipped:
                        skipped_count += 1
                except Exception as e:
                    log.warning(f"[backtest] {type_name}/{ticker} 처리 실패: {e}")

                done_count += 1
                if done_count % _progress_step == 0 or done_count == n_submitted:
                    _print_progress(_label, type_name, done_count, n_submitted,
                                    len(per_ticker_summary), type_t0)

        processed_tickers = {r["ticker"] for r in per_ticker_summary}

        all_path = out_dir / "_all.csv"
        new_all = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
        if all_path.exists():
            existing_all = csv_io.read(all_path)
            if not existing_all.empty:
                other = existing_all[~existing_all["ticker"].astype(str).isin(processed_tickers)]
                new_all = pd.concat([other, new_all], ignore_index=True)
        if not new_all.empty:
            csv_io.atomic_write(new_all, all_path)

        summary_path = out_dir / "_summary.csv"
        new_summary = pd.DataFrame(per_ticker_summary)
        if summary_path.exists():
            existing_summary = csv_io.read(summary_path)
            if not existing_summary.empty:
                other_s = existing_summary[~existing_summary["ticker"].astype(str).isin(processed_tickers)]
                new_summary = pd.concat([other_s, new_summary], ignore_index=True)
        if not new_summary.empty:
            csv_io.atomic_write(new_summary, summary_path)

        if type_name == "type2_2_opt" and updated_opt_params:
            _save_opt_params_used(out_dir, updated_opt_params)

        results[type_name] = {
            "tickers": len(per_ticker_summary),
            "skipped": skipped_count,
            "total_trades": int(sum(len(t) for t in all_trades)),
        }
        total_elapsed = time.perf_counter() - type_t0
        tprint(
            f"[backtest] {_label}type={type_name} 완료 —"
            f" {total}개 중 {len(per_ticker_summary)}개 거래 발생 (skip={skipped_count}),"
            f" 총 {results[type_name]['total_trades']}건, {total_elapsed:.1f}s",
            flush=True,
        )

    _save_meta(bt_root, {**meta, **updated_meta})
    return results


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def _print_progress(label: str, type_name: str, i: int, total: int,
                    traded: int, t0: float) -> None:
    elapsed = time.perf_counter() - t0
    tprint(
        f"[backtest] {label}{type_name}  {i}/{total} ({i/total*100:.0f}%)"
        f"  거래발생={traded}  경과={elapsed:.0f}s",
        flush=True,
    )


def _count(df: pd.DataFrame, side: str) -> int:
    return int((df["side"] == side).sum()) if not df.empty else 0


def _summary_row(type_name: str, ticker: str, inst_row, currency: str,
                 buy_count: int, sell_count: int, last_row) -> dict:
    return {
        "type": type_name,
        "ticker": ticker,
        "name": str(inst_row["name"]),
        "currency": currency,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "final_holding_qty": float(pd.to_numeric(
            pd.Series([last_row.get("holding_qty")]), errors="coerce").fillna(0).iloc[0]),
        "final_holding_value": float(pd.to_numeric(
            pd.Series([last_row.get("holding_value")]), errors="coerce").fillna(0).iloc[0]),
        "final_cash": (float(pd.to_numeric(
            pd.Series([last_row.get("cash")]), errors="coerce").iloc[0])
                       if last_row.get("cash") is not None else None),
        "return_pct": last_row.get("return_pct"),
    }


def _resume(type_name: str, ticker: str, daily: pd.DataFrame,
            currency: str, cfg, existing_trades: pd.DataFrame,
            prev_to: str, end: date | None,
            opt_plus_days: int | None = None,
            opt_minus_days: int | None = None):
    """기존 trades 에서 Portfolio 상태를 복원하고 prev_to 다음 날부터만 계산."""
    s = cfg.strategies
    prev_to_date = pd.to_datetime(prev_to).date()
    new_start = prev_to_date + timedelta(days=1)

    initial_cash = None
    if type_name in ("type0_2", "type1_2", "type2_2", "type2_2b", "type2_2_opt"):
        initial_cash = _initial_cash(cfg, currency)
    elif type_name == "type3":
        installment_amount = _initial_cash(cfg, currency)
        n_buys = _count(existing_trades, "buy")
        initial_cash = installment_amount * n_buys

    pf = base.Portfolio.from_trades(ticker, type_name, initial_cash, existing_trades)

    last_buy_date = None
    if type_name == "type3":
        buys = existing_trades[existing_trades["side"] == "buy"]
        if not buys.empty:
            last_buy_date = str(buys["date"].max())

    return _dispatch(type_name, ticker, daily, currency, cfg,
                     new_start, end, portfolio=pf,
                     last_buy_date=last_buy_date,
                     opt_plus_days=opt_plus_days,
                     opt_minus_days=opt_minus_days), new_start


def _dispatch(type_name: str, ticker: str, daily: pd.DataFrame,
              currency: str, cfg: config.Config,
              start: date | None, end: date | None,
              portfolio: base.Portfolio | None = None,
              last_buy_date: str | None = None,
              opt_plus_days: int | None = None,
              opt_minus_days: int | None = None) -> base.Portfolio | None:
    s = cfg.strategies
    if type_name == "type0_2":
        return type0_2.run_one(ticker, daily, initial_cash=_initial_cash(cfg, currency),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type1_1":
        return type1_1.run_one(ticker, daily, qty=int(s["type1_1"]["qty"]),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type1_2":
        return type1_2.run_one(ticker, daily, initial_cash=_initial_cash(cfg, currency),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type2_1":
        return type2_1.run_one(ticker, daily, qty=int(s["type2_1"]["qty"]),
                                plus_days=int(s["type2_1"]["plus_days"]),
                                minus_days=int(s["type2_1"]["minus_days"]),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type2_2":
        return type2_2.run_one(ticker, daily, initial_cash=_initial_cash(cfg, currency),
                                plus_days=int(s["type2_2"]["plus_days"]),
                                minus_days=int(s["type2_2"]["minus_days"]),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type2_1b":
        return type2_1.run_one(ticker, daily, qty=int(s["type2_1b"]["qty"]),
                                plus_days=int(s["type2_1b"]["plus_days"]),
                                minus_days=int(s["type2_1b"]["minus_days"]),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type2_2b":
        return type2_2.run_one(ticker, daily, initial_cash=_initial_cash(cfg, currency),
                                plus_days=int(s["type2_2b"]["plus_days"]),
                                minus_days=int(s["type2_2b"]["minus_days"]),
                                start=start, end=end, portfolio=portfolio)
    if type_name == "type2_2_opt":
        t2opt = s.get("type2_2_opt", {})
        p_days = opt_plus_days  if opt_plus_days  is not None else int(t2opt.get("fallback_plus_days",  33))
        m_days = opt_minus_days if opt_minus_days is not None else int(t2opt.get("fallback_minus_days", 5))
        return type2_2_opt.run_one(ticker, daily, initial_cash=_initial_cash(cfg, currency),
                                    plus_days=p_days, minus_days=m_days,
                                    start=start, end=end, portfolio=portfolio)
    if type_name == "type3":
        return type3.run_one(ticker, daily,
                              installment_amount=_initial_cash(cfg, currency),
                              interval_days=int(s["type3"]["interval_days"]),
                              start=start, end=end,
                              portfolio=portfolio, last_buy_date=last_buy_date)
    return None
