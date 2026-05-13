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
