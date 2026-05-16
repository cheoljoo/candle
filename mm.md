feat: Makefile KR/US 분리 파이프라인 + candle.sh 인자 분기

- `Makefile`: `v2-all-kr` 신규 — 한국장 종료 후 실행 (gmail-etf→fetch-kr→analyze-kr→backtest-kr→simulate→market-signals→dashboard→sendmail)
- `Makefile`: `v2-all-us` 신규 — 미국장 종료 후 실행 (fetch-us→analyze-us→backtest-us→simulate→dashboard→sendmail)
- `Makefile`: `v2-fetch-kr/us`, `v2-analyze-kr/us`, `v2-backtest-kr/us` 단계별 타겟 추가 (`--market kr|us`)
- `Makefile`: `v2-backtest-compare-full/5y-kr/us` — KR/US 전용 backtest+compare 묶음 (full/5y 병렬 실행)
- `Makefile`: `help` 섹션에 "시장별 분리 파이프라인" 항목 추가
- `candle.sh`: 인자(`kr|us`) 기반 파이프라인 분기 — `./candle.sh kr` → v2-all-kr, `./candle.sh us` → v2-all-us, 인자 없음 → v2-all(기존 동작 유지)
- `candle.sh`: 로그 파일/날짜 백업 파일명도 시장별(`candle-v2-kr.log` / `candle-v2-us.log`) 분리
- 문서: `claude-work.md` 2026-05-16 3차 항목 추가, `claude-opus-4-7_guide.md` §4 Makefile 섹션 현행화 (10차)

