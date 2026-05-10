"""plus_days / minus_days 그리드 서치 — type2_2 계열 최적화.

전략: MA10M_UPDOWN 이 + 방향으로 P일 연속 → 전액 매수
      MA10M_UPDOWN 이 - 방향으로 M일 연속 → 전량 매도

접근:
  1) 각 ticker 의 streak(연속일수) 을 한 번만 계산 (O(N_tickers × N_rows)).
  2) (P, M) 조합별 이벤트 필터링 + 간략 시뮬레이션 (O(N_combos × N_events_per_ticker)).
  3) 전체 ticker 의 평균 수익률 / 양수 비율로 최적 파라미터 선정.
"""
from __future__ import annotations

import logging
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


# ── 5. 그리드 서치 메인 ─────────────────────────────────────────────────
def run(
    cfg: config.Config,
    market:     str   = "all",
    start:      date | None = None,
    end:        date | None = None,
    plus_min:   int   = 2,
    plus_max:   int   = 50,
    plus_step:  int   = 1,
    minus_min:  int   = 2,
    minus_max:  int   = 20,
    minus_step: int   = 1,
    workers:    int   = 4,
    top_n:      int   = 30,
    output_csv: Path | None = None,
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

    initial_capital = cfg.strategies["initial_capital"]

    # --- ticker별 streak 로딩 (thread pool) ---
    tprint(f"[streak_grid] ticker streak 계산 중... ({len(inst)}개, workers={workers})", flush=True)
    t0 = time.perf_counter()

    ticker_list = [(str(r["ticker"]), str(r["market"]), str(r["currency"]))
                   for _, r in inst.iterrows()]

    loaded: list[tuple] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_load_ticker, cfg, tk, mkt, start, end): (tk, mkt, cur)
            for tk, mkt, cur in ticker_list
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            if done % 50 == 0 or done == len(futs):
                tprint(f"[streak_grid]   로딩 {done}/{len(futs)}", flush=True)
            result = fut.result()
            if result is not None:
                tk, mkt, cur = futs[fut]
                ticker, events, last_close = result
                ic = float(initial_capital.get(
                    "KRW" if mkt == "KR" else "USD",
                    1000
                ))
                loaded.append((ticker, events, last_close, ic))

    tprint(f"[streak_grid] 유효 ticker={len(loaded)}개, elapsed={time.perf_counter()-t0:.1f}s", flush=True)

    if not loaded:
        tprint("[streak_grid] 유효 ticker 없음. 종료", flush=True)
        return pd.DataFrame()

    # --- (plus_days, minus_days) 그리드 서치 ---
    p_range = range(plus_min,  plus_max  + 1, plus_step)
    m_range = range(minus_min, minus_max + 1, minus_step)
    n_combos = len(p_range) * len(m_range)

    tprint(f"[streak_grid] 그리드 서치 시작: plus={plus_min}~{plus_max} step={plus_step}, "
          f"minus={minus_min}~{minus_max} step={minus_step}", flush=True)
    tprint(f"[streak_grid]   조합 수={n_combos}, ticker={len(loaded)}", flush=True)
    t0 = time.perf_counter()

    rows: list[dict] = []
    done = 0

    for p in p_range:
        for m in m_range:
            returns: list[float] = []
            for ticker, events, last_close, ic in loaded:
                ret = _simulate_one(events, p, m, ic, last_close)
                returns.append(ret)

            if not returns:
                continue

            s = pd.Series(returns)
            rows.append({
                "plus_days":    p,
                "minus_days":   m,
                "avg_return":   round(float(s.mean()), 4),
                "median_return": round(float(s.median()), 4),
                "n_positive":   int((s > 0).sum()),
                "n_total":      len(returns),
                "hit_rate":     round(float((s > 0).mean() * 100), 2),
            })
            done += 1
            if done % 100 == 0 or done == n_combos:
                elapsed = time.perf_counter() - t0
                eta = elapsed / done * (n_combos - done) if done < n_combos else 0
                tprint(f"[streak_grid]   {done}/{n_combos} 완료 "
                       f"({elapsed:.0f}s 경과, 잔여 ~{eta:.0f}s)", flush=True)

    result_df = pd.DataFrame(rows).sort_values("avg_return", ascending=False).reset_index(drop=True)

    # 상위 N개 출력
    tprint(f"\n[streak_grid] === 상위 {min(top_n, len(result_df))}개 (avg_return 기준) ===")
    print(result_df.head(top_n).to_string(index=False))  # 표 데이터는 timestamp 불필요

    # 최적값 강조
    best = result_df.iloc[0]
    tprint(f"\n[streak_grid] ★ 최적 파라미터: plus_days={best.plus_days}, "
           f"minus_days={best.minus_days}  "
           f"avg_return={best.avg_return:.2f}%  "
           f"hit_rate={best.hit_rate:.1f}%")

    # CSV 저장
    if output_csv:
        result_df.to_csv(output_csv, index=False)
        tprint(f"[streak_grid] 전체 결과 저장: {output_csv}", flush=True)

    total_elapsed = time.perf_counter() - t0
    tprint(f"[streak_grid] 완료 — 전체 {total_elapsed:.1f}s", flush=True)
    return result_df
