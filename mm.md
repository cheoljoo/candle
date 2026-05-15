feat: gmail_sender — 수신자 중복 제거 + HTML 이메일 발송 지원

- 수신자 중복 제거: owner + recipients 합산 후 순서 유지 중복 제거, 제거 수 로그 출력
- `_build_html_body_from_decisions()` 신규: 이메일 클라이언트 호환 인라인 스타일 HTML 생성
  - 파란 헤더 + 대시보드 바로가기 버튼
  - BUY(초록) / SELL(빨강) 신호 테이블 (종목명·코드·그룹·순위·현재가·전략)
  - 전략 설명 테이블 + 푸터
- `_send_one()`: `html_body` 파라미터 추가 → multipart/alternative (plain + html) 발송
- `main()`: --decisions-json 지정 시 plain/html 양쪽 자동 생성 후 발송
- 문서: claude-work.md, claude-opus-4-7_guide.md 현행화

