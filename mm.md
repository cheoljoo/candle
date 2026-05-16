feat: 리스크 지표·거래상세·US시그널·외국인매매 + MDD설명·링크수정·US차트 (2026-05-16~17)

## Feature 3 — 리스크 지표 (MDD·승률·평균보유일)
- `compare/run.py`: `_compute_risk_map()`, `_win_rate_and_hold()`, `_mdd_from_trades()` 신규
- `strategy_summary.csv`, `per_ticker.csv`에 `avg_mdd`, `avg_win_rate`, `avg_hold_days` 컬럼 추가
- `compare.html`: 설명 섹션(`<details>`) + 테이블 컬럼 3개 추가 (색상: MDD≤10%초록/≤25%주황/>25%빨강, 승률≥60%초록)
- 활용: `make v2-compare` 후 전략별 요약 탭

## Feature 8 — 백테스트 거래 상세 페이지
- `render.py`: `_generate_trade_jsons()` → `dashboard_site/data/trades/{ticker}.json`
- `ticker_trades.html` 신규: URL 해시 기반(`#005930`), JS fetch로 요약 카드 + 거래 테이블 표시
- 404 시 "백테스트가 실행되지 않은 종목" 친화적 안내 메시지
- `group_returns.html`: `tickers_with_trades` 집합으로 데이터 있는 종목만 링크 표시
- `_nav.html`: "거래 이력" 독립 메뉴 제거 (group_returns 상세 행 링크로만 접근)
- `render.py`: trade JSON 생성을 group_returns 렌더 전으로 이동
- 활용: KOSPI200/SP500/ETF 페이지에서 종목 클릭 → 상세 펼치기 → "📋 거래 이력 상세 →"

## Feature 10 — 미국 시장 시그널 (VIX + 수익률 곡선)
- `fetch/market_signals_us.py` 신규: yfinance `^VIX`, `^TNX`, `^IRX` 증분 수집
- `candle market-signals-us` CLI + `make v2-market-signals-us` 타겟
- `market_signals.html`: KR/US Alpine.js 탭 분리. US 탭에 VIX 3개월 막대 SVG + Spread 꺾은선 SVG + 테이블 + 용어 설명
- `render.py`: `_load_market_signals_us()` + `common_ctx["market_signals_us"]`
- 활용: `make v2-market-signals-us` → `make v2-dashboard` → 시장 시그널 페이지 US 탭

## Feature 13 — KOSPI200 외국인/기관 종목별 매매
- `fetch/foreign_trading.py` 신규: pykrx per-ticker, ThreadPoolExecutor 4-worker 병렬
- `candle foreign-trading` CLI + `make v2-foreign-trading` 타겟
- `group_returns.html`: KOSPI200 종목 상세 행에 외국인/기관 5일 순매수 합산 표시
- 활용: `make v2-foreign-trading` → `make v2-dashboard` → KOSPI200 종목 클릭

