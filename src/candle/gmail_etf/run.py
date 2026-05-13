"""ETF ticker 메일 등록 처리 — 메인 오케스트레이션.

흐름:
  1. Gmail 에서 조건에 맞는 미처리 메일 조회
  2. 본문 TICKER 라인 파싱
  3. ticker별 시장 판별 → 종목 정보 조회
  4. 이미 등록/신규/실패 분류
  5. 신규 ticker → etf_user.json + instruments.csv 즉시 반영
  6. 처리 결과를 메일 답장으로 발송
  7. 처리한 메시지 ID 저장

상태 파일: data/gmail_etf_state.json
  {
    "processed_ids": ["msg_id_1", ...]
  }

사용자 ETF 목록: data/universe/etf_user.json
  [{"ticker": "...", "name": "...", "market": "...", "group_name": "...", "currency": "..."}]
"""
from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import pandas as pd

from .. import config
from ..io_report import announce
from ..storage import csv_io, paths

log = logging.getLogger(__name__)

_STATE_FILENAME = "gmail_etf_state.json"
_USER_ETF_FILENAME = "etf_user.json"
_HISTORY_FILENAME = "gmail_etf_history.json"

# SMTP 발송 설정 (gmail_sender.py 와 동일)
_SMTP_SENDER = "cheoljoo@gmail.com"
_SMTP_PASSWORD = "dytf xplz hjea dhwj"


def _send_reply_smtp(to_email: str, orig_subject: str, body: str, owner: str = "") -> bool:
    """SMTP 로 답장 발송. owner 는 항상 To 에 포함 (발신자와 다를 경우 둘 다 수신)."""
    subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
    # To: 발신자 + owner (둘 다 포함, 중복 제거)
    to_list = [to_email]
    if owner and owner.lower() != to_email.lower():
        to_list.append(owner)
    to_header = ", ".join(to_list)
    try:
        msg = MIMEMultipart()
        msg["From"] = _SMTP_SENDER
        msg["To"] = to_header
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(_SMTP_SENDER, _SMTP_PASSWORD)
            server.sendmail(_SMTP_SENDER, to_list, msg.as_string())
        log.info("[gmail_etf] 답장 발송 완료 → %s", to_header)
        return True
    except Exception as e:
        log.error("[gmail_etf] 답장 발송 실패: %s", e)
        return False


# ── 상태 파일 ──────────────────────────────────────────────────────────────────

def _state_path(data_dir: Path) -> Path:
    return data_dir / _STATE_FILENAME


def _load_state(data_dir: Path) -> dict[str, Any]:
    p = _state_path(data_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed_ids": []}


def _save_state(data_dir: Path, state: dict[str, Any]) -> None:
    p = _state_path(data_dir)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 이력 파일 ──────────────────────────────────────────────────────────────────

def _history_path(data_dir: Path) -> Path:
    return data_dir / _HISTORY_FILENAME


def _load_history(data_dir: Path) -> list[dict]:
    p = _history_path(data_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _append_history(data_dir: Path, entries: list[dict]) -> None:
    """entries 를 이력 파일에 추가 저장."""
    if not entries:
        return
    history = _load_history(data_dir)
    history.extend(entries)
    p = _history_path(data_dir)
    p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 사용자 ETF 목록 ─────────────────────────────────────────────────────────────

def _user_etf_path(data_dir: Path) -> Path:
    return data_dir / "universe" / _USER_ETF_FILENAME


def _load_user_etf(data_dir: Path) -> list[dict]:
    p = _user_etf_path(data_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_user_etf(data_dir: Path, entries: list[dict]) -> None:
    p = _user_etf_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


# ── instruments.csv 즉시 반영 ──────────────────────────────────────────────────

def _add_to_csv_files(data_dir: Path, info: dict) -> None:
    """신규 ticker 를 etf_KR/US csv + instruments.csv 에 즉시 추가."""
    market = info["market"]
    group_name = info["group_name"]

    # 1) data/universe/etf_kr.csv 또는 etf_us.csv
    etf_csv = paths.etf_list_csv(data_dir, market)
    existing_etf = csv_io.read(etf_csv)
    new_row = pd.DataFrame([{"ticker": info["ticker"], "name": info["name"]}])
    if existing_etf.empty:
        csv_io.atomic_write(new_row, etf_csv)
    else:
        if info["ticker"] not in existing_etf["ticker"].astype(str).values:
            merged = pd.concat([existing_etf, new_row], ignore_index=True)
            csv_io.atomic_write(merged, etf_csv)

    # 2) data/instruments.csv
    inst_csv = paths.instruments_csv(data_dir)
    existing_inst = csv_io.read(inst_csv)
    new_inst_row = pd.DataFrame([{
        "ticker": info["ticker"],
        "name": info["name"],
        "market": market,
        "group_name": group_name,
        "currency": info["currency"],
        "active": 1,
    }])
    if existing_inst.empty:
        csv_io.atomic_write(new_inst_row, inst_csv)
    else:
        if info["ticker"] not in existing_inst["ticker"].astype(str).values:
            merged = pd.concat([existing_inst, new_inst_row], ignore_index=True)
            csv_io.atomic_write(merged, inst_csv)


# ── 메인 실행 ──────────────────────────────────────────────────────────────────

def run(
    cfg: config.Config,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Gmail 을 읽어 ETF ticker 등록 처리.

    Returns: {"processed": int, "added": int, "skipped": int, "failed": int}
    """
    from .reader import get_service, list_new_messages
    from .resolver import detect_market, resolve_ticker

    credentials_path = credentials_path or (cfg.repo_root / "credentials.json")
    # 기존 token.json (gmail.readonly) 재사용 — 별도 OAuth 인증 불필요
    token_path = token_path or (cfg.repo_root / "token.json")

    announce(
        "gmail-etf",
        inputs=[
            (str(credentials_path), "Google OAuth 클라이언트 파일"),
            (str(token_path), "Gmail OAuth 토큰 (gmail.readonly — 기존 token.json 재사용 가능)"),
            ("config/recipients.yml", "owner / 수신자 목록"),
            ("data/gmail_etf_state.json", "처리된 메시지 ID 상태 파일"),
            ("data/universe/etf_user.json", "사용자 요청 ETF 목록"),
        ],
        outputs=[
            ("data/gmail_etf_state.json", "처리 완료 후 갱신"),
            ("data/universe/etf_user.json", "신규 ETF 추가"),
            ("data/universe/etf_kr.csv 또는 etf_us.csv", "ETF 목록 즉시 반영"),
            ("data/instruments.csv", "신규 ticker 즉시 추가"),
        ],
    )

    # recipients.yml 로드
    recipients_cfg = cfg.recipients  # {"owner": ..., "recipients": [...]}
    owner = recipients_cfg.get("owner", "")
    sender_emails: set[str] = {
        r["email"].lower()
        for r in recipients_cfg.get("recipients", [])
        if r.get("email")
    }
    if not owner:
        log.error("[gmail_etf] config/recipients.yml 에 owner 가 없습니다.")
        return {"processed": 0, "added": 0, "skipped": 0, "failed": 0}

    # 상태 + 사용자 ETF 목록 로드
    state = _load_state(cfg.data_dir)
    processed_ids: set[str] = set(state.get("processed_ids", []))
    user_etf = _load_user_etf(cfg.data_dir)
    existing_tickers: set[str] = {e["ticker"].upper() for e in user_etf}

    # instruments.csv 에 이미 있는 ticker 도 확인
    inst_df = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if not inst_df.empty:
        existing_tickers |= set(inst_df["ticker"].astype(str).str.upper().values)

    # Gmail 서비스 연결
    try:
        service = get_service(credentials_path, token_path)
    except Exception as e:
        log.error("[gmail_etf] Gmail 서비스 연결 실패: %s", e)
        return {"processed": 0, "added": 0, "skipped": 0, "failed": 0}

    # 미처리 메일 조회
    messages = list_new_messages(service, owner, sender_emails, processed_ids)
    log.info("[gmail_etf] 미처리 매칭 메일 %d건", len(messages))

    counters = {"processed": 0, "added": 0, "skipped": 0, "failed": 0}
    history_new: list[dict] = []

    for msg in messages:
        tickers_in_mail: list[str] = msg["tickers"]
        added_list: list[str] = []
        already_list: list[str] = []
        failed_list: list[tuple[str, str]] = []  # (ticker, reason)

        for raw_ticker in tickers_in_mail:
            ticker = raw_ticker.upper().strip()

            # 이미 등록된 경우
            if ticker in existing_tickers:
                already_list.append(ticker)
                counters["skipped"] += 1
                continue

            # 시장 판별
            market = detect_market(ticker)
            if market is None:
                reason = f"형식 불명 (KR: 6자리 숫자, US: 영문 1~5자)"
                failed_list.append((ticker, reason))
                counters["failed"] += 1
                log.info("[gmail_etf] 시장 판별 실패: %s", ticker)
                continue

            # 종목 정보 조회
            info = resolve_ticker(ticker, market)
            if info is None:
                reason = f"종목 정보를 찾을 수 없음 ({'pykrx/FDR' if market == 'KR' else 'yfinance'} 조회 실패)"
                failed_list.append((ticker, reason))
                counters["failed"] += 1
                log.info("[gmail_etf] 종목 조회 실패: %s (%s)", ticker, market)
                continue

            # 등록
            if not dry_run:
                user_etf.append(dict(info))
                _add_to_csv_files(cfg.data_dir, dict(info))
                existing_tickers.add(ticker)

            added_list.append(f"{ticker} ({info['name']}) → {info['group_name']}")
            counters["added"] += 1
            log.info("[gmail_etf] 추가 완료: %s (%s) → %s", ticker, info["name"], info["group_name"])
            # 이력 항목
            history_new.append({
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "by": msg["from_email"],
                "ticker": ticker,
                "name": info["name"],
                "market": info["market"],
                "group_name": info["group_name"],
            })

        # 답장 작성
        reply_lines: list[str] = [
            "안녕하세요,",
            "",
            f"ETF 종목 추가 요청({datetime.now().strftime('%Y-%m-%d %H:%M')}) 처리 결과입니다.",
            "",
        ]

        if added_list:
            reply_lines.append(f"✅ 추가 완료 ({len(added_list)}건)")
            for item in added_list:
                reply_lines.append(f"  - {item}")
            reply_lines.append("")

        if already_list:
            reply_lines.append(f"ℹ️ 이미 등록된 종목 ({len(already_list)}건)")
            for tk in already_list:
                reply_lines.append(f"  - {tk} : 이미 등록되어 있습니다.")
            reply_lines.append("")

        if failed_list:
            reply_lines.append(f"❌ 등록 실패 ({len(failed_list)}건)")
            for tk, reason in failed_list:
                reply_lines.append(f"  - {tk} : {reason}")
            reply_lines.append("")

        if dry_run:
            reply_lines.append("※ dry-run 모드: 실제 등록은 수행되지 않았습니다.")
            reply_lines.append("")

        reply_lines += [
            "감사합니다.",
            "Candle 자동화 시스템",
        ]

        reply_body = "\n".join(reply_lines)

        if not dry_run:
            _send_reply_smtp(msg["from_email"], msg["subject"], reply_body, owner=owner)

        # 처리 완료 기록
        processed_ids.add(msg["id"])
        counters["processed"] += 1

    # 상태 + 사용자 ETF + 이력 저장
    if not dry_run:
        state["processed_ids"] = list(processed_ids)
        _save_state(cfg.data_dir, state)
        if user_etf:
            _save_user_etf(cfg.data_dir, user_etf)
        if history_new:
            _append_history(cfg.data_dir, history_new)

    return counters
