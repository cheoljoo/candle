feat: decisions 직전날짜 신호비교 + enabled_types 필터 + 거래이력링크 + Buy-Sell 수익률

## backtest/base.py — Buy-Sell 사이클별 수익률(buy_sell_return_pct) 추가
- TRADE_COLUMNS에 `buy_sell_return_pct` 추가
- Portfolio: `_last_buy_total` 필드로 buy 시점 총자산 기록
  - buy(): `_last_buy_total = holding_value + cash` 저장
  - sell(): `(sell_total − _last_buy_total) / _last_buy_total × 100` 계산 후 _record() 전달
  - from_trades() 증분 복원 시 미결 buy의 _last_buy_total 복원

## dashboard/render.py — buy_sell_return_pct JSON 생성
- `_compute_buy_sell_returns()` 헬퍼: 기존 CSV에 컬럼 없을 때 buy-sell 쌍으로 계산(폴백)
- `_generate_trade_jsons()`: buy_sell_return_pct 포함, 없으면 자동 계산

## dashboard/templates/ticker_trades.html — Buy-Sell 수익률 컬럼 표시
- "현금" 옆 "Buy-Sell 수익률" 컬럼 추가
- sell 행: 이익(+) = 빨간색 굵은 글씨, 손실(−) = 파란색 굵은 글씨

## dashboard/render.py — prev_action 기반 신호 변화 감지
- `_load_last_backtest_actions()` 제거 (정상 운영 시 backtest=simulate로 항상 동일)
- decisions.csv 직전 날짜 (ticker, source) → action 매핑 → prev_action, signal_changed 필드
- enabled_types에 없는 rule type decisions 필터링 (stale type1_1 등 방어)

## dashboard/templates/decisions.html — 신호 변화 색상 코딩
- signal_changed + buy → 빨간 굵은 글씨 + "← 직전: sell"
- signal_changed + sell → 파란 굵은 글씨 + "← 직전: buy"
- 변화없음 → 기존 pill + prev_action 회색 소자

## dashboard/templates/ticker_trades.html — #TICKER:type_name URL hash 지원
- focusType 자동 펼침 + indigo ring + smooth scroll

## 변곡점 테이블 날짜 컬럼 + ticker str 강제화 + market_calendar 검증 가드
- index.html 변곡점 테이블: 날짜 컬럼 (KR/US 시장별 거래일 기준)
- csv_io.read(): ticker 컬럼 `.astype(str)` 강제 (KR 선행 0 보존)
- engine.py: market_calendar 기반 비거래일 decisions 검증 → skip
