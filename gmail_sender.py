"""gmail_sender.py — Candle 투자 리포트 메일 발송.

수신자 목록 : config/recipients.yml
발송 방식   : 각 수신자에게 개별 To: (1인 1메일) — 추후 개인별 맞춤 내용 대비
--only-me   : owner(cheoljoo@gmail.com)에게만 발송
본문 자동생성: --decisions-json 지정 시 의사결정 요약 + 대시보드 링크 자동 구성
기존 호환   : --body-file 로 직접 본문 파일 지정 가능
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
from collections import defaultdict
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml


# ── 설정 로드 ────────────────────────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).parent / "config"

def _load_recipients() -> dict:
    p = _CONFIG_DIR / "recipients.yml"
    if not p.exists():
        return {"owner": "cheoljoo@gmail.com", "recipients": [], "dashboard_url": ""}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── 의사결정 본문 자동 생성 ───────────────────────────────────────────────────
_TYPE_DESC = {
    "type1_1":  "MA10M 교차(-→+) 매수 / (+→-) 매도, 10주 고정",
    "type1_2":  "MA10M 교차(-→+) 전액 매수 / (+→-) 전량 매도",
    "type2_1":  "+8일 연속 → 매수 / -4일 연속 → 매도, 10주 고정",
    "type2_2":  "+8일 연속 → 전액 매수 / -4일 연속 → 전량 매도",
    "type2_1b": "+33일 연속 → 매수 / -5일 연속 → 매도, 10주 고정",
    "type2_2b": "+33일 연속 → 전액 매수 / -5일 연속 → 전량 매도",
    "type3":    "90일 주기 적립식 매수",
}


def _build_body_from_decisions(decisions_json_path: str, dashboard_url: str) -> str:
    """decisions.json 을 읽어 메일 본문 문자열 생성."""
    try:
        with open(decisions_json_path, encoding="utf-8") as f:
            decisions: list[dict] = json.load(f)
    except Exception as e:
        return f"(의사결정 데이터 로드 실패: {e})"

    today_str = date.today().strftime("%Y-%m-%d")

    # type3(적립식) 제외 후 action 별 분류
    filtered = [d for d in decisions if not d.get("source", "").startswith("rule:type3")]

    buys  = [d for d in filtered if d.get("action") == "buy"]
    sells = [d for d in filtered if d.get("action") == "sell"]

    # ticker별로 전략 묶기
    def _group_by_ticker(rows: list[dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for d in rows:
            tk = d["ticker"]
            if tk not in out:
                out[tk] = {
                    "name": d.get("name", ""),
                    "group": d.get("group_name", ""),
                    "rank": d.get("rank_in_group"),
                    "price": d.get("price"),
                    "types": [],
                }
            src = d.get("source", "")
            if src.startswith("rule:"):
                out[tk]["types"].append(src[5:])
        return out

    buy_map  = _group_by_ticker(buys)
    sell_map = _group_by_ticker(sells)

    def _fmt_ticker_line(tk: str, info: dict) -> str:
        rank_str = f", 순위 {info['rank']}위" if info["rank"] else ""
        price_str = f"  @ {info['price']:,.0f}" if info["price"] else ""
        types_str = " · ".join(sorted(set(info["types"])))
        return (f"  • {info['name']} ({tk}) [{info['group']}{rank_str}]{price_str}"
                f"\n      전략: {types_str}")

    lines: list[str] = []
    lines.append(f"안녕하세요,")
    lines.append(f"")
    lines.append(f"{today_str} Candle 투자 리포트입니다.")
    lines.append(f"")
    lines.append(f"📊 대시보드: {dashboard_url}")
    lines.append(f"")
    lines.append("─" * 50)

    if buy_map:
        lines.append(f"📈 BUY 신호 — {len(buy_map)}종목")
        for tk, info in sorted(buy_map.items(), key=lambda x: (x[1]["group"], x[0])):
            lines.append(_fmt_ticker_line(tk, info))
    else:
        lines.append("📈 BUY 신호 — 없음")

    lines.append("")

    if sell_map:
        lines.append(f"📉 SELL 신호 — {len(sell_map)}종목")
        for tk, info in sorted(sell_map.items(), key=lambda x: (x[1]["group"], x[0])):
            lines.append(_fmt_ticker_line(tk, info))
    else:
        lines.append("📉 SELL 신호 — 없음")

    lines.append("─" * 50)
    lines.append("")
    lines.append("전략 설명:")
    for code, desc in _TYPE_DESC.items():
        lines.append(f"  {code:<10}: {desc}")
    lines.append("")
    lines.append("─" * 50)
    lines.append(f"* type3(적립식) 신호는 요약에서 제외됩니다.")
    lines.append(f"* 상세 내용은 대시보드에서 확인하세요.")

    return "\n".join(lines)


# ── 메일 발송 ─────────────────────────────────────────────────────────────────
def _send_one(
    sender_email: str,
    sender_password: str,
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str | None,
) -> bool:
    """수신자 1인에게 메일 발송. 성공 True, 실패 False."""
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(attachment_path)
            part.add_header("Content-Disposition", "attachment",
                            filename=("utf-8", "", filename))
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"  [ERROR] {to_email} 발송 실패: {e}")
        return False


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Candle 투자 리포트 메일 발송 (config/recipients.yml 기반 개별 To: 발송)"
    )
    parser.add_argument("--sendmail", default='YES',
                        help="메일 발송 활성화 값 (빈값/미지정이면 즉시 종료). 예: YES     default:보냄")
    parser.add_argument("--subject",  default="[candle] 투자 리포트", help="메일 제목")
    parser.add_argument("--body-file", default=None, help="본문 파일 경로 (--decisions-json 없을 때 사용)")
    parser.add_argument("--attach-file", default=None, help="첨부 파일 경로 (선택)")
    parser.add_argument("--decisions-json", default=None,
                        help="decisions.json 경로 — 의사결정 요약 본문 자동 생성")
    parser.add_argument("--dashboard-url", default=None,
                        help="대시보드 URL 덮어쓰기 (기본: config/recipients.yml 값)")
    parser.add_argument("--only-me", action="store_true",
                        help="owner 에게만 발송 (수신자 목록 무시)")
    args = parser.parse_args()

    # --sendmail 이 빈값이거나 미지정이면 발송하지 않고 즉시 종료
    if not args.sendmail or not args.sendmail.strip():
        print("[mail] SENDMAIL 값 없음 — 메일 발송 건너뜀")
        return

    cfg = _load_recipients()
    owner       = cfg.get("owner", "cheoljoo@gmail.com")
    recipients  = cfg.get("recipients", [])
    dashboard_url = args.dashboard_url or cfg.get("dashboard_url", "")

    sender_email    = "cheoljoo@gmail.com"
    sender_password = "dytf xplz hjea dhwj"  # Gmail app-specific password

    # ── 본문 결정 ──────────────────────────────────────────────────────────
    if args.decisions_json:
        body = _build_body_from_decisions(args.decisions_json, dashboard_url)
    elif args.body_file and os.path.exists(args.body_file):
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read().strip()
    else:
        body = f"(본문 없음)\n\n대시보드: {dashboard_url}"

    # ── 수신자 목록 결정 ───────────────────────────────────────────────────
    if args.only_me:
        to_list = [owner]
        print(f"[mail] --only-me: {owner} 에게만 발송")
    else:
        to_list = [owner] + [r["email"] for r in recipients if r.get("email")]
        print(f"[mail] 수신자 {len(to_list)}명: {owner} + {len(recipients)}명")

    # ── 개별 발송 ──────────────────────────────────────────────────────────
    ok = fail = 0
    for to_email in to_list:
        print(f"[mail]   → {to_email} ...", end=" ", flush=True)
        if _send_one(sender_email, sender_password, to_email,
                     args.subject, body, args.attach_file):
            print("OK")
            ok += 1
        else:
            fail += 1

    print(f"[mail] 완료 — 성공 {ok} / 실패 {fail}")


if __name__ == "__main__":
    main()
