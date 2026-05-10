"""Backtest 진입 — 타입별로 모든 ticker를 돌려 종목별 csv + 통합 csv.

증분(incremental) 처리 — output/backtest/{label}/_meta.csv 에 type별·ticker별
(backtest_from, backtest_to) 기록:
- from/to 동일 → skip
- from 이 당겨짐  → 전체 재계산
- to 만 늘어남   → 직전 Portfolio 상태 복원 후 새 구간만 계산 → 기존 CSV 에 append
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .. import config
from ..io_report import announce, tprint
from ..storage import csv_io, paths
from . import type1_1, type1_2, type2_1, type2_2, type3, base

log = logging.getLogger(__name__)

ALL = ["type1_1", "type1_2", "type2_1", "type2_2", "type2_1b", "type2_2b", "type3"]

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


def _initial_cash(cfg: config.Config, currency: str) -> float:
    return float(cfg.strategies["initial_capital"][currency])


def run(cfg: config.Config, type_names: list[str], market: str,
        start: date | None, end: date | None,
        debug: bool = False, period: str | None = None) -> dict[str, dict]:
    # 실제 출력 경로 패턴 — period/label 유무에 따라 다름
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

    # ── 증분 meta 로드 ─────────────────────────────────────────────────────
    bt_root = paths.backtest_root(cfg.output_dir, period)
    bt_root.mkdir(parents=True, exist_ok=True)
    meta = _load_meta(bt_root)
    updated_meta: dict[tuple[str, str], tuple[str, str]] = {}

    for type_idx, type_name in enumerate(type_names, start=1):
        out_dir = paths.backtest_dir(cfg.output_dir, type_name, period)
        out_dir.mkdir(parents=True, exist_ok=True)
        all_trades: list[pd.DataFrame] = []
        per_ticker_summary: list[dict] = []
        type_t0 = time.perf_counter()
        skipped_count = 0

        tprint(f"[backtest] {_label}type={type_name} ({type_idx}/{n_types}) 시작 — {total}개 ticker", flush=True)

        for i, (_, row) in enumerate(inst.iterrows(), start=1):
            ticker   = str(row["ticker"])
            mkt      = str(row["market"])
            group    = str(row["group_name"])
            currency = str(row["currency"])
            trades_path = out_dir / f"{ticker}.csv"

            t0 = time.perf_counter()
            daily = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, ticker))
            if daily.empty:
                if debug:
                    print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} — empty daily", flush=True)
                continue

            # 실제 처리 구간
            eff_from = start.isoformat() if start else str(daily.iloc[0]["date"])
            eff_to   = end.isoformat()   if end   else str(daily.iloc[-1]["date"])
            prev = meta.get((type_name, ticker))

            mode = "full"  # full | skip | resume
            if prev is not None:
                if prev[0] == eff_from and prev[1] == eff_to:
                    mode = "skip"
                elif prev[0] == eff_from and prev[1] < eff_to:
                    mode = "resume"
                # prev[0] != eff_from → full (from 이 달라짐)

            if mode == "skip":
                skipped_count += 1
                # 기존 trades 로 summary 재구성
                existing = csv_io.read(trades_path)
                if not existing.empty:
                    last_row = existing.iloc[-1]
                    per_ticker_summary.append(_summary_row(type_name, ticker, row, currency,
                                                            _count(existing, "buy"),
                                                            _count(existing, "sell"),
                                                            last_row))
                    all_trades.append(existing)
                updated_meta[(type_name, ticker)] = prev
                if debug:
                    print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} SKIP — from={eff_from} to={eff_to}", flush=True)
                if i % _progress_step == 0 or i == total:
                    _print_progress(_label, type_name, i, total, len(per_ticker_summary), type_t0)
                continue

            try:
                if mode == "resume":
                    existing = csv_io.read(trades_path)
                    pf, new_start = _resume(type_name, ticker, daily, currency, cfg,
                                            existing, prev[1], end)
                    new_trades = pf.trades_df()
                    if new_trades.empty:
                        # 새 신호 없음 — 기존 유지
                        updated_meta[(type_name, ticker)] = (eff_from, eff_to)
                        last_row = existing.iloc[-1]
                        per_ticker_summary.append(_summary_row(type_name, ticker, row, currency,
                                                                _count(existing, "buy"),
                                                                _count(existing, "sell"),
                                                                last_row))
                        all_trades.append(existing)
                        if debug:
                            print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} resume — 새 거래 없음 ({time.perf_counter()-t0:.2f}s)", flush=True)
                    else:
                        # mark_to_market 제거 후 append
                        base_trades = existing[existing["side"] != "mark_to_market"].copy()
                        combined = pd.concat([base_trades, new_trades], ignore_index=True)
                        csv_io.atomic_write(combined, trades_path)
                        last_row = combined.iloc[-1]
                        per_ticker_summary.append(_summary_row(type_name, ticker, row, currency,
                                                                _count(combined, "buy"),
                                                                _count(combined, "sell"),
                                                                last_row))
                        all_trades.append(combined)
                        updated_meta[(type_name, ticker)] = (eff_from, eff_to)
                        if debug:
                            print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} resume +{len(new_trades)}건 ({time.perf_counter()-t0:.2f}s)", flush=True)
                else:
                    pf = _dispatch(type_name, ticker, daily, currency, cfg, start, end)
                    if pf is None:
                        continue
                    new_trades = pf.trades_df()
                    if new_trades.empty:
                        continue
                    csv_io.atomic_write(new_trades, trades_path)
                    last_row = new_trades.iloc[-1]
                    per_ticker_summary.append(_summary_row(type_name, ticker, row, currency,
                                                            pf.buy_count, pf.sell_count, last_row))
                    all_trades.append(new_trades)
                    updated_meta[(type_name, ticker)] = (eff_from, eff_to)
                    if debug:
                        print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} full {len(new_trades)}건 ({time.perf_counter()-t0:.2f}s)", flush=True)

            except Exception as e:
                log.warning(f"backtest {type_name} {ticker} 실패: {e}")
                if debug:
                    print(f"[backtest][debug] [{type_name}] ({i}/{total}) {mkt}/{ticker} FAIL: {e}", flush=True)
                continue

            if i % _progress_step == 0 or i == total:
                _print_progress(_label, type_name, i, total, len(per_ticker_summary), type_t0)

        if all_trades:
            csv_io.atomic_write(pd.concat(all_trades, ignore_index=True), out_dir / "_all.csv")
        if per_ticker_summary:
            csv_io.atomic_write(pd.DataFrame(per_ticker_summary), out_dir / "_summary.csv")
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

    # meta 저장 (기존 + 이번 갱신분 merge)
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
            prev_to: str, end: date | None):
    """기존 trades 에서 Portfolio 상태를 복원하고 prev_to 다음 날부터만 계산."""
    s = cfg.strategies
    # 새 구간 시작일
    prev_to_date = pd.to_datetime(prev_to).date()
    new_start = prev_to_date + timedelta(days=1)

    initial_cash = None
    if type_name in ("type1_2", "type2_2", "type2_2b"):
        initial_cash = _initial_cash(cfg, currency)
    elif type_name == "type3":
        # type3 initial_cash 는 누적 입금액 — 기존 buy × installment_amount
        installment_amount = _initial_cash(cfg, currency)
        n_buys = _count(existing_trades, "buy")
        initial_cash = installment_amount * n_buys

    pf = base.Portfolio.from_trades(ticker, type_name, initial_cash, existing_trades)

    # type3 last_buy_date
    last_buy_date = None
    if type_name == "type3":
        buys = existing_trades[existing_trades["side"] == "buy"]
        if not buys.empty:
            last_buy_date = str(buys["date"].max())

    return _dispatch(type_name, ticker, daily, currency, cfg,
                     new_start, end, portfolio=pf,
                     last_buy_date=last_buy_date), new_start


def _dispatch(type_name: str, ticker: str, daily: pd.DataFrame,
              currency: str, cfg: config.Config,
              start: date | None, end: date | None,
              portfolio: base.Portfolio | None = None,
              last_buy_date: str | None = None) -> base.Portfolio | None:
    s = cfg.strategies
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
    if type_name == "type3":
        return type3.run_one(ticker, daily,
                              installment_amount=_initial_cash(cfg, currency),
                              interval_days=int(s["type3"]["interval_days"]),
                              start=start, end=end,
                              portfolio=portfolio, last_buy_date=last_buy_date)
    return None
