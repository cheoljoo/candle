feat: 시장 시그널 대시보드 고도화 — KOSPI 연동·상관관계·용어 설명·SVG 차트

- `market_signals.html` 신규: 시장 시그널 전용 독립 페이지 (경보 배너, 요약 카드, 3개월 차트, 1개월 테이블)
- `_nav.html`: "시장 시그널" 메뉴 아이템 추가
- `index.html`: 홈 요약 간소화 — 오늘 카드 + 3개월 미니 차트 + "전체 보기 →" 링크
- `render.py`: `uk_fmt` Jinja2 필터 추가 (10000억 이상 → X조 Y,YYY억 변환)
- `market_signals.py`: `fetch_kospi_index()` 신규 — pykrx KOSPI 일별 종가 증분 수집 → `data/market/kospi_index.csv`
- `market_signals.py`: `_calc_correlation()` Pearson r 헬퍼, `check_signals(kospi_df=)`에 통합, `prog_kospi_corr`/`finv_kospi_corr`/`kospi_data` 반환
- `render.py`: kospi_index.csv 로드, 차트 데이터에 `kospi_close`/`kospi_y_pct`(10~90% 정규화) 추가, 테이블에 KOSPI 컬럼
- CSS flex 막대 차트 → SVG 인라인 차트 (`<rect>` 막대 + `<polyline>` KOSPI 꺾은선) 교체 (market_signals.html, index.html)
- `market_signals.html`: 용어 설명 카드(프로그램 비차익/금융투자 정의·경보 로직·출처), 상관관계 시각화(−1~+1 게이지 바, 강도 뱃지, r 해석 테이블)
- 검증: 프로그램 비차익↔KOSPI r=−0.373, 금융투자↔KOSPI r=+0.279 출력 확인
- 문서: `claude-work.md`, `claude-opus-4-7_guide.md` 현행화

feat: KOSPI 시장 시그널 시스템 신규 구축 + 대시보드 통합

- `src/candle/fetch/market_signals.py` 신규: KRX MDCSTAT02601 프로그램 비차익 per-day fetch, pykrx 투자자별 매매 fetch, _get_trading_days() KOSPI 인덱스 기반 거래일 루프 최적화
- 퍼센타일 기반 시그널 임계값: 고정 -3000억 → 역사적 분포 하위 10%(프로그램) / 하위 20% × 3일(금융투자) 로 변경
- `check_signals()`에 `program_max_sell` / `program_max_ratio` 추가 (역사적 최대 순매도 대비 오늘 비율)
- `run()` incremental 방식으로 개선: 기존 CSV 마지막 날짜 다음부터만 추가 수집, `--days` 파라미터 제거
- `cli.py`: `candle market-signals` 명령 추가 (--today, --quiet)
- `Makefile`: `v2-market-signals` 타겟 추가, v2-all 파이프라인 포함, --days 360 제거
- `render.py`: `_load_market_signals()` 추가, `common_ctx`에 `market_signals=` 포함
- `index.html`: 시장 시그널 섹션 — 🇰🇷 KR 배지, 3개월 CSS 막대 차트, 1개월 테이블(날짜/순매수/역사적MAX/MAX비율%), owner 옆 GitHub 소스 링크



