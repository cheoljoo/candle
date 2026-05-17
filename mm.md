feat: ticker 컬럼 str 강제화 + market_calendar 기반 비거래일 decisions 검증 가드 + 변곡점 발생 테이블 날짜 컬럼 추가

## storage/csv_io.py — ticker 컬럼 str 강제화
- `read()` 함수: `pd.read_csv()` 후 `"ticker"` 컬럼이 있으면 `.astype(str)` 강제
- KR ticker(`000120` 등) 선행 0 손실 방지 — 모든 CSV 읽기 경로에 자동 적용

## simulate/engine.py — market_calendar 기반 비거래일 decisions 검증 가드
- `_load_trading_days(data_dir)`: market_calendar.csv → `{'KR': {날짜 set}, 'US': {날짜 set}}`
- rule decisions 생성 후 비거래일 date 검증: 해당 market 거래일 set에 없으면 log.warning + skip
- 정상 운영 시 cur_row["date"] = 실데이터 날짜이므로 항상 통과. 이상 상황 방어 필터
- market_calendar.csv 없으면 검증 skip (신규 서버 첫 fetch 전에도 동작 보장)

## dashboard/render.py + index.html — 변곡점 발생 테이블 날짜 컬럼 추가
- `_load_inflections()` 반환 dict에 `"date": target` 추가
- index.html 변곡점 테이블: `날짜` 헤더 + `{{ r.date | dow_fmt }}` 각 행 표시
- KR/US 종목별 각자 해당 시장 거래일 기준 날짜 표시
