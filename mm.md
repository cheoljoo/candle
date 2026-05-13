feat: gmail-etf 기능 추가, dashboard 이력 페이지, KR 알파뉴메릭 ticker 지원, FutureWarning 수정



## gmail-etf — Gmail 기반 ETF 자동 등록 (`src/candle/gmail_etf/`)
- `reader.py`: Gmail API (gmail.readonly) 제목 패턴 매칭 + 본문 TICKER 파싱
- `resolver.py`: `detect_market()` — KR 패턴 `^\d{6}$` → `^[0-9A-Z]{6}$` (영숫자 혼합 6자리 KR 지원)
  - `0190Y0` (TIGER 구글밸류체인 ETF, 2026-05-12 신규 상장) 처리 가능
  - `_resolve_kr()`: pykrx → FDR KRX → FDR ETF/KR → yfinance .KS 순 fallback
  - pykrx `get_market_ticker_name()` DataFrame 반환 시 안전 처리 추가
- `run.py`: 오케스트레이션 — 등록/중복/실패 분류, etf_user.json + instruments.csv 즉시 반영
  - SMTP 답장: 발신자 + owner 둘 다 `To` 에 포함 (`send_message` → `sendmail` 변경)
  - 등록 이력: `data/gmail_etf_history.json` 누적 저장 (`_append_history()`)
- `Makefile`: `v2-gmail-etf`, `v2-gmail-etf-dry` 타겟 추가
- `cli.py`: `gmail-etf` subcommand 추가

## dashboard — ETF 등록 이력 페이지 신규 추가
- `templates/_nav.html`: "문서" 다음 "이력" 링크 추가
- `templates/history.html` 신규: 요약 카드(총 건수/KR/US/등록자 수) + 시장·등록자 필터 + 최신순 테이블
- `render.py`: `_load_etf_history()` 추가, `history.html` 렌더 (총 10개 파일)
- `data/gmail_etf_history.json`: 0190Y0 초기 항목 추가 (2026-05-13, cheoljoo@gmail.com)

## docs — ETF 종목 등록 안내 추가
- `claude/register_etf_ticker.md` 신규: 이메일 형식, 처리 실행, 답장 예시(성공/실패), 지원 ticker 형식 표
- `README.md`: "ETF 종목 등록" 섹션 추가 (맨 끝)
- `render.py`: `_DOC_LABELS`, `_DOC_ORDER`에 `register_etf_ticker` 추가 → docs.html에 반영

## analyze/run.py — FutureWarning 수정
- `import numpy as np` 추가
- `iloc` 할당 전 컬럼 dtype 확인: float → `to_numpy(dtype=float, na_value=np.nan)`, object → `to_numpy(dtype=object)`
- `FutureWarning: Setting an item of incompatible dtype` 완전 제거

## 문서 업데이트
- `claude/claude-work.md`: 2026-05-12/13 작업 항목 추가
- `claude/claude-opus-4-7_guide.md`: 8차 업데이트 — gmail-etf 섹션(6.4), dashboard 파일 목록(6.5), 리스크 항목 2개 추가, 향후 작업 1개 추가
- `var RANK_MAP` JS 주입, `tickerRank(tk)` 함수 추가
- per-ticker 테이블에 RANK(`rank_in_group`) 컬럼 추가
- "rank" 정렬 버튼 추가 (기본 오름차순 — 낮은 rank = 상위 종목)

## optimize/streak_grid.py — debug 전용 로그 분리
- `_debug_log(enabled, message)` 헬퍼 추가
- `debug=False`(기본) 시 streak 로딩/완료/그룹별 진행 로그 완전 침묵

## 기타
- `config/recipients.yml`: `cheoljoo.lee@lge.com` 수신자 추가
- `README.md`: Motivation 섹션 추가 (10월이평선 기반 투자 배경)


- v2-all: 투자 리포트 메일에서 --only-me 제거 (전체 수신자 발송)
- v2-optimize 완료 후 v2-dashboard 자동 실행 추가

### 문서 업데이트
- claude-work.md: 2026-05-11 세션 내용 추가
- claude-opus-4-7_guide.md: 6차 업데이트
  - per_ticker 디렉터리 트리에 KOSPI200/SP500 추가
  - render.py/optimize.html 주석 현행화

---

feat: dashboard owner 표시, 신규상장 종목 안내, candle.sh v2-all 전환

## dashboard — index.html owner 이메일 표시
- `render.py`: `common_ctx`에 `owner_name="이철주"`, `owner_email` (recipients.yml 연동) 추가
- `templates/index.html`: 헤더에 `Owner: 이철주 <cheoljoo@gmail.com>` (mailto 링크)
- `dashboard_site/index.html`: 현재 생성 파일도 동일 반영

## dashboard — group_returns.html 신규 상장/데이터 누적 중 섹션
- `render.py`: `MA10M_MIN_ROWS=200`. instruments에 있지만 period_table에 없는 종목 중
  daily CSV 행수 < 200인 종목을 `new_listings_by_group`으로 수집, 그룹 ctx에 전달
- `templates/group_returns.html`: 수익률 테이블 아래 amber 섹션 추가
  — 종목명/보유일수/필요일수(200)/진행률 바 표시
  — 200일 도달 시 자동으로 수익률 테이블에 포함됨 안내

## candle.sh — make v2-all 래퍼로 전면 교체
- 기존 pvs_crawler 코드 → `make v2-all 2>&1 | tee v2-all.log`
- 날짜별 log backup: `v2-all_YYYY_MM_DD.log` (같은 날 재실행 시 `-1`, `-2` 번호 부여)


Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
