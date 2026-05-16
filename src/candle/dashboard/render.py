"""Static dashboard renderer — Jinja2 → dashboard_site/index.html."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config
from ..io_report import announce, tprint
from ..storage import csv_io, paths
from ..simulate import engine

log = logging.getLogger(__name__)


def render(cfg: config.Config, on_date: date,
           out_dir: Path | None = None, debug: bool = False) -> dict:
    out_dir = out_dir or (cfg.repo_root / "dashboard_site")
    rel_out = out_dir.relative_to(cfg.repo_root) if out_dir.is_absolute() else out_dir
    announce(
        f"dashboard --today {on_date.isoformat()}",
        inputs=[
            ("output/compare/strategy_summary.csv",
             "전략별 KPI 표 (총자산/수익률/매수·매도)"),
            ("output/simulate/decisions.csv",
             "오늘의 의사결정 (rule/ai/manual 3 그룹 탭)"),
            ("data/instruments.csv + data/daily/{KR|US}/{ticker}.csv",
             "오늘 변곡점 발생 종목 lookup (Action Required 섹션)"),
            ("src/candle/dashboard/templates/index.html",
             "Jinja2 템플릿 (Tailwind + Alpine.js)"),
        ],
        outputs=[
            (f"{rel_out}/index.html",
             "정적 dashboard — 전략 KPI / 오늘 결정 (rule/ai/manual) / 변곡점 발생 종목"),
            (f"{rel_out}/data/compare.json",
             "compare strategy_summary 의 JSON 사본 (외부 도구 연동용)"),
            (f"{rel_out}/data/decisions.json",
             "오늘 의사결정 JSON 사본 — ticker,source,action,qty,price,reason,tab"),
            (f"{rel_out}/data/inflections.json",
             "오늘 변곡점 발생 종목 JSON — ticker,group,inflection,close,ma10m,per,pbr,rank"),
        ],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    _t_total = time.perf_counter()

    # ── 데이터 수집 ────────────────────────────────────────────────────────
    tprint("[dashboard] compare 결과 로딩...", flush=True)
    t0 = time.perf_counter()
    compare_all = _load_compare_all(cfg)
    compare_period_list = list(compare_all.keys())
    tprint(f"[dashboard] compare 완료 — {len(compare_period_list)}개 period ({time.perf_counter()-t0:.1f}s)", flush=True)

    _first_rows = next(iter(compare_all.values()), []) if compare_all else []
    best_strategy = (
        max(_first_rows, key=lambda r: r["수익률"])["strategy"]
        if _first_rows else None
    )

    tprint(f"[dashboard] 의사결정 로딩 (on_date={on_date.isoformat()})...", flush=True)
    t0 = time.perf_counter()
    rank_map = _load_rank_snapshot(cfg)
    decisions, counts, type_counts, actual_date = _load_decisions(cfg, on_date, rank_map=rank_map)
    tprint(f"[dashboard] 의사결정 완료 — {len(decisions)}건 ({time.perf_counter()-t0:.1f}s)", flush=True)

    tprint(f"[dashboard] 변곡점 lookup (on_date={on_date.isoformat()})...", flush=True)
    t0 = time.perf_counter()
    inflections = _load_inflections(cfg, on_date, debug=debug)
    tprint(f"[dashboard] 변곡점 완료 — {len(inflections)}종목 ({time.perf_counter()-t0:.1f}s)", flush=True)

    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))

    # ticker → 종목명 매핑 (index.html inflection 테이블에서 사용)
    name_map: dict[str, str] = {}
    if not inst.empty:
        for _, r in inst.iterrows():
            name_map[str(r["ticker"])] = str(r["name"])

    tprint(f"[dashboard] 기간별 ticker 수익률 테이블 구성 ({len(inst)}개 ticker)...", flush=True)
    t0 = time.perf_counter()
    period_table, bt_periods = _build_period_table(cfg)
    tprint(f"[dashboard] 수익률 테이블 완료 — {len(period_table)}개 ticker × {len(bt_periods)}기간 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # 외국인/기관 최근 5일 스냅샷 (KOSPI200)
    tprint("[dashboard] 외국인/기관 스냅샷 로딩...", flush=True)
    t0 = time.perf_counter()
    foreign_snapshot = _load_foreign_snapshot(cfg)
    tprint(f"[dashboard] 외국인/기관 완료 — {len(foreign_snapshot)}개 종목 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # ticker → period_table row (index.html inflection 테이블 기간수익률 조회용)
    period_table_by_ticker: dict[str, dict] = {r["ticker"]: r for r in period_table}

    # 그룹별 분리
    groups = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]
    period_table_by_group: dict[str, list[dict]] = {
        g: [r for r in period_table if r["group_name"] == g] for g in groups
    }

    # 데이터 부족 종목 감지
    # MA10M 계산에 최소 200행 필요 → 그 미만이면 "신규 상장 추정"으로 분류
    MA10M_MIN_ROWS = 200
    tickers_in_table: set[str] = {r["ticker"] for r in period_table}

    # instruments 1회 순회 → ticker별 CSV 행 수 수집 + 신규상장(미포함) 리스트 구축
    ticker_rc: dict[str, int] = {}
    new_listings_by_group: dict[str, list[dict]] = {g: [] for g in groups}
    if not inst.empty:
        for _, r in inst.iterrows():
            tk = str(r["ticker"])
            grp = str(r.get("group_name", ""))
            market = str(r.get("market", "KR"))
            csv_path = paths.daily_csv(cfg.data_dir, market, tk)
            rc = 0
            if csv_path.exists():
                try:
                    rc = sum(1 for _ in csv_path.open("r", encoding="utf-8")) - 1  # 헤더 제외
                except Exception:
                    pass
            ticker_rc[tk] = rc
            if tk not in tickers_in_table and grp in groups:
                new_listings_by_group[grp].append({
                    "ticker": tk,
                    "name": str(r.get("name", tk)),
                    "row_count": rc,
                    "needed": MA10M_MIN_ROWS,
                })

    # period_table 행에 data_lacking / row_count 필드 추가 (템플릿 뱃지 표시용)
    for pt_row in period_table:
        rc = ticker_rc.get(pt_row["ticker"], MA10M_MIN_ROWS)
        pt_row["data_lacking"] = rc < MA10M_MIN_ROWS
        pt_row["row_count"] = rc

    # ── 종목별 거래 JSON 미리 생성 (group_returns 링크 표시 여부 판단용) ────
    tprint("[dashboard] 종목별 거래 JSON 사전 생성 중...", flush=True)
    t0 = time.perf_counter()
    _generate_trade_jsons(cfg, out_dir)
    _trades_dir = out_dir / "data" / "trades"
    tickers_with_trades: set[str] = {p.stem for p in _trades_dir.glob("*.json")} if _trades_dir.exists() else set()
    tprint(f"[dashboard] 거래 JSON 완료 — {len(tickers_with_trades)}개 종목 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # ── 시장 시그널 KR (프로그램 비차익 + 금융투자) ───────────────────────
    tprint("[dashboard] 시장 시그널 KR 로딩...", flush=True)
    t0 = time.perf_counter()
    market_signal_ctx = _load_market_signals(cfg, on_date)
    tprint(f"[dashboard] 시장 시그널 KR 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # ── 시장 시그널 US (VIX + 미국채 수익률) ─────────────────────────────
    tprint("[dashboard] 시장 시그널 US 로딩...", flush=True)
    t0 = time.perf_counter()
    market_signal_us_ctx = _load_market_signals_us(cfg, on_date)
    tprint(f"[dashboard] 시장 시그널 US 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # ── 템플릿 렌더 ────────────────────────────────────────────────────────
    def _uk_fmt(value: object) -> str:
        """억 단위 숫자를 '3조 3664억' 형태로 변환."""
        try:
            v = int(value)
        except (TypeError, ValueError):
            return str(value)
        neg = v < 0
        av = abs(v)
        if av >= 10_000:
            jo = av // 10_000
            uk = av % 10_000
            result = f"{jo:,}조 {uk:,}억" if uk else f"{jo:,}조"
        else:
            result = f"{av:,}억"
        return f"-{result}" if neg else result

    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["uk_fmt"] = _uk_fmt

    # 전략 type 이름 설명 (모든 페이지 공통)
    type_descriptions = {
        "type1_1":  ("변곡점 신호 · 고정수량",      "MA10M 교차(-→+) 매수 / (+→-) 매도, 10주 고정"),
        "type1_2":  ("변곡점 신호 · 전액매수",       "MA10M 교차(-→+) 전액 매수 / (+→-) 전량 매도"),
        "type2_1":  ("연속일수(8/4) · 고정수량",    "+8일 연속 → 매수 / -4일 연속 → 매도, 10주 고정"),
        "type2_2":  ("연속일수(8/4) · 전액매수",    "+8일 연속 → 전액 매수 / -4일 연속 → 전량 매도"),
        "type2_1b": ("연속일수(33/5) · 고정수량",   "+33일 연속 → 매수 / -5일 연속 → 매도, 10주 고정"),
        "type2_2b": ("연속일수(33/5) · 전액매수",   "+33일 연속 → 전액 매수 / -5일 연속 → 전량 매도"),
        "type3":    ("적립식 90일 주기",             "90일마다 일정 금액 입금 후 전액 매수 (매도 없음)"),
    }

    common_ctx = dict(
        as_of=actual_date,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        owner_name="이철주",
        owner_email=cfg.recipients.get("owner", ""),
        kpi={
            "tickers": (0 if inst.empty else len(inst)),
            "decisions_today": len(decisions),
            "best_strategy": best_strategy,
        },
        compare_all=compare_all,
        compare_period_list=compare_period_list,
        decisions=decisions,
        counts=counts,
        type_counts=type_counts,
        inflections=inflections,
        period_table=period_table,
        periods=bt_periods,
        type_descriptions=type_descriptions,
        name_map=name_map,
        period_table_by_ticker=period_table_by_ticker,
        market_signals=market_signal_ctx,
        market_signals_us=market_signal_us_ctx,
        foreign_snapshot=foreign_snapshot,
    )

    # index.html
    tprint("[dashboard] index.html 렌더...", flush=True)
    t0 = time.perf_counter()
    tpl = env.get_template("index.html")
    (out_dir / "index.html").write_text(tpl.render(**common_ctx), encoding="utf-8")
    tprint(f"[dashboard] index.html 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # 그룹별 수익률 페이지
    group_tpl = env.get_template("group_returns.html")
    group_file_map = {
        "KOSPI200": "kospi200.html",
        "SP500":    "sp500.html",
        "ETF_KR":   "etf_kr.html",
        "ETF_US":   "etf_us.html",
    }
    for g, fname in group_file_map.items():
        n_rows = len(period_table_by_group.get(g, []))
        tprint(f"[dashboard] {fname} 렌더 ({n_rows}종목)...", flush=True)
        t0 = time.perf_counter()
        group_ctx = dict(common_ctx)
        group_ctx["group_name"] = g
        group_ctx["period_table"] = period_table_by_group.get(g, [])
        group_ctx["new_listings"] = new_listings_by_group.get(g, [])
        group_ctx["foreign_snapshot"] = foreign_snapshot
        group_ctx["tickers_with_trades"] = tickers_with_trades
        (out_dir / fname).write_text(group_tpl.render(**group_ctx), encoding="utf-8")
        tprint(f"[dashboard] {fname} 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # compare.html
    tprint("[dashboard] compare.html 렌더...", flush=True)
    t0 = time.perf_counter()
    cmp_tpl = env.get_template("compare.html")
    (out_dir / "compare.html").write_text(cmp_tpl.render(**common_ctx), encoding="utf-8")
    tprint(f"[dashboard] compare.html 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # decisions.html
    tprint(f"[dashboard] decisions.html 렌더 ({len(decisions)}건)...", flush=True)
    t0 = time.perf_counter()
    dec_tpl = env.get_template("decisions.html")
    (out_dir / "decisions.html").write_text(dec_tpl.render(**common_ctx), encoding="utf-8")
    tprint(f"[dashboard] decisions.html 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # docs.html
    tprint("[dashboard] docs.html 렌더...", flush=True)
    t0 = time.perf_counter()
    docs = _load_docs(cfg)
    docs_tpl = env.get_template("docs.html")
    docs_ctx = dict(common_ctx)
    docs_ctx["docs"] = docs
    (out_dir / "docs.html").write_text(docs_tpl.render(**docs_ctx), encoding="utf-8")
    tprint(f"[dashboard] docs.html 완료 — {len(docs)}개 문서 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # history.html
    tprint("[dashboard] history.html 렌더...", flush=True)
    t0 = time.perf_counter()
    etf_history = _load_etf_history(cfg)
    hist_tpl = env.get_template("history.html")
    hist_ctx = dict(common_ctx)
    hist_ctx["history"] = etf_history
    (out_dir / "history.html").write_text(hist_tpl.render(**hist_ctx), encoding="utf-8")
    tprint(f"[dashboard] history.html 완료 — {len(etf_history)}건 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # optimize.html
    tprint("[dashboard] optimize.html 렌더...", flush=True)
    t0 = time.perf_counter()
    opt_data = _load_optimize_results(cfg)
    opt_tpl = env.get_template("optimize.html")
    opt_ctx = dict(common_ctx)
    opt_ctx["opt_data"] = opt_data
    opt_ctx["opt_groups"] = _OPT_GROUPS
    opt_ctx["opt_labels"] = _OPT_LABELS
    opt_ctx["etf_name_map"] = name_map  # backward compat alias
    opt_ctx["rank_map"] = rank_map
    (out_dir / "optimize.html").write_text(opt_tpl.render(**opt_ctx), encoding="utf-8")
    n_all = len(opt_data.get("all", []))
    tprint(f"[dashboard] optimize.html 완료 — 전체 {n_all}개 조합 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # market_signals.html
    tprint("[dashboard] market_signals.html 렌더...", flush=True)
    t0 = time.perf_counter()
    ms_tpl = env.get_template("market_signals.html")
    (out_dir / "market_signals.html").write_text(ms_tpl.render(**common_ctx), encoding="utf-8")
    tprint(f"[dashboard] market_signals.html 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # ticker_trades.html (정적 셸 — 실제 데이터는 JS fetch로 로딩)
    tprint("[dashboard] ticker_trades.html 렌더...", flush=True)
    t0 = time.perf_counter()
    tt_tpl = env.get_template("ticker_trades.html")
    (out_dir / "ticker_trades.html").write_text(tt_tpl.render(**common_ctx), encoding="utf-8")
    tprint(f"[dashboard] ticker_trades.html 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    # (종목별 거래 JSON은 데이터 준비 단계에서 이미 생성됨)

    # 사이드 JSON
    tprint("[dashboard] JSON 산출물 저장...", flush=True)
    t0 = time.perf_counter()
    data_dir = out_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "compare.json").write_text(
        json.dumps(compare_all, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "inflections.json").write_text(
        json.dumps(inflections, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8")
    (data_dir / "period_table.json").write_text(
        json.dumps({"periods": bt_periods, "rows": period_table},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    tprint(f"[dashboard] JSON 완료 ({time.perf_counter()-t0:.1f}s)", flush=True)

    total_elapsed = time.perf_counter() - _t_total
    tprint(f"[dashboard] 완료 — 10개 파일, 전체 {total_elapsed:.1f}s", flush=True)

    return {
        "out": str(out_dir / "index.html"),
        "pages": 11,
        "decisions": len(decisions),
        "compare_periods": len(compare_period_list),
        "inflections": len(inflections),
        "bt_periods": len(bt_periods),
    }


def _load_compare_all(cfg: config.Config) -> dict[str, list[dict]]:
    """output/compare/ 아래 모든 period/label 디렉터리의 strategy_summary.csv 를 읽어
    {period_label: [strategy rows]} 형태로 반환.

    flat 구조(output/compare/strategy_summary.csv)도 period="" 로 포함.
    """
    result: dict[str, list[dict]] = {}

    # label 디렉터리 스캔
    for label in paths.list_compare_periods(cfg.output_dir):
        p = paths.compare_dir(cfg.output_dir, label) / "strategy_summary.csv"
        df = csv_io.read(p)
        if not df.empty:
            result[label] = df.fillna(0).to_dict(orient="records")

    # flat (label 없음) 도 포함
    flat_p = cfg.output_dir / "compare" / "strategy_summary.csv"
    if flat_p.exists():
        df = csv_io.read(flat_p)
        if not df.empty:
            result["(기본)"] = df.fillna(0).to_dict(orient="records")

    return result


def _load_decisions(cfg: config.Config, on_date: date,
                    rank_map: dict[str, int] | None = None) -> tuple[list[dict], dict, dict, str]:
    df = csv_io.read(engine.decisions_path(cfg))
    if df.empty:
        return [], {"rule": 0, "ai": 0, "manual": 0}, {}, on_date.isoformat()
    today = df[df["date"] == on_date.isoformat()].copy()
    actual_date = on_date.isoformat()
    if today.empty:
        # 오늘 데이터가 없으면 (주말/공휴일/미실행) 가장 최근 날짜로 fallback
        actual_date = str(df["date"].max())
        today = df[df["date"] == actual_date].copy()
    if today.empty:
        return [], {"rule": 0, "ai": 0, "manual": 0}, {}, actual_date

    # type3 (적립식) rule 신호는 표시에서 제외
    today = today[today["source"].astype(str) != "rule:type3"].copy()

    def _tab(s: str) -> str:
        if s.startswith("rule:"):
            return "rule"
        return s

    today["tab"] = today["source"].astype(str).map(_tab)
    counts = {
        "rule": int((today["tab"] == "rule").sum()),
        "ai": int((today["tab"] == "ai").sum()),
        "manual": int((today["tab"] == "manual").sum()),
    }

    # rule type별 건수 (type 필터 버튼용)
    rule_rows = today[today["tab"] == "rule"]
    type_counts: dict[str, int] = {}
    for src in rule_rows["source"].astype(str):
        if src.startswith("rule:"):
            tcode = src[5:]
            type_counts[tcode] = type_counts.get(tcode, 0) + 1

    # 종목 메타 (이름, 그룹) lookup
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    inst_map: dict[str, dict] = {}
    if not inst.empty:
        for _, row in inst.iterrows():
            inst_map[str(row["ticker"])] = {
                "name": str(row["name"]),
                "group_name": str(row["group_name"]),
            }

    etf_groups = {"ETF_KR", "ETF_US"}
    rows = []
    for _, r in today.iterrows():
        tk = str(r["ticker"])
        meta = inst_map.get(tk, {"name": "", "group_name": ""})
        group = meta["group_name"]
        rank = None
        if group not in etf_groups and rank_map:
            rank = rank_map.get(tk)
        rows.append({
            "ticker": tk,
            "name": meta["name"],
            "group_name": group,
            "rank_in_group": rank,
            "source": str(r["source"]),
            "action": str(r["action"]),
            "qty": (None if pd.isna(r.get("qty")) or r.get("qty") == "" else float(r["qty"])),
            "price": (None if pd.isna(r.get("price")) or r.get("price") == "" else float(r["price"])),
            "reason": str(r.get("reason", "")) if not pd.isna(r.get("reason")) else "",
            "tab": str(r["tab"]),
        })
    return rows, counts, type_counts, actual_date


def _load_inflections(cfg: config.Config, on_date: date, debug: bool = False) -> list[dict]:
    """오늘 변곡점이 발생한 종목."""
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return []
    target = on_date.isoformat()
    out: list[dict] = []
    total = len(inst)
    _step = max(1, min(50, total // 10))
    if debug:
        tprint(f"[dashboard][debug] inflection scan {total}개 ticker")
    for i, (_, row) in enumerate(inst.iterrows(), start=1):
        if i % _step == 0 or i == total:
            tprint(f"[dashboard] 변곡점 scan {i}/{total} ({i/total*100:.0f}%)", flush=True)
        tk = str(row["ticker"])
        mkt = str(row["market"])
        group = str(row["group_name"])
        if debug:
            tprint(f"[dashboard][debug] ({i}/{total}) {mkt}/{tk} ({group}) start")
        t0 = time.perf_counter()
        df = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, tk))
        if df.empty or "inflection" not in df.columns:
            if debug:
                tprint(f"[dashboard][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — no inflection col")
            continue
        match = df[df["date"] == target]
        if match.empty:
            if debug:
                tprint(f"[dashboard][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — no row on {target}")
            continue
        rec = match.iloc[0]
        infl = rec.get("inflection")
        if pd.isna(infl) or infl == "" or infl is None:
            if debug:
                tprint(f"[dashboard][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — no inflection")
            continue
        out.append({
            "ticker": tk,
            "group_name": str(row["group_name"]),
            "inflection": str(infl),
            "close": _maybe_float(rec.get("close")),
            "ma10m": _maybe_float(rec.get("ma10m")),
            "per": _maybe_float(rec.get("per")),
            "pbr": _maybe_float(rec.get("pbr")),
            "rank_in_group": _maybe_int(rec.get("rank_in_group")),
        })
        if debug:
            tprint(f"[dashboard][debug] ({i}/{total}) {mkt}/{tk} end ({time.perf_counter()-t0:.2f}s) — inflection={infl}")
    return out


def _maybe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def _maybe_int(v) -> int | None:
    f = _maybe_float(v)
    return int(f) if f is not None else None


def _load_rank_snapshot(cfg: config.Config) -> dict[str, int]:
    """data/{kospi,sp500}_daily_rank.csv 의 가장 최근 rank 를 ticker → rank 로 반환.

    legacy fetch_data.py 산출물 — Date index, 각 컬럼은 ticker, 값은 rank.
    파일 없으면 빈 dict.
    """
    out: dict[str, int] = {}
    for fname in ["kospi_daily_rank.csv", "sp500_daily_rank.csv"]:
        p = cfg.data_dir / fname
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, encoding="utf-8-sig")
        except Exception as e:
            log.warning(f"rank file 읽기 실패 {fname}: {e}")
            continue
        if df.empty or len(df.columns) < 2:
            continue
        last = df.iloc[-1]
        date_col = df.columns[0]
        for tk in df.columns[1:]:
            v = last[tk]
            if pd.notna(v):
                try:
                    out[str(tk)] = int(float(v))
                except (TypeError, ValueError):
                    pass
        log.info(f"{fname}: {date_col}={last[date_col]} → {sum(1 for c in df.columns[1:] if pd.notna(last[c]))} ranks")
    return out


def _build_period_table(cfg: config.Config) -> tuple[list[dict], list[str]]:
    """output/backtest/ 아래 모든 기간 디렉터리를 스캔해
    ticker × period → {type: return_pct} 테이블을 구성한다.

    반환:
        rows   : [{ticker, name, group_name, currency, rank_in_group,
                   period_returns: {period: {best_return, detail: {type: ret}}}}, ...]
        periods: 정렬된 기간 문자열 목록
    """
    period_list = paths.list_backtest_periods(cfg.output_dir)
    if not period_list:
        return [], []

    # instruments 이름/그룹 lookup
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    inst_map: dict[str, dict] = {}
    if not inst.empty:
        for _, r in inst.iterrows():
            inst_map[str(r["ticker"])] = {
                "name": str(r["name"]),
                "group_name": str(r["group_name"]),
                "currency": str(r["currency"]),
            }

    # 그룹 내 시총순위 (legacy data/{kospi,sp500}_daily_rank.csv 의 최신 row)
    rank_map = _load_rank_snapshot(cfg)

    # 기간별 _summary.csv 수집
    # ticker → {period → {type → return_pct}}
    ticker_data: dict[str, dict[str, dict[str, float]]] = {}

    n_periods = len(period_list)
    for p_idx, period in enumerate(period_list, start=1):
        bt_root = paths.backtest_root(cfg.output_dir, period)
        type_dirs = [d for d in sorted(bt_root.iterdir())
                     if bt_root.exists() and d.is_dir()] if bt_root.exists() else []
        tprint(f"[dashboard] period_table: period={period} ({p_idx}/{n_periods}) — {len(type_dirs)}개 type 로딩...", flush=True)
        for type_dir in type_dirs:
            summary_path = type_dir / "_summary.csv"
            if not summary_path.exists():
                continue
            sdf = csv_io.read(summary_path)
            if sdf.empty or "ticker" not in sdf.columns or "return_pct" not in sdf.columns:
                continue
            type_name = type_dir.name
            for _, row in sdf.iterrows():
                tk = str(row["ticker"])
                ret = pd.to_numeric(pd.Series([row["return_pct"]]), errors="coerce").iloc[0]
                if pd.isna(ret):
                    continue
                ticker_data.setdefault(tk, {}).setdefault(period, {})[type_name] = float(ret)
        tprint(f"[dashboard] period_table: period={period} 완료 — 누적 {len(ticker_data)}개 ticker", flush=True)

    # rows 구성
    rows: list[dict] = []
    for tk, period_map in sorted(ticker_data.items()):
        meta = inst_map.get(tk, {"name": tk, "group_name": "", "currency": ""})
        period_returns: dict[str, dict] = {}
        for period, type_map in period_map.items():
            best_ret = max(type_map.values()) if type_map else None
            period_returns[period] = {
                "best_return": round(best_ret, 4) if best_ret is not None else None,
                "detail": {t: round(r, 4) for t, r in type_map.items()},
            }
        rows.append({
            "ticker": tk,
            "name": meta["name"],
            "group_name": meta["group_name"],
            "currency": meta["currency"],
            "rank_in_group": rank_map.get(tk),  # ETF 는 None
            "period_returns": period_returns,
        })

    # best_return 기준으로 정렬 (첫 번째 period의 best_return)
    first_period = period_list[0] if period_list else None
    rows.sort(
        key=lambda r: r["period_returns"].get(first_period, {}).get("best_return") or -9999,
        reverse=True,
    )
    return rows, period_list


_DOC_LABELS: dict[str, str] = {
    "README":                 "README",
    "claude-opus-4-7_guide":  "아키텍처 가이드",
    "req":                    "요구사항",
    "claude-work":            "작업 이력",
    "msg":                    "메시지/노트",
    "gemini_analysis_report": "Gemini 분석",
    "register_etf_ticker":    "ETF 종목 등록",
}

# 원하는 표시 순서 (목록에 없으면 알파벳 순으로 자동 추가 — 새 *.md 파일은 자동 반영)
_DOC_ORDER: list[str] = [
    "README",
    "claude-opus-4-7_guide",
    "req",
    "claude-work",
    "msg",
    "gemini_analysis_report",
    "register_etf_ticker",
]


def _load_docs(cfg: config.Config) -> list[dict]:
    """claude/ 디렉터리의 *.md 파일을 모두 읽어 [{label, filename, content}, ...] 반환.

    - _DOC_ORDER 에 정의된 파일은 그 순서대로 표시.
    - 목록에 없는 새 *.md 파일은 알파벳 순으로 자동 추가됨 (별도 코드 수정 불필요).
    - _DOC_LABELS 에 없는 파일은 파일명(stem)이 그대로 레이블로 사용됨.
    """
    docs_dir = cfg.repo_root / "claude"
    if not docs_dir.exists():
        return []
    raw: dict[str, dict] = {}
    for p in docs_dir.glob("*.md"):
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            content = f"(읽기 실패: {p.name})"
        label = _DOC_LABELS.get(p.stem, p.stem)
        raw[p.stem] = {"label": label, "filename": p.name, "content": content}

    ordered: list[dict] = []
    for stem in _DOC_ORDER:
        if stem in raw:
            ordered.append(raw.pop(stem))
    # 나머지 알파벳 순
    for stem in sorted(raw):
        ordered.append(raw[stem])
    return ordered


def _load_etf_history(cfg: config.Config) -> list[dict]:
    """data/gmail_etf_history.json 읽어 이력 반환."""
    p = cfg.data_dir / "gmail_etf_history.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


_OPT_GROUPS = ["all", "KOSPI200", "SP500", "ETF_KR", "ETF_US"]
_OPT_LABELS = {
    "all":     "전체 (718종목)",
    "KOSPI200":"KOSPI200",
    "SP500":   "S&P500",
    "ETF_KR":  "ETF_KR",
    "ETF_US":  "ETF_US",
}


def _load_optimize_results(cfg: config.Config) -> dict[str, list[dict]]:
    """output/optimize/streak_grid_{group}.csv 읽어 {group: [rows]} 반환.

    파일이 없는 그룹은 빈 리스트. 기존 streak_grid.csv(단일파일)도 'all'로 fallback.
    """
    opt_dir = cfg.output_dir / "optimize"
    # 메타데이터 로드 (없으면 빈 dict)
    meta_path = opt_dir / "streak_grid_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            import json as _json
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    result: dict[str, list[dict]] = {"_meta": [meta] if meta else []}
    PER_TICKER_GROUPS = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]

    for g in _OPT_GROUPS:
        p = opt_dir / f"streak_grid_{g}.csv"
        if not p.exists() and g == "all":
            p = opt_dir / "streak_grid.csv"  # 기존 단일 파일 fallback
        if not p.exists():
            result[g] = []
            continue
        try:
            df = pd.read_csv(p)
        except Exception as e:
            log.warning(f"{p.name} 읽기 실패: {e}")
            result[g] = []
            continue
        for col in ["avg_return", "median_return", "hit_rate"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["plus_days", "minus_days", "n_positive", "n_total"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        result[g] = df.fillna("").to_dict(orient="records")

    # ── 전체 그룹 종목별 per-ticker 데이터 로드 ──────────────────────────────
    import json as _j
    for g in PER_TICKER_GROUPS:
        per_dir = opt_dir / "per_ticker" / g
        key_tickers = f"{g}_tickers"
        key_summary = f"{g}_summary"
        if not per_dir.exists():
            result[key_tickers] = {}
            result[key_summary] = {}
            continue
        # 요약 (ticker → 최적 파라미터)
        summary_path = per_dir / "_summary.json"
        result[key_summary] = {}
        if summary_path.exists():
            try:
                result[key_summary] = _j.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        # 종목별 전체 결과 rows
        tickers_data: dict[str, list[dict]] = {}
        for csv_p in sorted(per_dir.glob("*.csv")):
            if csv_p.name.startswith("_"):
                continue
            tk = csv_p.stem
            try:
                df = pd.read_csv(csv_p)
                for col in ["avg_return", "median_return", "hit_rate"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                for col in ["plus_days", "minus_days", "n_positive", "n_total"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                tickers_data[tk] = df.fillna("").to_dict(orient="records")
            except Exception as e:
                log.warning(f"per_ticker/{g}/{csv_p.name} 읽기 실패: {e}")
        result[key_tickers] = tickers_data
    return result


def _generate_trade_jsons(cfg: config.Config, out_dir: Path) -> int:
    """output/backtest/full/{type}/_all.csv 에서 종목별 거래 이력 JSON 생성.

    dashboard_site/data/trades/{ticker}.json 으로 저장.
    ticker_trades.html 에서 JS fetch로 사용.

    Returns:
        생성된 ticker 수
    """
    # 우선순위: full > 5y > 첫 번째 period
    period_list = paths.list_backtest_periods(cfg.output_dir)
    target_period = None
    for preferred in ["full", "5y"]:
        if preferred in period_list:
            target_period = preferred
            break
    if target_period is None and period_list:
        target_period = period_list[0]
    if target_period is None:
        return 0

    bt_root = paths.backtest_root(cfg.output_dir, target_period)
    if not bt_root or not bt_root.exists():
        return 0

    # instruments 메타 로드
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    inst_map: dict[str, dict] = {}
    if not inst.empty:
        for _, r in inst.iterrows():
            inst_map[str(r["ticker"])] = {
                "name": str(r.get("name", "")),
                "group_name": str(r.get("group_name", "")),
                "currency": str(r.get("currency", "")),
            }

    # (type, ticker) → trades 리스트 수집
    ticker_trades: dict[str, dict[str, list]] = {}
    for type_dir in sorted(bt_root.iterdir()):
        if not type_dir.is_dir():
            continue
        all_csv = type_dir / "_all.csv"
        if not all_csv.exists():
            continue
        adf = csv_io.read(all_csv)
        if adf.empty or "ticker" not in adf.columns:
            continue
        type_name = type_dir.name
        for ticker, grp in adf.groupby("ticker"):
            tk = str(ticker)
            cols = ["date", "side", "price", "qty", "amount",
                    "holding_qty", "holding_value", "cash", "return_pct"]
            cols = [c for c in cols if c in grp.columns]
            records = grp[cols].fillna("").to_dict(orient="records")
            # None/NaN 정리
            clean = []
            for rec in records:
                clean.append({k: (None if v == "" else v) for k, v in rec.items()})
            ticker_trades.setdefault(tk, {})[type_name] = clean

    trades_dir = out_dir / "data" / "trades"
    trades_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for tk, type_map in ticker_trades.items():
        meta = inst_map.get(tk, {"name": tk, "group_name": "", "currency": ""})
        payload = {
            "ticker": tk,
            "name": meta["name"],
            "group_name": meta["group_name"],
            "currency": meta["currency"],
            "period": target_period,
            "types": type_map,
        }
        (trades_dir / f"{tk}.json").write_text(
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        count += 1
    return count


def _json_default(o):
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    raise TypeError(f"not serializable: {type(o)}")


def _load_market_signals(cfg: config.Config, on_date: date) -> dict:
    """프로그램 비차익 + 금융투자 시장 시그널 로딩 (dashboard용).

    data/market/program_trading.csv, investor_trading.csv 에서 읽어
    최근 1개월(테이블) + 3개월(차트) 데이터를 반환.
    파일이 없으면 빈 구조 반환 (dashboard graceful degradation).
    """
    from ..fetch import market_signals as ms

    market_dir = cfg.data_dir / "market"
    prog_path = market_dir / "program_trading.csv"
    inv_path  = market_dir / "investor_trading.csv"

    # 파일이 없으면 빈 컨텍스트 반환 (make v2-market-signals 미실행 상태)
    prog_df = pd.read_csv(prog_path) if prog_path.exists() else pd.DataFrame()
    inv_df  = pd.read_csv(inv_path)  if inv_path.exists()  else pd.DataFrame()
    kospi_path = market_dir / "kospi_index.csv"
    kospi_df = pd.read_csv(kospi_path) if kospi_path.exists() else pd.DataFrame()

    signals = ms.check_signals(prog_df, inv_df, kospi_df=kospi_df, as_of=on_date)

    today_str = on_date.strftime("%Y-%m-%d")
    prog_thr = signals.get("program_threshold", 0)
    inv_thr  = signals.get("finv_threshold", 0)
    kospi_lookup: dict = signals.get("kospi_data", {})

    # ── 프로그램 비차익 ─────────────────────────────────────────────────
    prog_max_sell = signals.get("program_max_sell", 0)   # 역사적 최대 순매도 (가장 음수)
    prog_max_억 = round(prog_max_sell / 1e8, 0) if prog_max_sell else 0

    # 차트용 3개월(약 63거래일) — 최신이 오른쪽
    prog_chart_3m: list[dict] = []
    if not prog_df.empty and "비차익_순매수" in prog_df.columns:
        c3 = prog_df[prog_df["date"] <= today_str].tail(63)
        abs_max = abs(c3["비차익_순매수"].min()) if not c3.empty else 1
        for _, r in c3.iterrows():
            val = int(r["비차익_순매수"])
            height = round(abs(val) / abs_max * 100, 1) if abs_max else 0
            max_ratio = round(val / prog_max_sell * 100, 1) if prog_max_sell else 0
            prog_chart_3m.append({
                "date": r["date"],
                "val_억": round(val / 1e8, 0),
                "height_pct": height,
                "max_ratio": max_ratio,
                "alert": val <= prog_thr,
                "kospi_close": kospi_lookup.get(r["date"]),
                "kospi_y_pct": None,  # 이후 정규화
            })

    # KOSPI 선 정규화: 차트 창 내 10~90% 범위
    _kc = [d["kospi_close"] for d in prog_chart_3m if d["kospi_close"] is not None]
    if _kc:
        _kmin, _kmax = min(_kc), max(_kc)
        _kr = (_kmax - _kmin) or 1
        for _d in prog_chart_3m:
            if _d["kospi_close"] is not None:
                _d["kospi_y_pct"] = round((_d["kospi_close"] - _kmin) / _kr * 80 + 10, 1)

    # 테이블용 1개월(약 21거래일) — 최신이 맨 위
    prog_table: list[dict] = []
    if not prog_df.empty and "비차익_순매수" in prog_df.columns:
        t1 = prog_df[prog_df["date"] <= today_str].tail(21)
        for _, r in t1.iloc[::-1].iterrows():
            val = int(r["비차익_순매수"])
            max_ratio = round(val / prog_max_sell * 100, 1) if prog_max_sell else 0
            prog_table.append({
                "date": r["date"],
                "val_억": round(val / 1e8, 0),
                "max_억": prog_max_억,
                "max_ratio": max_ratio,
                "alert": val <= prog_thr,
                "kospi_close": kospi_lookup.get(r["date"]),
            })

    # ── 금융투자 ────────────────────────────────────────────────────────
    inv_max_sell = signals.get("finv_max_sell", 0)
    inv_max_억 = round(inv_max_sell / 1e8, 0) if inv_max_sell else 0

    inv_chart_3m: list[dict] = []
    if not inv_df.empty and "금융투자" in inv_df.columns:
        c3i = inv_df[inv_df["date"] <= today_str].tail(63)
        abs_max_i = abs(c3i["금융투자"].min()) if not c3i.empty else 1
        for _, r in c3i.iterrows():
            val_i = int(r["금융투자"])
            height_i = round(abs(val_i) / abs_max_i * 100, 1) if abs_max_i else 0
            max_ratio_i = round(val_i / inv_max_sell * 100, 1) if inv_max_sell else 0
            inv_chart_3m.append({
                "date": r["date"],
                "val_억": round(val_i / 1e8, 0),
                "height_pct": height_i,
                "max_ratio": max_ratio_i,
                "alert": val_i <= inv_thr,
                "kospi_close": kospi_lookup.get(r["date"]),
                "kospi_y_pct": None,
            })

    _kci = [d["kospi_close"] for d in inv_chart_3m if d["kospi_close"] is not None]
    if _kci:
        _kimin, _kimax = min(_kci), max(_kci)
        _kir = (_kimax - _kimin) or 1
        for _di in inv_chart_3m:
            if _di["kospi_close"] is not None:
                _di["kospi_y_pct"] = round((_di["kospi_close"] - _kimin) / _kir * 80 + 10, 1)

    inv_table: list[dict] = []
    if not inv_df.empty and "금융투자" in inv_df.columns:
        t1i = inv_df[inv_df["date"] <= today_str].tail(21)
        for _, r in t1i.iloc[::-1].iterrows():
            val_i = int(r["금융투자"])
            max_ratio_i = round(val_i / inv_max_sell * 100, 1) if inv_max_sell else 0
            inv_table.append({
                "date": r["date"],
                "val_억": round(val_i / 1e8, 0),
                "max_억": inv_max_억,
                "max_ratio": max_ratio_i,
                "alert": val_i <= inv_thr,
                "kospi_close": kospi_lookup.get(r["date"]),
            })

    prog_stats = signals.get("stats", {}).get("program", {})

    return {
        "available": not prog_df.empty,
        "program_signal": signals["program_signal"],
        "finv_signal": signals["finv_signal"],
        "any_signal": signals["program_signal"] or signals["finv_signal"],
        "signals": signals["signals"],
        "program_value_억": round(signals["program_value"] / 1e8, 0) if signals["program_value"] else 0,
        "program_threshold_억": round(prog_thr / 1e8, 0),
        "program_max_억": prog_max_억,
        "program_max_ratio": signals.get("program_max_ratio", 0),
        "program_pct_rank": signals.get("program_pct_rank", 50),
        "finv_value_억": round(signals["finv_value"] / 1e8, 0) if signals["finv_value"] else 0,
        "finv_threshold_억": round(inv_thr / 1e8, 0),
        "finv_max_억": inv_max_억,
        "finv_max_ratio": signals.get("finv_max_ratio", 0),
        "finv_consec": signals["finv_consec"],
        "lookback_days": prog_stats.get("lookback_days", 0),
        "prog_kospi_corr": signals.get("prog_kospi_corr"),
        "finv_kospi_corr": signals.get("finv_kospi_corr"),
        "prog_chart_3m": prog_chart_3m,
        "prog_table": prog_table,
        "inv_chart_3m": inv_chart_3m,
        "inv_table": inv_table,
    }


def _load_foreign_snapshot(cfg: config.Config, days: int = 5) -> dict[str, dict]:
    """KOSPI200 종목별 최근 N일 외국인/기관 순매수 합산 로드.

    data/market/foreign/{ticker}.csv 에서 읽어 {ticker: {외국인합계, 기관합계, 개인}} 반환.
    파일 없으면 빈 dict.
    """
    from ..fetch import foreign_trading as ft
    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        return {}
    tickers = inst[inst["group_name"] == "KOSPI200"]["ticker"].astype(str).tolist()
    return ft.load_latest_snapshot(cfg.data_dir, tickers, days=days)


def _load_market_signals_us(cfg: config.Config, on_date: date) -> dict:
    """VIX + 미국채 수익률 곡선 시그널 로딩 (dashboard용).

    data/market/us_vix.csv, data/market/us_yields.csv 에서 읽어
    최근 3개월(차트) + 1개월(테이블) 데이터를 반환.
    파일이 없으면 available=False 반환.
    """
    from ..fetch import market_signals_us as ms_us

    market_dir = cfg.data_dir / "market"
    vix_path    = market_dir / "us_vix.csv"
    yields_path = market_dir / "us_yields.csv"

    vix_df    = pd.read_csv(vix_path)    if vix_path.exists()    else pd.DataFrame()
    yields_df = pd.read_csv(yields_path) if yields_path.exists() else pd.DataFrame()

    if vix_df.empty and yields_df.empty:
        return {"available": False}

    signals = ms_us.check_us_signals(vix_df, yields_df, as_of=on_date)
    today_str = on_date.strftime("%Y-%m-%d")
    vix_thr = signals.get("vix_threshold", 30.0)

    # VIX 차트 (3개월, 63거래일)
    vix_chart: list[dict] = []
    if not vix_df.empty and "close" in vix_df.columns:
        hist = vix_df[vix_df["date"] <= today_str].tail(63)
        for _, r in hist.iterrows():
            v = float(pd.to_numeric(r["close"], errors="coerce") or 0)
            vix_chart.append({
                "date": r["date"],
                "vix": round(v, 2),
                "alert": v >= vix_thr,
            })

    # VIX 테이블 (1개월, 21거래일)
    vix_table: list[dict] = []
    if not vix_df.empty and "close" in vix_df.columns:
        hist = vix_df[vix_df["date"] <= today_str].tail(21)
        for _, r in hist.iloc[::-1].iterrows():
            v = float(pd.to_numeric(r["close"], errors="coerce") or 0)
            vix_table.append({
                "date": r["date"],
                "vix": round(v, 2),
                "alert": v >= vix_thr,
            })

    # 수익률 곡선 차트 (3개월)
    yield_chart: list[dict] = []
    yield_table: list[dict] = []
    if not yields_df.empty:
        hist_y = yields_df[yields_df["date"] <= today_str].tail(63)
        for _, r in hist_y.iterrows():
            sp = float(pd.to_numeric(r.get("spread"), errors="coerce") or 0) if "spread" in r.index else None
            yield_chart.append({
                "date": r["date"],
                "y10":    (round(float(pd.to_numeric(r.get("y10"),    errors="coerce")), 3) if "y10"    in r.index and pd.notna(r.get("y10"))    else None),
                "y3m":    (round(float(pd.to_numeric(r.get("y3m"),    errors="coerce")), 3) if "y3m"    in r.index and pd.notna(r.get("y3m"))    else None),
                "spread": (round(sp, 3) if sp is not None else None),
                "inverted": sp is not None and sp < 0,
            })
        for _, r in yields_df[yields_df["date"] <= today_str].tail(21).iloc[::-1].iterrows():
            sp = float(pd.to_numeric(r.get("spread"), errors="coerce") or 0) if "spread" in r.index else None
            yield_table.append({
                "date": r["date"],
                "y10":    (round(float(pd.to_numeric(r.get("y10"), errors="coerce")), 3) if "y10" in r.index and pd.notna(r.get("y10")) else None),
                "y3m":    (round(float(pd.to_numeric(r.get("y3m"), errors="coerce")), 3) if "y3m" in r.index and pd.notna(r.get("y3m")) else None),
                "spread": (round(sp, 3) if sp is not None else None),
                "inverted": sp is not None and sp < 0,
            })

    return {
        "available": True,
        "vix_signal": signals["vix_signal"],
        "inversion_signal": signals["inversion_signal"],
        "any_signal": signals.get("any_signal", False),
        "signals": signals["signals"],
        "vix_value": round(signals["vix_value"], 2),
        "vix_threshold": round(vix_thr, 2),
        "vix_pct_rank": signals.get("vix_pct_rank", 50.0),
        "spread": signals["spread"],
        "inversion_days": signals["inversion_days"],
        "vix_chart": vix_chart,
        "vix_table": vix_table,
        "yield_chart": yield_chart,
        "yield_table": yield_table,
    }

