"""Simulate CLI 진입."""
from __future__ import annotations

import logging
from datetime import date

from .. import config
from ..io_report import announce
from . import engine, manual

log = logging.getLogger(__name__)


def run(cfg: config.Config, on_date: date, use_ai: bool = True, debug: bool = False,
        rule_types: list[str] | None = None) -> dict[str, int]:
    announce(
        f"simulate --today {on_date.isoformat()} {'--ai' if use_ai else '--no-ai'}",
        inputs=[
            ("config/strategies.yml",
             "rule(=backtest types)의 신호 파라미터 (plus_days/minus_days, qty, interval_days)"),
            ("data/instruments.csv",
             "의사결정 대상 ticker"),
            ("data/daily/{KR|US}/{ticker}.csv",
             "기준일 시점의 시세 + 지표 (inflection·ma10m_updown으로 rule 신호 평가)"),
            ("output/simulate/manual_input.csv",
             "사용자 수동 입력 — date,ticker,action(buy/sell/hold),qty,reason (사용자가 편집)"),
            ("ANTHROPIC_API_KEY (env, AI 사용 시)",
             "Claude Opus 4.7 호출에 필요. 없으면 ai source skip"),
        ],
        outputs=[
            ("output/simulate/decisions.csv",
             "오늘의 의사결정 ledger — decision_id,date,ticker,source(rule:type/ai/manual),action,qty,price,reason,raw_json_path"),
            ("output/simulate/trades.csv",
             "D+1 시작가에 체결된 거래 — trade_id,decision_id,date,ticker,side,price,qty,amount"),
            (f"output/ai_cache/{on_date.isoformat()}/{{ticker}}.json (AI 사용 시)",
             "Claude 응답 raw — action/confidence/reasons_buy/reasons_sell/key_signals/risks + _usage"),
        ],
    )
    manual.ensure_template(cfg)
    _rule_types = rule_types if rule_types is not None else cfg.enabled_types
    return engine.run(cfg, on_date, rule_types=_rule_types, use_ai=use_ai, debug=debug)
