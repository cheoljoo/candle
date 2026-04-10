## 2026-04-10 — FinanceDataReader API 변경 대응

- `fdr.DataReader(symbol, unit='M')` 은 최신 버전에서 지원 종료
- 월봉이 필요하면 일봉 수집 후 `resample('ME').last()` 로 직접 생성할 것

## 2026-04-10 — 증분 데이터 수집 설계

- CSV 마지막 행의 날짜를 확인해 당일이면 스킵, 이전이면 그 다음 날부터만 수집
- 같은 날 여러 번 실행해도 네트워크 요청 없이 빠르게 완료됨

## 2026-04-10 — 10월 이평의 일봉 forward-fill

- 10월 이평은 월말에만 갱신되므로 `reindex(daily_index, method='ffill')` 로 일봉에 적용
- 덕분에 매일의 이격률을 계산할 수 있고, 변곡점(부호 변경) 탐지가 가능해짐

## 2026-04-10 — pyproject.toml 패키지명 주의

- PyPI 패키지명은 `finance-datareader` (하이픈), import명은 `FinanceDataReader` (CamelCase)
- `uv add FinanceDataReader` 는 실패 → `uv add finance-datareader` 로 설치

## 2026-04-10 — 한글 터미널 정렬

- `pd.to_string()` 은 한글 전각문자 너비를 1칸으로 처리 → 열 어긋남 발생
- `unicodedata.east_asian_width(ch) in ('W', 'F')` → 2칸으로 계산하는 커스텀 `print_table()` 구현
- 모든 값은 str 변환 후 width 기반 패딩 적용

## 2026-04-10 — MA10M CSV 사전 계산 저장

- analyze.py 실행마다 resample/rolling/reindex 반복 계산은 비효율적
- fetch_data.py에서 수집 시 MA10M을 함께 계산해 CSV에 저장 (Close + MA10M 2컬럼)
- analyze.py는 CSV의 MA10M 컬럼을 직접 읽어 사용 → 재계산 불필요
- 기존 CSV(Close만 있는 파일)는 fetch 재실행 시 자동 백필 (네트워크 요청 없음)
- MA10M 컬럼이 없는 경우 fallback으로 즉석 계산하여 하위 호환 유지

## 2026-04-10 — sort_values 혼재 타입 오류

- 이격률 컬럼에 float 값과 '-' 문자열이 혼재할 때 sort_values가 TypeError 발생
- `key=lambda col: pd.to_numeric(col, errors='coerce')` 로 해결
- S&P500처럼 종목 수가 많고 상장일이 다른 경우 반드시 필요

## 2026-04-10 — 변곡점 종목 파일 저장

- print_section()이 inflect_df를 반환하도록 변경
- main()에서 3섹션(KOSPI/S&P500/ETF) 변곡점을 합쳐 data/inflection_points.csv 저장
- 컬럼: 기준일, 그룹, 티커, 종목명, 시가총액, 방향, 현재가, 10월이평, 현재이격률(%), 날짜별이격률
- data/ 는 .gitignore 등록이므로 inflection_points.csv 도 자동 제외


