"""Gmail 읽기 헬퍼.

사용 권한: gmail.readonly (읽기 전용)
토큰 파일: token.json (기존 token.json 재사용)
답장 발송: SMTP (gmail_sender.py 방식) — Gmail API 불필요
"""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

# 읽기 전용 — 기존 token.json 재사용 가능
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# 메일 제목 패턴: "[candle][v2] YYYY-MM-DD 투자 리포트" (Re:, FW: 등 접두사 허용)
_SUBJECT_RE = re.compile(
    r"\[candle\]\[v2\]\s+\d{4}-\d{2}-\d{2}\s+투자\s*리포트",
    re.IGNORECASE,
)

# 본문에서 TICKER 라인 추출: "TICKER : XXX, YYY" 또는 "TICKER: XXX"
_TICKER_LINE_RE = re.compile(
    r"^TICKER\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def get_service(credentials_path: Path, token_path: Path):
    """Gmail API 서비스 객체 반환. 필요 시 OAuth 갱신."""
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth 클라이언트 파일이 없습니다: {credentials_path}\n"
                    "Google Cloud Console 에서 credentials.json 을 내려받아 현재 "
                    "디렉터리에 넣어주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            # 서버리스 환경 대응: manual 코드 입력 방식
            flow.redirect_uri = "http://localhost"
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            print("\n[gmail_etf] Gmail OAuth 인증이 필요합니다.")
            print("아래 URL을 브라우저에서 열어 승인 후, 리다이렉트 URL(또는 code)을 붙여넣으세요.")
            print(auth_url)
            response = input("리다이렉트 URL 또는 code: ").strip()
            if response.startswith("http://") or response.startswith("https://"):
                from urllib.parse import parse_qs, urlparse
                parsed = urlparse(response)
                code_list = parse_qs(parsed.query).get("code", [])
                if not code_list:
                    raise RuntimeError("URL 에서 code 를 찾지 못했습니다.")
                flow.fetch_token(code=code_list[0])
            else:
                flow.fetch_token(code=response)
            creds = flow.credentials

        token_path.write_text(creds.to_json(), encoding="utf-8")
        log.info("[gmail_etf] 토큰 저장: %s", token_path)

    return build("gmail", "v1", credentials=creds)


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(payload: dict) -> str:
    """메시지 payload 에서 plain text 본문 추출."""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})

    if "parts" in payload:
        for part in payload["parts"]:
            text = _decode_body(part)
            if text:
                return text
        return ""

    if "text/plain" in mime_type:
        data = body.get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    return ""


def list_new_messages(
    service,
    owner: str,
    sender_emails: set[str],
    processed_ids: set[str],
) -> list[dict[str, Any]]:
    """처리하지 않은 매칭 메일 목록 반환.

    Returns: [{"id": ..., "thread_id": ..., "subject": ..., "from": ...,
               "to": ..., "body": ..., "tickers": [...]}]
    """
    # Gmail query: 수신함(me), 발신자 제한은 클라이언트에서 필터
    # [candle][v2] 제목 포함 메일 최대 50개 조회
    query = 'subject:"[candle][v2]" subject:"투자 리포트"'
    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=50
        ).execute()
    except Exception as e:
        log.error("[gmail_etf] Gmail 조회 실패: %s", e)
        return []

    messages = result.get("messages", [])
    matched: list[dict[str, Any]] = []

    for msg_stub in messages:
        msg_id = msg_stub["id"]
        if msg_id in processed_ids:
            continue  # 이미 처리됨

        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception as e:
            log.warning("[gmail_etf] 메시지 상세 조회 실패 %s: %s", msg_id, e)
            continue

        headers = msg.get("payload", {}).get("headers", [])
        subject = _get_header(headers, "Subject")
        from_addr = _get_header(headers, "From")
        to_addr = _get_header(headers, "To")

        # 제목 패턴 확인
        if not _SUBJECT_RE.search(subject):
            continue

        # From: recipients 중 하나인지 확인 (이메일 주소만 추출)
        from_email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", from_addr)
        if not from_email or from_email.group().lower() not in sender_emails:
            continue

        # To: owner 포함 확인
        if owner.lower() not in to_addr.lower():
            continue

        # 본문에서 TICKER 라인 추출
        body = _decode_body(msg.get("payload", {}))
        ticker_match = _TICKER_LINE_RE.search(body)
        if not ticker_match:
            log.info("[gmail_etf] TICKER 라인 없음 — 메시지 %s 건너뜀", msg_id)
            continue

        raw_tickers = [t.strip().upper() for t in ticker_match.group(1).split(",") if t.strip()]
        if not raw_tickers:
            continue

        matched.append({
            "id": msg_id,
            "thread_id": msg["threadId"],
            "subject": subject,
            "from": from_addr,
            "from_email": from_email.group(),
            "to": to_addr,
            "body": body,
            "tickers": raw_tickers,
        })

    return matched
