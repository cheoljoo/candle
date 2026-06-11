"""Universe 일괄 갱신 — instruments.csv + universe/*_membership.csv + etf_*.csv."""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import pandas as pd

from .. import config
from ..io_report import announce
from ..storage import csv_io, paths
from . import etf, kospi200, sp500

log = logging.getLogger(__name__)


_STABLE_DAYS = 5   # 진입/퇴출 안정성 확인 기간 (거래일)
_EXIT_DAYS = 20    # 퇴출 확정 연속 부재 기간 (거래일, ≈1개월)


def _record_membership_changes(
    data_dir,
    group: str,
    market: str,
    as_of: date,
    new_members: pd.DataFrame,
) -> int:
    """이전 스냅샷과 비교해 진입/퇴출 변동을 membership_changes.csv 에 append.

    노이즈 방지 기준:
    - 퇴출: 최근 _EXIT_DAYS(≈1개월) 거래일 스냅샷에 단 한 번도 등장하지 않고 오늘도 없으며,
            그 이전 _STABLE_DAYS 거래일 스냅샷 모두에 존재했던 종목.
            최초 부재일 기준으로 단 1회 기록 (upsert 중복 방지).
    - 진입: 과거 스냅샷 전체에 없었는데 오늘 처음 등장한 종목.
    """
    changes_path = paths.membership_changes_csv(data_dir)
    mem_path = paths.membership_csv(data_dir, group)

    if not mem_path.exists():
        return 0  # 최초 실행 — 비교 대상 없음

    mem = pd.read_csv(mem_path, dtype=str)
    past = mem[mem["from_date"] < as_of.isoformat()]
    if past.empty:
        return 0

    all_prev_dates = sorted(past["from_date"].unique())
    ever_prev = set(past["ticker"].tolist())
    cur_tickers = set(new_members["ticker"].astype(str).tolist())
    name_map = dict(zip(new_members["ticker"].astype(str), new_members.get("name", pd.Series(dtype=str))))

    # instruments.csv 에서 퇴출 종목 name 조회 (아직 instruments 갱신 전이므로 가능)
    inst_name_map: dict[str, str] = {}
    inst_p = data_dir / "instruments.csv"
    if inst_p.exists():
        try:
            inst_df = pd.read_csv(inst_p, dtype=str)
            inst_name_map = dict(zip(inst_df["ticker"].astype(str), inst_df["name"].astype(str)))
        except Exception:
            pass

    # ── 진입 판정 ───────────────────────────────────────────────────────────
    # 과거 스냅샷 전체에 없었는데 오늘 처음 등장한 종목
    entered = sorted(cur_tickers - ever_prev)

    # ── 퇴출 판정 (_EXIT_DAYS ≈ 1개월 연속 부재) ──────────────────────────
    # _EXIT_DAYS + _STABLE_DAYS 일치의 스냅샷이 있어야 판정 가능
    exited_with_dates: list[tuple[str, str]] = []  # (ticker, first_absent_date)
    if len(all_prev_dates) >= _EXIT_DAYS + _STABLE_DAYS:
        recent_dates = set(all_prev_dates[-_EXIT_DAYS:])
        # 최근 _EXIT_DAYS 동안 단 한 번도 등장하지 않고 오늘도 없는 종목
        ever_in_recent = set(past[past["from_date"].isin(recent_dates)]["ticker"].tolist())
        absent_candidates = (ever_prev - ever_in_recent) - cur_tickers

        # 그 이전 _STABLE_DAYS 거래일 스냅샷 모두에 안정적으로 존재했던 종목
        pre_exit_dates = all_prev_dates[:-_EXIT_DAYS]
        stable_dates = pre_exit_dates[-_STABLE_DAYS:]
        stable_before: set[str] | None = None
        for d in stable_dates:
            day_set = set(past[past["from_date"] == d]["ticker"].tolist())
            stable_before = day_set if stable_before is None else stable_before & day_set

        for t in sorted(absent_candidates & (stable_before or set())):
            # 최초 부재일: 마지막 등장일 직후 스냅샷 날짜 (upsert 중복 방지)
            last_seen = past[past["ticker"] == t]["from_date"].max()
            after = [d for d in all_prev_dates if d > last_seen]
            first_absent = after[0] if after else as_of.isoformat()
            exited_with_dates.append((t, first_absent))

    # 변동 비율이 10% 이상이면 데이터 노이즈(fallback 오염)로 간주하고 기록 스킵
    total = max(len(cur_tickers), 1)
    noise_threshold = max(10, int(total * 0.10))
    if len(entered) >= noise_threshold or len(exited_with_dates) >= noise_threshold:
        log.warning(
            f"{group} {as_of.isoformat()} 변동 {len(entered)}진입/{len(exited_with_dates)}퇴출 — "
            f"임계치({noise_threshold}) 초과, 노이즈로 간주하여 기록 스킵"
        )
        return 0

    entries = [
        {"date": as_of.isoformat(), "group": group, "market": market,
         "ticker": t, "name": name_map.get(t, "") or inst_name_map.get(t, ""), "event_type": "진입"}
        for t in entered
    ]
    exits = [
        {"date": first_absent, "group": group, "market": market,
         "ticker": t, "name": inst_name_map.get(t, ""), "event_type": "퇴출"}
        for t, first_absent in exited_with_dates
    ]
    rows = entries + exits
    if not rows:
        return 0

    new_df = pd.DataFrame(rows)
    csv_io.upsert_by_keys(
        changes_path,
        new_df,
        key_cols=["date", "group", "ticker", "event_type"],
        sort_cols=["date", "group", "event_type", "ticker"],
    )
    return len(rows)


def update(cfg: config.Config, as_of: date, small: bool = False, debug: bool = False) -> dict[str, int]:
    announce(
        "universe",
        inputs=[
            ("config/universe.yml",
             "그룹 정의(KOSPI200/SP500/ETF_KR/ETF_US) + ETF 고정 list + small_universe 항목"),
        ],
        outputs=[
            ("data/instruments.csv",
             "전체 종목 마스터 — ticker,name,market,group_name,currency,active"),
            ("data/universe/kospi200_membership.csv",
             "KOSPI200 시점별 멤버십 — ticker,from_date,to_date(빈값=현재 포함)"),
            ("data/universe/sp500_membership.csv",
             "S&P500 시점별 멤버십 — 동일 스키마"),
            ("data/universe/etf_kr.csv",
             "한국상장 ETF list — ticker,name (이름→ticker 매핑은 pykrx로 보강)"),
            ("data/universe/etf_us.csv",
             "미국상장 ETF list — ticker,name"),
        ],
    )
    counts: dict[str, int] = {}
    data_dir = cfg.data_dir
    universe_cfg = cfg.universe

    if small:
        if debug:
            print("[universe][debug] small 모드 build")
        return _build_small(cfg, universe_cfg)

    # KOSPI200
    if debug:
        print(f"[universe][debug] KOSPI200 fetch start (as_of={as_of.isoformat()})")
    t0 = time.perf_counter()
    try:
        kr_members = kospi200.fetch_members(as_of)
    except Exception as e:
        log.warning(f"KOSPI200 fetch 실패: {e}")
        kr_members = pd.DataFrame(columns=["ticker", "name"])
    if debug:
        print(f"[universe][debug] KOSPI200 fetch end ({time.perf_counter()-t0:.2f}s) — members={len(kr_members)}")
    if not kr_members.empty:
        kr_membership = kr_members.assign(from_date=as_of.isoformat(), to_date="")
        csv_io.upsert_by_keys(
            paths.membership_csv(data_dir, "KOSPI200"),
            kr_membership[["ticker", "from_date", "to_date"]],
            key_cols=["ticker", "from_date"],
            sort_cols=["from_date", "ticker"],
        )
        n_changes = _record_membership_changes(data_dir, "KOSPI200", "KR", as_of, kr_members)
        if debug and n_changes:
            print(f"[universe][debug] KOSPI200 변동 {n_changes}건 기록")
    counts["KOSPI200"] = len(kr_members)

    # SP500
    if debug:
        print("[universe][debug] SP500 fetch start")
    t0 = time.perf_counter()
    try:
        us_members = sp500.fetch_members()
    except Exception as e:
        log.warning(f"SP500 fetch 실패: {e}")
        us_members = pd.DataFrame(columns=["ticker", "name"])
    if debug:
        print(f"[universe][debug] SP500 fetch end ({time.perf_counter()-t0:.2f}s) — members={len(us_members)}")
    if not us_members.empty:
        us_membership = us_members.assign(from_date=as_of.isoformat(), to_date="")
        csv_io.upsert_by_keys(
            paths.membership_csv(data_dir, "SP500"),
            us_membership[["ticker", "from_date", "to_date"]],
            key_cols=["ticker", "from_date"],
            sort_cols=["from_date", "ticker"],
        )
        n_changes = _record_membership_changes(data_dir, "SP500", "US", as_of, us_members)
        if debug and n_changes:
            print(f"[universe][debug] SP500 변동 {n_changes}건 기록")
    counts["SP500"] = len(us_members)

    # ETF KR
    etf_kr_items = universe_cfg["groups"]["ETF_KR"]["items"]
    if debug:
        print(f"[universe][debug] ETF_KR resolve start (items={len(etf_kr_items)})")
    t0 = time.perf_counter()
    try:
        etf_kr_df = etf.resolve_kr_etf_tickers(etf_kr_items)
    except Exception as e:
        log.warning(f"ETF_KR 해석 실패: {e}")
        etf_kr_df = pd.DataFrame(
            [{"ticker": it.get("ticker"), "name": it["name"]} for it in etf_kr_items]
        )
    csv_io.atomic_write(etf_kr_df, paths.etf_list_csv(data_dir, "KR"))
    counts["ETF_KR"] = int(etf_kr_df["ticker"].notna().sum())
    if debug:
        print(f"[universe][debug] ETF_KR resolve end ({time.perf_counter()-t0:.2f}s) — resolved={counts['ETF_KR']}")

    # ETF US
    etf_us_items = universe_cfg["groups"]["ETF_US"]["items"]
    if debug:
        print(f"[universe][debug] ETF_US start (items={len(etf_us_items)})")
    t0 = time.perf_counter()
    etf_us_df = etf.us_etf_df(etf_us_items)
    csv_io.atomic_write(etf_us_df, paths.etf_list_csv(data_dir, "US"))
    counts["ETF_US"] = len(etf_us_df)
    if debug:
        print(f"[universe][debug] ETF_US end ({time.perf_counter()-t0:.2f}s) — count={counts['ETF_US']}")

    # instruments.csv 통합
    rows: list[dict[str, Any]] = []
    for _, r in kr_members.iterrows():
        rows.append({"ticker": r["ticker"], "name": r["name"], "market": "KR",
                     "group_name": "KOSPI200", "currency": "KRW", "active": 1})
    for _, r in us_members.iterrows():
        rows.append({"ticker": r["ticker"], "name": r["name"], "market": "US",
                     "group_name": "SP500", "currency": "USD", "active": 1})
    for _, r in etf_kr_df.iterrows():
        if pd.isna(r["ticker"]):
            continue
        rows.append({"ticker": r["ticker"], "name": r["name"], "market": "KR",
                     "group_name": "ETF_KR", "currency": "KRW", "active": 1})
    for _, r in etf_us_df.iterrows():
        rows.append({"ticker": r["ticker"], "name": r["name"], "market": "US",
                     "group_name": "ETF_US", "currency": "USD", "active": 1})

    # 사용자 메일 요청으로 추가된 ETF (data/universe/etf_user.json) 병합
    user_etf_path = data_dir / "universe" / "etf_user.json"
    if user_etf_path.exists():
        try:
            import json as _json
            user_entries: list[dict] = _json.loads(user_etf_path.read_text(encoding="utf-8"))
            for entry in user_entries:
                if entry.get("ticker"):
                    rows.append({
                        "ticker": entry["ticker"],
                        "name": entry.get("name", entry["ticker"]),
                        "market": entry.get("market", "US"),
                        "group_name": entry.get("group_name", "ETF_US"),
                        "currency": entry.get("currency", "USD"),
                        "active": 1,
                    })
            if debug:
                print(f"[universe][debug] etf_user.json 병합 — {len(user_entries)}개")
        except Exception as e:
            log.warning(f"etf_user.json 로드 실패: {e}")

    inst = pd.DataFrame(rows)
    if not inst.empty:
        inst = inst.drop_duplicates(subset=["ticker"], keep="first")
    csv_io.atomic_write(inst, paths.instruments_csv(data_dir))
    counts["instruments"] = len(inst)
    return counts


def _build_small(cfg: config.Config, universe_cfg: dict[str, Any]) -> dict[str, int]:
    """smoke run / dev 용 작은 universe."""
    rows: list[dict[str, Any]] = []
    small = universe_cfg.get("small_universe", {})
    for market, items in small.items():
        for it in items:
            currency = "KRW" if market == "KR" else "USD"
            rows.append({
                "ticker": it["ticker"], "name": it["name"], "market": market,
                "group_name": it["group"], "currency": currency, "active": 1,
            })
    inst = pd.DataFrame(rows).drop_duplicates(subset=["ticker"])
    csv_io.atomic_write(inst, paths.instruments_csv(cfg.data_dir))
    return {"instruments": len(inst), "small": 1}
