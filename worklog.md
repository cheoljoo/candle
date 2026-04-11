## 2026-04-11 11:16 ~ 12:17 (1h 1m) [tool: copilot-cli / session: f2c11256-1494-4558-ae54-888c7b541e32]
- `backtest_type1.py` 추가: MA10M `-→+` 10주 매수 / `+→-` 전량 매도 규칙으로 KOSPI 200, S&P500, ETF 백테스트 구현
- 평가 기준 정리: `--from`, `--to`, `--output_csv` CLI 추가, `--to`를 평가기준일로 사용하고 평가가격일 별도 기록
- 지표 확장: 사고판수익/사고판수익률(닫힌 거래만), 총손익/수익률(평가손익 포함), 그룹별 합계 행 추가
- 실행 환경 정리: `Makefile`에 type1 프리셋 타겟 추가, `README.md`와 `--help`에 사용법/기준/출력 컬럼 문서화

## 2026-04-10 17:43 ~ 21:56 (4h 13m) [tool: copilot-cli / session: 18954c03-67a8-46b8-8d43-e2ff49c8dfa3]
- main.py 실행 환경 구성: `finance-datareader`, `pandas` 의존성 설치 (uv add)
- `fdr.DataReader(unit='M')` API 변경 대응 → 일봉 resample('ME')로 월봉 계산하도록 수정
- 빈 DataFrame sort_values KeyError 버그 수정
- fetch_data.py 분리: 증분 수집 (당일 데이터 있으면 스킵, 마지막 날짜 이후만 추가)
- analyze.py 분리: 저장 데이터 읽어 분석, 네트워크 불필요
- Makefile 생성: make fetch / analyze / all / clean
- GitHub 저장소(cheoljoo/candle) 초기 push
- analyze.py 개선: 최근 7거래일 이격률 컬럼 추가, 변곡점 종목 별도 섹션 출력
- .github/copilot-instructions.md 프로젝트 실정에 맞게 업데이트

## 2026-04-10 (2차) [tool: copilot-cli / session: 18954c03-67a8-46b8-8d43-e2ff49c8dfa3]
- 한글 종목명 열 정렬 수정: unicodedata.east_asian_width() 기반 str_width / print_table 구현
- 시가총액 조/억 단위 포맷 추가 (format_marcap)
- 티커 컬럼 추가
- S&P500 전 종목 분석 추가 (data/stocks_us/ 저장, sp500_list.csv 활용)
- ETF 분석 추가: VOO, SPY, QQQ, SCHD, JEPI, SOXX, XLE
- fetch_data.py 리팩터: fetch_stock_data() 공통 함수, KOSPI/US 공통 처리
- MA10M(10월이평) CSV 사전 계산 저장: compute_ma10m() 추가, Close + MA10M 컬럼 저장
  - 기존 CSV에 MA10M 없으면 make fetch 재실행 시 네트워크 없이 자동 백필
  - analyze.py는 CSV의 MA10M 컬럼 직접 사용 (재계산 불필요), fallback 포함
- 변곡점 테이블에 10월이평 컬럼 추가
- sort_values float/str 혼재 TypeError 수정 (key=pd.to_numeric)
- 변곡점 종목 data/inflection_points.csv 파일 저장 기능 추가 (기준일·그룹 컬럼 포함)
