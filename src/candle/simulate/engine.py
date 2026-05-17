"""Simulate engine — 매일 1회 의사결정 → decisions.csv append.

원칙:
- 의사결정은 D일에 일어나고, 체결은 D+1 거래일의 시작가(open).
- source = 'rule:type1_1' | 'rule:type1_2' | ... | 'ai' | 'manual'
- 같은 (date, ticker, source) 는 1행만.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from .. import config
from ..storage import csv_io, paths
from . import manual, ai_advisor

log = logging.getLogger(__name__)


DECISIONS_COLUMNS = [
    "decision_id", "date", "ticker", "source", "action",
    "qty", "price", "reason", "event_date", "raw_json_path",
]
TRADES_COLUMNS = [
    "trade_id", "decision_id", "date", "ticker", "side",
    "price", "qty", "amount", "holding_qty", "holding_value",
]


def decisions_path(cfg: config.Config) -> Path:
    return cfg.output_dir / "simulate" / "decisions.csv"


def trades_path(cfg: config.Config) -> Path:
    return cfg.output_dir / "simulate" / "trades.csv"


def run(cfg: config.Config, on_date: date,
        rule_types: Iterable[str] = ("type1_1", "type1_2", "type2_1", "type2_2", "type2_1b", "type2_2b", "type3"),
        use_ai: bool = True, debug: bool = False) -> dict[str, int]:
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {"decisions": 0}

    rule_decisions: list[dict] = []
    ai_decisions: list[dict] = []

    total = len(inst)
    if debug:
        print(f"[simulate][debug] rule decisions 시작 — {total}개 ticker, on_date={on_date.isoformat()}")

    # 1) Rule decisions: 각 ticker에 대해 각 type 신호 평가
    for i, (_, row) in enumerate(inst.iterrows(), start=1):
        tk = str(row["ticker"])
        mkt = str(row["market"])
        group = str(row["group_name"])
        if debug:
            print(f"[simulate][debug] ({i}/{total}) {mkt}/{tk} ({group}) start")
        t0 = time.perf_counter()
        daily = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, tk))
        if daily.empty:
            if debug:
                print(f"[simulate][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — empty daily")
            continue
        daily = daily.sort_values("date").reset_index(drop=True)
        cur_idx = daily.index[daily["date"] == on_date.isoformat()].tolist()
        if not cur_idx:
            # on_date row가 없으면 그 이전 가장 최근 거래일 row 사용
            past = daily[daily["date"] <= on_date.isoformat()]
            if past.empty:
                if debug:
                    print(f"[simulate][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — no row <= on_date")
                continue
            cur_row = past.iloc[-1]
        else:
            cur_row = daily.loc[cur_idx[0]]

        before = len(rule_decisions)
        for type_name in rule_types:
            res = _rule_signal(type_name, daily, cur_row, cfg)
            if res is None:
                continue
            action, reason, event_date = res
            rule_decisions.append({
                "decision_id": str(uuid.uuid4())[:8],
                "date": str(cur_row.get("date", on_date.isoformat())),  # 마지막 거래일(신호 확인일)
                "ticker": tk,
                "source": f"rule:{type_name}",
                "action": action,
                "qty": _rule_qty(type_name, cfg, action),
                "price": float(pd.to_numeric(cur_row.get("close"), errors="coerce")),
                "reason": reason,
                "event_date": event_date,
                "raw_json_path": "",
            })
        if debug:
            added = len(rule_decisions) - before
            print(f"[simulate][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — rule_decisions+={added}")

    # 2) AI decisions
    if use_ai:
        ai_decisions = ai_advisor.run_for_universe(cfg, inst, on_date)

    # 3) Manual decisions
    man_df = manual.load(cfg, on_date)
    manual_decisions: list[dict] = []
    for _, m in man_df.iterrows():
        manual_decisions.append({
            "decision_id": str(uuid.uuid4())[:8],
            "date": on_date.isoformat(),
            "ticker": str(m["ticker"]),
            "source": "manual",
            "action": str(m["action"]),
            "qty": (float(m["qty"]) if not pd.isna(m.get("qty")) else None),
            "price": None,
            "reason": str(m.get("reason", "")),
            "raw_json_path": "",
        })

    all_dec = rule_decisions + ai_decisions + manual_decisions
    if all_dec:
        new_df = pd.DataFrame(all_dec, columns=DECISIONS_COLUMNS)
        csv_io.upsert_by_keys(
            decisions_path(cfg), new_df,
            key_cols=["date", "ticker", "source"],
            sort_cols=["date", "ticker", "source"],
            overwrite=True,
        )

    # 4) D+1 시작가 체결 시뮬레이션
    settled = _settle_yesterday_decisions(cfg, on_date)

    return {
        "rule": len(rule_decisions),
        "ai": len(ai_decisions),
        "manual": len(manual_decisions),
        "settled_today": settled,
    }


def _rule_qty(type_name: str, cfg: config.Config, action: str) -> float | None:
    s = cfg.strategies
    if type_name == "type1_1":
        return float(s["type1_1"]["qty"])
    if type_name in ("type2_1", "type2_1b"):
        return float(s[type_name]["qty"])
    if type_name == "type3":
        return None  # "전액" 입금 후 매수
    return None  # 1_2, 2_2, 2_2b = 전액/전량


def _rule_signal(type_name: str, daily: pd.DataFrame, cur_row: pd.Series,
                 cfg: config.Config) -> tuple[str, str, str] | None:
    """오늘 row 기준으로 신호 발화 여부.
    반환: (action, reason, event_date) — event_date는 변곡점/연속 시작일."""
    s = cfg.strategies
    cur_date = str(cur_row["date"])
    if type_name in ("type1_1", "type1_2"):
        infl = cur_row.get("inflection")
        if pd.isna(infl):
            return None
        if infl == "-→+":
            return ("buy", "MA10M 변곡 -→+", cur_date)
        if infl == "+→-":
            return ("sell", "MA10M 변곡 +→-", cur_date)
        return None

    if type_name in ("type2_1", "type2_2", "type2_1b", "type2_2b"):
        plus_days = int(s[type_name]["plus_days"])
        minus_days = int(s[type_name]["minus_days"])
        return _streak_signal(daily, cur_row, plus_days, minus_days)

    if type_name == "type3":
        return ("buy", "적립식 90일 주기", cur_date)

    return None


def _streak_signal(daily: pd.DataFrame, cur_row: pd.Series,
                   plus_days: int, minus_days: int) -> tuple[str, str, str] | None:
    cur_date = cur_row["date"]
    idx_list = daily.index[daily["date"] == cur_date].tolist()
    if not idx_list:
        return None
    idx = idx_list[0]
    sign = cur_row.get("ma10m_updown")
    if pd.isna(sign) or sign not in ("+", "-"):
        return None
    streak = 1
    for j in range(idx - 1, -1, -1):
        prev = daily.iloc[j].get("ma10m_updown")
        if prev == sign:
            streak += 1
        else:
            break
    # 연속 시작일 (패턴이 시작된 날) 계산
    streak_start_idx = max(0, idx - (streak - 1))
    streak_start_date = str(daily.iloc[streak_start_idx]["date"])
    if sign == "+" and streak == plus_days:
        return ("buy", f"+{plus_days}일 연속 유지", streak_start_date)
    if sign == "-" and streak == minus_days:
        return ("sell", f"-{minus_days}일 연속 유지", streak_start_date)
    return None


def _settle_yesterday_decisions(cfg: config.Config, on_date: date) -> int:
    """on_date를 D 라 할 때, D-1(거래일)의 decisions 중 buy/sell을 D 시작가로 체결.

    이 단순화 버전은 'on_date 의 직전 거래일이 D-1' 가정 (휴장 보정 X).
    """
    dec = csv_io.read(decisions_path(cfg))
    if dec.empty:
        return 0
    # on_date의 일봉 시작가가 있는 ticker만 체결
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    market_map = {str(r["ticker"]): str(r["market"]) for _, r in inst.iterrows()}

    candidates = dec[(dec["action"].isin(["buy", "sell"]))].copy()
    if candidates.empty:
        return 0

    # 이미 체결된 decision_id 제외
    exist_trades = csv_io.read(trades_path(cfg))
    settled_ids = set(exist_trades["decision_id"].astype(str)) if not exist_trades.empty else set()
    candidates = candidates[~candidates["decision_id"].astype(str).isin(settled_ids)]
    if candidates.empty:
        return 0

    new_trades: list[dict] = []
    for _, d in candidates.iterrows():
        tk = str(d["ticker"])
        mkt = market_map.get(tk)
        if not mkt:
            continue
        daily = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, tk))
        if daily.empty:
            continue
        daily = daily.sort_values("date").reset_index(drop=True)
        # decision date 다음 거래일 row
        decision_date = str(d["date"])
        nxt = daily[daily["date"] > decision_date]
        if nxt.empty:
            continue
        ex = nxt.iloc[0]
        if ex["date"] > on_date.isoformat():
            continue  # on_date까지 거래일이 없음
        open_px = pd.to_numeric(pd.Series([ex["open"]]), errors="coerce").iloc[0]
        if pd.isna(open_px):
            continue
        qty = d.get("qty")
        if pd.isna(qty) or qty is None or qty == "":
            qty_f = 0.0  # 전액/전량은 별도 처리 필요. 기본 0
        else:
            qty_f = float(qty)
        new_trades.append({
            "trade_id": str(uuid.uuid4())[:8],
            "decision_id": str(d["decision_id"]),
            "date": str(ex["date"]),
            "ticker": tk,
            "side": str(d["action"]),
            "price": float(open_px),
            "qty": qty_f,
            "amount": float(open_px) * qty_f,
            "holding_qty": None,  # 본격 portfolio tracking은 차후
            "holding_value": None,
        })
    if not new_trades:
        return 0
    new_df = pd.DataFrame(new_trades, columns=TRADES_COLUMNS)
    csv_io.upsert_by_keys(
        trades_path(cfg), new_df,
        key_cols=["trade_id"],
        sort_cols=["date", "ticker"],
        overwrite=False,
    )
    return len(new_trades)
