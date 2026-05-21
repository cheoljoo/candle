feat: 신규 type 6종 + config-driven 자동화 + 버그수정 + reason컬럼 (2026-05-21)

## 신규 backtest type 6종 구현
- type4_boost: DCA(90일) + -→+ 변곡 × inflection_boost 추가매수 + +→- 30% 부분매도 (price_guard)
- type3_im_boost: DCA + -→+ 변곡 × (boost + alpha × 할인율) 추가매수, 매도없음
- type4_boost_opt: type4_boost의 streak 신호 버전 (per-ticker 최적 파라미터)
- type3_im_boost_opt: type3_im_boost의 streak 신호 버전
- type5_dd: -→+ 변곡 전액매수 + drawdown 분할매도 (1차 15%→50%, 2차 25%→30%)
- type2_2_opt_v: 최적 streak ±30% variant band 첫 진입일 거래
- 전 파이프라인 반영: backtest → compare → simulate(rule=995건) → dashboard

## config/strategies.yml 완전 자동화
- ALL_TYPES: config.py 하드코딩 제거 → strategies.yml `type` 시작 키 자동 파생 (@property, YAML 순서 유지)
- type_descriptions(dashboard): render.py 하드코딩 제거 → short_desc/description 자동 읽기
- simulate 신호: engine.py if/elif 제거 → simulate:{signal,sell} 공통 로직
- strategies.yml에 short_desc + description + simulate 섹션 추가 (15종 전체)
- 새 type 추가: strategies.yml 1파일 + backtest 코드만 추가 → 목록·설명·simulate 자동반영

## 버그 수정
- CASH_TRACKING_TYPES 누락(compare/run.py): 7종 추가 → type2_2_opt_v 수익률 -93%→+1007% 정정
- _all.csv / _summary.csv KR/US merge 버그(backtest/run.py): 분리 실행 시 덮어쓰기 → 타마켓 행 보존
- _type_legend.html 전략코드 글자겹침: w-16→w-40

## backtest 거래 결정사유 (reason) 추가
- base.py: TRADE_COLUMNS에 "reason" 추가, buy()/sell() reason 파라미터
- 13개 type 파일: 각 신호 이유 기록 (예: "MA10M 변곡 -→+", "+8일 연속 유지", "DCA 90일 주기",
  "변곡 -→+ alpha 추가매수 (×1.50)", "Drawdown -16.3% (≥15%) 1차 50% 매도")
- render.py _generate_trade_jsons(): reason 컬럼 포함
- ticker_trades.html: "결정 사유" 컬럼 추가 (buy=초록/sell=빨강)

## 전략별 요약(compare.html) 탭 구조 변경 + 전략명 정렬
- 기존: 1탭=기간, 2탭=전략, 테이블=그룹별
- 변경: 1탭=기간, 2탭=그룹(KOSPI200/SP500/ETF_KR/ETF_US/TOTAL), 테이블=전략별(전략명 오름차순)

## 기간별 주식수 % 변화 표시 (ticker_trades.html)
- fmtQtyCell(): (±N.N%) 색상 표시 추가 (증가=초록, 감소=빨강)

## 문서 업데이트 (21차)
- claude-opus-4-7_guide.md: 21차 헤더 + Phase 3/4/5 + Config-driven 섹션 추가
- claude-work.md: 2026-05-21 전체 작업 로그 (4차분 포함)

---

feat: compare Top10%/전체분리 + 문서 19차 업데이트 (2026-05-20)

## 신규 backtest type 6종 구현
- type4_boost: DCA + -→+ 변곡 × inflection_boost 추가매수 + +→- 30% 부분매도 + price_guard
- type3_im_boost: DCA + -→+ 변곡 × (boost + alpha × discount_ratio) + 매도없음 + alpha 할인
- type4_boost_opt: type4_boost의 streak 신호 버전
- type3_im_boost_opt: type3_im_boost의 streak 신호 버전
- type5_dd: -→+ 전액매수 + drawdown(15%→50%, 25%→30%) 분할매도 + high_watermark 관리
- type2_2_opt_v: 최적streak ±30% variant band 첫 진입일 거래

## 연동 파일 수정
- backtest/run.py: 6종 dispatch + DCA 증분 처리(last_dca_date/last_sell_price/last_sell_inflection_price 복원)
- config/strategies.yml: 6종 파라미터 + enabled_types 추가
- config.py + backtest/__init__.py: ALL_TYPES 갱신
- simulate/engine.py: _rule_signal() + _rule_qty() 6종 신호 로직 추가

## 검증
- backtest: 6종 CSV 생성 확인
- compare: strategy_summary.csv 6종 행 포함 확인
- simulate: rule=962건, decisions.csv 6종 rule 소스 확인
- dashboard: decisions.html 6종 필터 버튼 정상 생성 (11개 파일)

## 문서 업데이트 (20차)
- claude-opus-4-7_guide.md: 20차 헤더 + 6종 타입 설명 추가
- claude-work.md: 2026-05-21 작업 로그 추가

---

feat: compare Top10%/전체분리 + 문서 19차 업데이트 (2026-05-20)

## compare.html — 수익률 Top 10% 상세 내역으로 개편
- 제목: "내림 순위 전체 상세" → "📈 수익률 Top 10% 상세 내역"
- 각 그룹 테이블: `max(group_size // 10, 1)`개만 표시 (전체 대신 상위 10%)
- 헤더: "상위 N개 / 전체 M개 (Top 10%)" 표시
- 제목 옆 "📋 내림 순위 전체 종목 상세 →" 링크 추가 (compare_full.html)

## compare_full.html — 전체 종목 내림차순 페이지 신규
- 기간×전략 2단 탭 구조 (compare.html과 동일)
- 전체 종목 수익률 내림차순, Top 10% 구간 ★ 뱃지·연초록 배경 강조
- 우상단 "← 전략별 요약 (Top 10%)" 복귀 버튼
- render.py에 compare_full.html 렌더링 추가

## 문서 업데이트 (19차)
- claude-opus-4-7_guide.md: 19차 헤더 + compare_full.html 섹션 추가
  대시보드 파일 목록에 compare_full.html 추가
- claude-work.md: 2026-05-20 2차 작업 로그 추가
