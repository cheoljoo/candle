"""AI advisor — Claude Opus 4.7 + prompt caching.

매일 universe의 종목들에 대해 buy/sell/hold 의견을 받아 decisions 형태로 반환.
ANTHROPIC_API_KEY 환경변수가 없으면 전체 호출 skip.

Prompt caching 전략:
- 시스템 프롬프트(역할/스키마) → 가장 안정 → cache_control on system block
- ticker별 호출은 종목 메타·최근 60거래일 시세를 system 다음 user 블록 첫 부분에 넣고 cache_control 추가
- 오늘의 룰 시그널 + 질문은 마지막 user 블록 (캐시 X)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .. import config
from ..storage import csv_io, paths

log = logging.getLogger(__name__)

MODEL_ID = "claude-opus-4-7"

SYSTEM_PROMPT = """You are a disciplined swing-trading analyst.
Based ONLY on the provided indicators (last 60 trading days, fundamentals, rule signals),
output ONE JSON object matching this schema:

{
  "ticker": str,
  "action": "buy" | "sell" | "hold",
  "confidence": 0.0 to 1.0,
  "reasons_buy": [str, str, ...],
  "reasons_sell": [str, str, ...],
  "key_signals": {
    "ma10m_updown": "+" | "-" | null,
    "inflection": "-→+" | "+→-" | null,
    "rank_in_group": int | null
  },
  "risks": [str, ...]
}

Always include reasons_buy AND reasons_sell (case for and against).
Do not invent data. Output only the JSON, no preamble.
Do not use any sampling-related instructions; you have no temperature control on Opus 4.7.
"""


def _have_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def run_for_universe(cfg: config.Config, inst: pd.DataFrame, on_date: date) -> list[dict]:
    """instruments DataFrame을 받아 ticker별로 Claude에 질의 → decisions list 반환.

    실패/키 없음/데이터 부족 시 빈 list. 사용량 제한이 우려되므로 한 번에 ticker 수를 limit.
    """
    if inst.empty:
        return []
    if not _have_api_key():
        log.info("ANTHROPIC_API_KEY 없음 → AI advisor skip")
        return []

    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK 미설치 → AI advisor skip")
        return []

    client = anthropic.Anthropic()
    cache_dir = cfg.output_dir / "ai_cache" / on_date.isoformat()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 비용 통제: 한 day 호출 상한 (config.runtime.ai.daily_limit 가능, 미설정 시 default 50)
    daily_limit = int(cfg.runtime.get("ai", {}).get("daily_limit", 50))
    out: list[dict] = []
    called = 0

    for _, row in inst.iterrows():
        if called >= daily_limit:
            log.info(f"AI daily_limit={daily_limit} 도달, 나머지 skip")
            break
        ticker = str(row["ticker"])
        mkt = str(row["market"])
        daily = csv_io.read(paths.daily_csv(cfg.data_dir, mkt, ticker))
        if daily.empty:
            continue

        recent = _last_n_rows(daily, on_date, n=60)
        if recent.empty:
            continue

        try:
            payload = _ask_claude(client, row, recent, on_date)
        except Exception as e:
            log.warning(f"AI advisor {ticker} 실패: {e}")
            continue
        if not payload:
            continue

        # cache 저장
        raw_path = cache_dir / f"{ticker}.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        out.append({
            "decision_id": str(uuid.uuid4())[:8],
            "date": on_date.isoformat(),
            "ticker": ticker,
            "source": "ai",
            "action": payload.get("action", "hold"),
            "qty": None,
            "price": float(pd.to_numeric(recent["close"].iloc[-1], errors="coerce") or 0.0) or None,
            "reason": _summarize_reasons(payload),
            "raw_json_path": str(raw_path.relative_to(cfg.repo_root)),
        })
        called += 1

    log.info(f"AI advisor: {len(out)} decisions ({called} API calls)")
    return out


def _last_n_rows(daily: pd.DataFrame, on_date: date, n: int = 60) -> pd.DataFrame:
    df = daily.copy()
    df = df[df["date"] <= on_date.isoformat()].sort_values("date")
    return df.tail(n).reset_index(drop=True)


def _summarize_reasons(payload: dict) -> str:
    rb = payload.get("reasons_buy") or []
    rs = payload.get("reasons_sell") or []
    parts = []
    if rb:
        parts.append("매수: " + "; ".join(rb[:2]))
    if rs:
        parts.append("매도: " + "; ".join(rs[:2]))
    return " | ".join(parts) or "(no reason)"


def _ask_claude(client: Any, instrument_row: pd.Series, recent: pd.DataFrame,
                on_date: date) -> dict | None:
    """ticker 한 종목에 대해 Claude에 질의. JSON 객체 반환."""
    ticker = str(instrument_row["ticker"])
    name = str(instrument_row.get("name", ""))
    group = str(instrument_row.get("group_name", ""))
    currency = str(instrument_row.get("currency", ""))

    series_rows = recent[[
        "date", "open", "high", "low", "close", "volume",
        "ma10d", "ma50d", "ma10m", "ma10m_updown", "inflection",
        "rank_in_group", "per", "pbr",
    ]].fillna("").to_dict(orient="records")

    cur = recent.iloc[-1]
    rule_today = {
        "ma10m_updown": (None if pd.isna(cur.get("ma10m_updown")) else str(cur.get("ma10m_updown"))),
        "inflection": (None if pd.isna(cur.get("inflection")) else str(cur.get("inflection"))),
        "rank_in_group": (None if pd.isna(cur.get("rank_in_group")) else int(cur.get("rank_in_group"))),
        "close": float(pd.to_numeric(cur.get("close"), errors="coerce") or 0.0),
    }

    # System: cached. User: meta + 60d 시세 → cached. + 오늘의 질문 (uncached).
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=2000,
        system=[
            {"type": "text",
             "text": SYSTEM_PROMPT,
             "cache_control": {"type": "ephemeral"}},
        ],
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                        "confidence": {"type": "number"},
                        "reasons_buy": {"type": "array", "items": {"type": "string"}},
                        "reasons_sell": {"type": "array", "items": {"type": "string"}},
                        "key_signals": {
                            "type": "object",
                            "properties": {
                                "ma10m_updown": {"type": ["string", "null"]},
                                "inflection": {"type": ["string", "null"]},
                                "rank_in_group": {"type": ["integer", "null"]},
                            },
                            "required": ["ma10m_updown", "inflection", "rank_in_group"],
                            "additionalProperties": False,
                        },
                        "risks": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["ticker", "action", "confidence",
                                 "reasons_buy", "reasons_sell", "key_signals", "risks"],
                    "additionalProperties": False,
                },
            },
        },
        messages=[{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": (
                    f"Ticker: {ticker} ({name})\n"
                    f"Group: {group}, Currency: {currency}\n"
                    f"Last 60 trading days (date, open, high, low, close, volume, ma10d, ma50d, ma10m, "
                    f"ma10m_updown, inflection, rank_in_group, per, pbr):\n"
                    f"{json.dumps(series_rows, ensure_ascii=False)}"
                 ),
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text",
                 "text": (
                    f"Today is {on_date.isoformat()}. Today's snapshot: {json.dumps(rule_today)}.\n"
                    "Decide: buy / sell / hold for tomorrow's open. Output JSON only."
                 )},
            ],
        }],
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log.warning(f"AI {ticker}: JSON decode 실패")
        return None
    payload["_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
    }
    return payload
