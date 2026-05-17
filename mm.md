feat: 거래이력 Chart.js 차트 + 전략설명 + Buy-Sell 수익률 + prev_action 신호변화

## dashboard/render.py — 거래 이력 JSON에 prices 추가
- inst_map에 market 필드 추가
- `_load_ticker_prices(data_dir, market, ticker, months=12)` 헬퍼 신규
  - data/daily/{KR|US}/{ticker}.csv 최근 12개월 종가·ma10m 반환
- `_generate_trade_jsons()` payload에 `prices` 키 추가

## dashboard/templates/ticker_trades.html — Chart.js 거래 이력 차트
- Chart.js 4.4.4 CDN 추가
- `buildTradeChart()` 함수 신규: 종가(slate), 10월MA(orange dash), 매수(green▲), 매도(red▽), 보유수량(green step-fill, 우측 y축)
- tooltip: 매수→현금·보유수량, 매도→현금·Buy-Sell 수익률
- ON 전략만 차트 표시 (ENABLED_TYPES 기반 isOn 조건)
- 전략 설명 표시: TYPE_DESCRIPTIONS JS Map (short — detail) + ON/OFF 뱃지
- 리스크 지표 설명 섹션 기본 접힘 상태 (hidden + 펼치기 버튼)
