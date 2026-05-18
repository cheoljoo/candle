feat: compare 상위10% 개편 + equity 차트 + UNKNOWN 제거 + 축 색상

- compare/run.py: instruments.csv 미등록 ticker 제외 (UNKNOWN 그룹 제거)
  2000-2015 기간 22개 편출 종목(삼성전자우 등) 필터링
- render.py _load_compare_top10: 반환 구조 계층화 (period→type→group→tickers)
  · backtest _summary.csv 로드 → buy_count/sell_count 추가
  · best_strategy.csv 로드 → 최고전략_매수일_시총순위(RANK) 추가
  · avg_hold_days 포함 / 분모=그룹 전체 종목 수 (비영리 필터 제거)
- compare.html 상위 10% 섹션 전면 개편
  · 기존 팝업 방식 → 독립 section + 2단계 탭 (기간 / 전략 타입)
  · 2×2 그리드: 행1=(ETF_KR|ETF_US) / 행2=(KOSPI200|SP500)
  · 테이블 컬럼: 수익률 + 매수 + 매도 + 보유일 + RANK + 거래이력 버튼
- ticker_trades.html 차트 개선
  · equity 라인 추가: 보유수량×종가+현금 (평가액+현금, indigo)
  · tooltip에 평가액+현금 표시
  · yQty 축 display:true (green, 보유수량 제목)
  · yEquity 축 색상 indigo / yPrice 축 색상 slate

