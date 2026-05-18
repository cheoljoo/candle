fix: analyze ValueError + 대시보드 테이블 정렬 + compare KR/US 병합

- analyze/run.py: _STRING_COLS 하드코딩 set으로 ma10m_updown/inflection dtype 오탐 수정
  (pd.NA 초기화 시 float64로 설정되어 is_float_dtype이 True 반환 → ValueError 발생하던 버그)
- _nav.html: 공유 JS 정렬 유틸리티 추가 — data-sortable 테이블 헤더 클릭 시 ⇕/↑/↓ 정렬
- compare.html, decisions.html, group_returns.html, history.html, index.html,
  market_signals.html, ticker_trades.html: data-sortable 속성 추가
- compare.html: 전략 컬럼 항상 전략명 표시 (정렬 후 빈칸 문제 해결)
- compare/run.py: strategy_summary.csv 저장 시 currency 기준 KR/US 데이터 병합
  (v2-all-kr / v2-all-us 각각 실행해도 4개 그룹 KOSPI200·ETF_KR·SP500·ETF_US 모두 유지)
