"""plus_days / minus_days 그리드 서치 — type2_2b 계열 최적화.

전략: MA10M_UPDOWN 이 + 방향으로 P일 연속 → 보유 현금 전액 매수
      MA10M_UPDOWN 이 - 방향으로 M일 연속 → 전량 매도

시뮬레이션 기준: type2_2b (전액 매수 / 전량 매도 방식)
- type2_1b (10주 고정 매수) 는 현실적이지 않아 최적화 대상에서 제외.
- 최적화 결과 (plus_days, minus_days) 는 type2_2b 전략에만 적용.

접근:
  1) 각 ticker 의 streak(연속일수) 을 한 번만 계산 (O(N_tickers × N_rows)).
  2) (P, M) 조합별 이벤트 필터링 + 간략 시뮬레이션 (O(N_combos × N_events_per_ticker)).
  3) 전체 ticker 의 평균 수익률 / 양수 비율로 최적 파라미터 선정.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from .. import config
from ..io_report import tprint
from ..storage import csv_io, paths

log = logging.getLogger(__name__)

_DEFAULT_WORKERS: int = max(1, (os.cpu_count() or 4) // 2)


def _debug_log(enabled: bool, message: str, *, flush: bool = False) -> None:
    """Emit optimize progress logs only when debug mode is enabled."""
    if enabled:
        tprint(message, flush=flush)


# ── 1. streak 사전 계산 ──────────────────────────────────────────────────
def _compute_streaks(daily: pd.DataFrame) -> pd.DataFrame:
    """일봉 df → streak_sign, streak_len, close 컬럼 추가.

    streak_len: 현재 방향(+/-)이 연속된 일수 (방향 전환 시 1로 리셋).
    """
    df = daily[["date", "close", "ma10m_updown"]].copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    streak_sign_list: list[str | None] = []
    streak_len_list:  list[int] = []

    cur_sign: str | None = None
    cur_len:  int = 0

    for val in df["ma10m_updown"]:
        if pd.isna(val) or val not in ("+", "-"):
            val = None
        if val != cur_sign:
            cur_sign = val
            cur_len  = 1
        else:
            cur_len += 1
        streak_sign_list.append(cur_sign)
        streak_len_list.append(cur_len)

    df["streak_sign"] = streak_sign_list
    df["streak_len"]  = streak_len_list
    return df.dropna(subset=["close"]).reset_index(drop=True)


# ── 2. 이벤트 추출 (plus_days/minus_days 독립) ──────────────────────────
def _extract_events(streaked: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """streak_len 값별로 buy/sell 이벤트를 미리 분류.

    반환:
        {
          "buy_k":  {k: DataFrame(date, close)} for k = 1..max_len
          "sell_m": {m: DataFrame(date, close)} for m = 1..max_len
        }
    """
    buy_events:  dict[int, pd.DataFrame] = {}
    sell_events: dict[int, pd.DataFrame] = {}

    buy_df  = streaked[streaked["streak_sign"] == "+"][["date", "close", "streak_len"]]
    sell_df = streaked[streaked["streak_sign"] == "-"][["date", "close", "streak_len"]]

    for k, grp in buy_df.groupby("streak_len"):
        buy_events[int(k)] = grp[["date", "close"]].reset_index(drop=True)
    for m, grp in sell_df.groupby("streak_len"):
        sell_events[int(m)] = grp[["date", "close"]].reset_index(drop=True)

    return {"buy": buy_events, "sell": sell_events}


# ── 3. 단일 (P, M) 시뮬레이션 ────────────────────────────────────────────
def _simulate_one(events: dict, plus_days: int, minus_days: int,
                  initial_cash: float, last_close: float) -> float:
    """이벤트 기반 type2_2 시뮬레이션 → return_pct."""
    buy_ev  = events["buy"].get(plus_days)
    sell_ev = events["sell"].get(minus_days)

    if (buy_ev is None or buy_ev.empty) and (sell_ev is None or sell_ev.empty):
        return 0.0

    # 이벤트 병합 → 날짜 순 정렬
    frames = []
    if buy_ev is not None and not buy_ev.empty:
        frames.append(buy_ev.assign(side="buy"))
    if sell_ev is not None and not sell_ev.empty:
        frames.append(sell_ev.assign(side="sell"))

    ev = pd.concat(frames).sort_values("date").reset_index(drop=True)

    cash  = float(initial_cash)
    qty   = 0.0

    for _, row in ev.iterrows():
        close = float(row["close"])
        if close <= 0:
            continue
        if row["side"] == "buy" and cash > 0:
            q = cash // close
            if q > 0:
                qty  += q
                cash -= q * close
        elif row["side"] == "sell" and qty > 0:
            cash += qty * close
            qty   = 0.0

    # 미청산 보유분 마지막 종가로 평가
    total_asset = cash + qty * last_close
    return (total_asset - initial_cash) / initial_cash * 100.0


# ── 4. 전체 ticker 한 번에 streak 로딩 ──────────────────────────────────
def _load_ticker(cfg: config.Config, ticker: str, market: str,
                 start: date | None, end: date | None) -> tuple | None:
    """(ticker, events_dict, last_close) 반환. 실패 시 None."""
    try:
        p = paths.daily_csv(cfg.data_dir, market, ticker)
        if not p.exists():
            return None
        # 필요한 컬럼 3개만 읽어 속도 향상 (전체 16컬럼 대비 ~5배 빠름)
        try:
            daily = pd.read_csv(p, usecols=["date", "close", "ma10m_updown"],
                                 dtype={"date": str, "ma10m_updown": str})
        except ValueError:
            # usecols 가 없는 경우 (옛 포맷)
            daily = pd.read_csv(p, dtype={"date": str})
        if daily.empty or "ma10m_updown" not in daily.columns:
            return None

        # 날짜 필터
        daily["date"] = daily["date"].astype(str)
        if start is not None:
            daily = daily[daily["date"] >= start.isoformat()]
        if end is not None:
            daily = daily[daily["date"] <= end.isoformat()]
        if daily.empty:
            return None

        streaked = _compute_streaks(daily)
        if streaked.empty:
            return None

        events     = _extract_events(streaked)
        last_close = float(streaked.iloc[-1]["close"])
        return ticker, events, last_close
    except Exception as e:
        log.debug(f"{ticker} 로드 실패: {e}")
        return None


ALL_GROUPS = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]


def run_all_groups(
    cfg: config.Config,
    output_dir: Path,
    start: date | None = None,
    end: date | None = None,
    plus_min: int = 4,
    plus_max: int = 40,
    plus_step: int = 2,
    minus_min: int = 4,
    minus_max: int = 10,
    minus_step: int = 2,
    workers: int = _DEFAULT_WORKERS,
    top_n: int = 30,
    debug: bool = False,
) -> dict[str, pd.DataFrame]:
    """전체(all) + 4개 그룹별 그리드 서치를 한번에 실행.

    ticker 로딩은 1회만 수행하고, 각 그룹 필터링 후 grid search.
    output_dir 아래에 streak_grid_{group}.csv 5개 저장.
    반환: {group_label: result_df}
    """
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        log.error("instruments.csv 없음. universe 먼저 실행")
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    initial_capital = cfg.strategies["initial_capital"]

    # ── 1회 streak 로딩 (전체) ────────────────────────────────────────
    print(f"[streak_grid] 전체 ticker streak 로딩 중... ({len(inst)}개, workers={workers})", flush=True)
    t0 = time.perf_counter()
    ticker_list = [(str(r["ticker"]), str(r["market"]), str(r["currency"]),
                    str(r.get("group_name", "")))
                   for _, r in inst.iterrows()]

    loaded_all: list[tuple] = []
    n_total = len(ticker_list)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_load_ticker, cfg, tk, mkt, start, end): (tk, mkt, cur, grp)
            for tk, mkt, cur, grp in ticker_list
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            tk, mkt, cur, grp = futs[fut]
            result = fut.result()
            if result is not None:
                ticker, events, last_close = result
                ic = float(initial_capital.get("KRW" if mkt == "KR" else "USD", 1000))
                loaded_all.append((ticker, events, last_close, ic, grp))
                if debug:
                    n_events = sum(len(v) for v in events.get("buy", {}).values())
                    print(f"[streak_grid][debug] ({done}/{n_total}) {mkt}/{tk} ({grp})"
                          f" → buy_events={n_events} last_close={last_close:,.1f}", flush=True)
            else:
                if debug:
                    print(f"[streak_grid][debug] ({done}/{n_total}) {mkt}/{tk} ({grp}) → SKIP (데이터 없음)", flush=True)
            if done % 100 == 0 or done == n_total:
                print(f"[streak_grid]   로딩 {done}/{n_total}", flush=True)

    print(f"[streak_grid] 로딩 완료 — 유효 {len(loaded_all)}개, elapsed={time.perf_counter()-t0:.1f}s", flush=True)
    if not loaded_all:
        return {}

    if debug:
        from collections import Counter as _Counter
        grp_cnt = _Counter(grp for *_, grp in loaded_all)
        print(f"[streak_grid][debug] 그룹별 유효 ticker: "
              + ", ".join(f"{g}={grp_cnt.get(g,0)}" for g in ["KOSPI200","SP500","ETF_KR","ETF_US"])
              + f", total={len(loaded_all)}", flush=True)

    # ── 5개 그룹 순서로 grid search ───────────────────────────────────
    # ── 메타데이터 저장 ─────────────────────────────────────────────────
    import json as _json
    from datetime import datetime as _dt
    meta = {
        "run_date":   _dt.now().strftime("%Y-%m-%d %H:%M"),
        "data_from":  start.isoformat() if start else "2000-01-01",
        "data_to":    end.isoformat() if end else _dt.today().strftime("%Y-%m-%d"),
        "plus_range": f"{plus_min}~{plus_max} step {plus_step}",
        "minus_range": f"{minus_min}~{minus_max} step {minus_step}",
        "n_combos":   len(range(plus_min, plus_max+1, plus_step)) * len(range(minus_min, minus_max+1, minus_step)),
        "n_tickers_total": len(loaded_all),
    }
    (output_dir / "streak_grid_meta.json").write_text(
        _json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    results: dict[str, pd.DataFrame] = {}
    targets = [("all", loaded_all)] + [
        (g, [(tk, ev, lc, ic, grp) for tk, ev, lc, ic, grp in loaded_all if grp == g])
        for g in ALL_GROUPS
    ]

    for group_label, loaded in targets:
        if not loaded:
            print(f"[streak_grid] {group_label}: 데이터 없음, 건너뜀", flush=True)
            continue
        print(f"[streak_grid] [{group_label}] 그리드 서치 시작 — {len(loaded)}개 ticker", flush=True)
        df = _grid_search(loaded, plus_min, plus_max, plus_step,
                          minus_min, minus_max, minus_step, top_n, group_label, debug=debug)
        out_csv = output_dir / f"streak_grid_{group_label}.csv"
        df.to_csv(out_csv, index=False)
        print(f"[streak_grid] [{group_label}] 완료 → {out_csv.name}", flush=True)
        results[group_label] = df

    # ── 전체 그룹 종목별 개별 grid search 추가 실행 (4개 그룹 동시) ──
    PER_TICKER_GROUPS = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]
    per_ticker_group_data = {
        g: [(tk, ev, lc, ic, grp) for tk, ev, lc, ic, grp in loaded_all if grp == g]
        for g in PER_TICKER_GROUPS
    }

    def _run_per_ticker_group(g: str) -> None:
        group_loaded = per_ticker_group_data[g]
        if not group_loaded:
            _debug_log(debug, f"[streak_grid] [{g}] 종목별 grid search: 데이터 없음, 건너뜀", flush=True)
            return
        run_per_ticker_group(
            group_loaded, g, output_dir,
            plus_min, plus_max, plus_step,
            minus_min, minus_max, minus_step, top_n,
            workers=workers, debug=debug,
        )

    with ThreadPoolExecutor(max_workers=_DEFAULT_WORKERS) as ex:
        per_ticker_futs = [ex.submit(_run_per_ticker_group, g) for g in PER_TICKER_GROUPS]
        for fut in as_completed(per_ticker_futs):
            fut.result()  # 예외 전파

    return results


def run_per_ticker_group(
    loaded_group: list[tuple],
    group_name: str,
    output_dir: "Path",
    plus_min: int = 4, plus_max: int = 40, plus_step: int = 2,
    minus_min: int = 4, minus_max: int = 10, minus_step: int = 2,
    top_n: int = 30,
    workers: int = _DEFAULT_WORKERS,
    debug: bool = False,
) -> dict[str, dict]:
    """ETF 그룹 내 각 ticker별로 독립적인 grid search 수행 (병렬).

    output_dir/per_ticker/{group_name}/{ticker}.csv 저장.
    반환: {ticker: {plus_days, minus_days, avg_return, hit_rate}} (최적 파라미터 요약)
    """
    import json as _json
    per_dir = Path(output_dir) / "per_ticker" / group_name
    per_dir.mkdir(parents=True, exist_ok=True)

    n = len(loaded_group)

    def _one_ticker(item: tuple, idx: int, total: int) -> tuple[str, dict]:
        tk, ev, lc, ic, grp = item
        _debug_log(debug, f"[streak_grid] [{group_name}] {tk} grid search...", flush=True)
        single = [(tk, ev, lc, ic, grp)]
        label = f"{group_name}/{tk} ({idx}/{total})"
        df = _grid_search(single, plus_min, plus_max, plus_step,
                          minus_min, minus_max, minus_step, top_n,
                          label, debug=debug)
        df.to_csv(per_dir / f"{tk}.csv", index=False)
        best = df.iloc[0]
        if debug:
            print(f"[streak_grid][debug] [{group_name}/{tk}] 최적: "
                  f"plus={best.plus_days} minus={best.minus_days} "
                  f"return={best.avg_return:.1f}%", flush=True)
        return tk, {
            "plus_days":  int(best.plus_days),
            "minus_days": int(best.minus_days),
            "avg_return": float(best.avg_return),
            "hit_rate":   float(best.hit_rate),
        }

    summary: dict[str, dict] = {}
    print(f"[streak_grid] [{group_name}] 종목별 grid search 시작 — {n}개 ticker (workers={min(workers, n)})", flush=True)
    with ThreadPoolExecutor(max_workers=min(workers, n)) as ex:
        futs = {
            ex.submit(_one_ticker, item, idx, n): item[0]
            for idx, item in enumerate(loaded_group, 1)
        }
        done = 0
        for fut in as_completed(futs):
            tk, best_dict = fut.result()
            summary[tk] = best_dict
            done += 1
            print(f"[streak_grid] [{group_name}] 완료 {done}/{n}: {tk}", flush=True)

    (per_dir / "_summary.json").write_text(
        _json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[streak_grid] [{group_name}] 종목별 전체 완료 — {len(summary)}개 → {per_dir}", flush=True)
    return summary


def _grid_search(
    loaded: list[tuple],
    plus_min: int, plus_max: int, plus_step: int,
    minus_min: int, minus_max: int, minus_step: int,
    top_n: int, label: str = "",
    debug: bool = False,
) -> pd.DataFrame:
    """loaded = [(ticker, events, last_close, ic, group), ...] 로 grid search."""
    p_range = range(plus_min, plus_max + 1, plus_step)
    m_range = range(minus_min, minus_max + 1, minus_step)
    n_combos = len(p_range) * len(m_range)

    if debug:
        print(f"[streak_grid][debug] [{label}] grid search 시작 — "
              f"plus={plus_min}~{plus_max} step={plus_step}, "
              f"minus={minus_min}~{minus_max} step={minus_step}, "
              f"조합={n_combos}, tickers={len(loaded)}", flush=True)

    rows: list[dict] = []
    done = 0
    t0 = time.perf_counter()
    for p in p_range:
        for m in m_range:
            returns = [_simulate_one(ev, p, m, ic, lc)
                       for _, ev, lc, ic, *_ in loaded]
            s = pd.Series(returns)
            avg  = round(float(s.mean()), 4)
            med  = round(float(s.median()), 4)
            npos = int((s > 0).sum())
            ntot = len(returns)
            hitr = round(float((s > 0).mean() * 100), 2)
            rows.append({
                "plus_days":     p,
                "minus_days":    m,
                "avg_return":    avg,
                "median_return": med,
                "n_positive":    npos,
                "n_total":       ntot,
                "hit_rate":      hitr,
            })
            done += 1
            if debug:
                print(f"[streak_grid][debug] [{label}] ({done:>3}/{n_combos})"
                      f"  plus={p:>3} minus={m:>2}"
                      f"  avg={avg:>9.1f}%  median={med:>8.1f}%"
                      f"  hit={hitr:.1f}%  n_pos={npos}/{ntot}", flush=True)
            elif done % 20 == 0 or done == n_combos:
                elapsed = time.perf_counter() - t0
                eta = elapsed / done * (n_combos - done) if done < n_combos else 0
                print(f"[streak_grid] [{label}]   {done}/{n_combos} ({elapsed:.0f}s, 잔여 ~{eta:.0f}s)", flush=True)

    result_df = pd.DataFrame(rows).sort_values("avg_return", ascending=False).reset_index(drop=True)
    best = result_df.iloc[0]
    if debug:
        _debug_log(debug, f"[streak_grid] [{label}] ★ 최적: plus={best.plus_days} minus={best.minus_days} "
                   f"avg={best.avg_return:.1f}% hit={best.hit_rate:.1f}%", flush=True)
        _debug_log(debug, f"\n[streak_grid] [{label}] === 상위 {min(top_n, len(result_df))}개 ===")
        print(result_df.head(top_n).to_string(index=False))
    return result_df


# ── 5. 그리드 서치 메인 (단일 그룹) ─────────────────────────────────────
def run(
    cfg: config.Config,
    market:     str   = "all",
    group_name: str | None = None,
    start:      date | None = None,
    end:        date | None = None,
    plus_min:   int   = 2,
    plus_max:   int   = 50,
    plus_step:  int   = 1,
    minus_min:  int   = 2,
    minus_max:  int   = 20,
    minus_step: int   = 1,
    workers:    int   = _DEFAULT_WORKERS,
    top_n:      int   = 30,
    output_csv: Path | None = None,
    debug:      bool  = False,
) -> pd.DataFrame:
    """
    (plus_days, minus_days) 전체 조합 수익률 계산.

    반환값: DataFrame(plus_days, minus_days, avg_return, median_return,
                       n_positive, n_total, hit_rate)
            — avg_return 내림차순 정렬
    """
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        log.error("instruments.csv 없음. universe 먼저 실행")
        return pd.DataFrame()

    if market != "all":
        inst = inst[inst["market"] == market.upper()]
    if group_name:
        inst = inst[inst["group_name"] == group_name]

    initial_capital = cfg.strategies["initial_capital"]

    # --- ticker별 streak 로딩 (thread pool) ---
    _debug_log(debug, f"[streak_grid] ticker streak 계산 중... ({len(inst)}개, workers={workers})", flush=True)
    t0 = time.perf_counter()

    ticker_list = [(str(r["ticker"]), str(r["market"]), str(r["currency"]))
                   for _, r in inst.iterrows()]

    n_total = len(ticker_list)
    loaded: list[tuple] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_load_ticker, cfg, tk, mkt, start, end): (tk, mkt, cur)
            for tk, mkt, cur in ticker_list
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            tk, mkt, cur = futs[fut]
            result = fut.result()
            if result is not None:
                ticker, events, last_close = result
                ic = float(initial_capital.get("KRW" if mkt == "KR" else "USD", 1000))
                loaded.append((ticker, events, last_close, ic))
                if debug:
                    n_ev = sum(len(v) for v in events.get("buy", {}).values())
                    print(f"[streak_grid][debug] ({done}/{n_total}) {mkt}/{tk}"
                          f" → buy_events={n_ev} last_close={last_close:,.1f}", flush=True)
            else:
                if debug:
                    print(f"[streak_grid][debug] ({done}/{n_total}) {mkt}/{tk} → SKIP", flush=True)
            if debug and (done % 50 == 0 or done == n_total):
                _debug_log(debug, f"[streak_grid]   로딩 {done}/{n_total}", flush=True)

    _debug_log(debug, f"[streak_grid] 유효 ticker={len(loaded)}개, elapsed={time.perf_counter()-t0:.1f}s", flush=True)

    if not loaded:
        _debug_log(debug, "[streak_grid] 유효 ticker 없음. 종료", flush=True)
        return pd.DataFrame()

    # --- (plus_days, minus_days) 그리드 서치 ---
    lbl = group_name or market
    result_df = _grid_search(loaded, plus_min, plus_max, plus_step,
                              minus_min, minus_max, minus_step, top_n, lbl, debug=debug)

    # CSV 저장
    if output_csv:
        result_df.to_csv(output_csv, index=False)
        _debug_log(debug, f"[streak_grid] 전체 결과 저장: {output_csv}", flush=True)

    total_elapsed = 0  # _grid_search 내부 측정
    _debug_log(debug, f"[streak_grid] 완료 — 전체 {total_elapsed:.1f}s", flush=True)
    return result_df
