## 2026-05-16 22:00 ~ 22:30 (30m) [tool: vscode-copilot / session: eac70b04-1c02-4033-a86d-3c01f01ca2b7]
- `Makefile` : `v2-all-kr` 신규 — 한국장 종료 후 KR 전용 파이프라인 (fetch-kr→analyze-kr→backtest-kr→simulate→market-signals→dashboard)
- `Makefile` : `v2-all-us` 신규 — 미국장 종료 후 US 전용 파이프라인 (fetch-us→analyze-us→backtest-us→simulate→dashboard)
- `Makefile` : `v2-fetch-kr/us`, `v2-analyze-kr/us`, `v2-backtest-kr/us`, `v2-backtest-compare-full/5y-kr/us` 단계별 타겟 추가
- `Makefile` : help 섹션 "시장별 분리 파이프라인" 항목 추가
- `candle.sh` : 인자(`kr|us`) 기반 파이프라인 분기, 로그 파일명 시장별 분리 (`candle-v2-kr.log` / `candle-v2-us.log` / `candle-v2-YYYY_MM_DD.log`)
- `claude-work.md` : 2026-05-16 3차 항목 추가 (Makefile KR/US 분리, candle.sh 개선)
- `claude-opus-4-7_guide.md` : §4 Makefile 섹션 전면 재작성 (10차), 헤더 날짜 업데이트
- `mm.md` : 최신 commit msg 추가

## 2026-05-16 16:30 ~ 18:37 (2h 7m) [tool: vscode-copilot / session: eac70b04-1c02-4033-a86d-3c01f01ca2b7]
- `templates/_nav.html` : "시장 시그널" 메뉴 추가 (approx by mtime)
- `templates/market_signals.html` 신규: 시장 시그널 전용 독립 페이지 — 경보 배너, 요약 카드, 3개월 차트, 1개월 상세 테이블
- `templates/index.html` 홈 요약 간소화: 오늘 카드 + 3개월 미니 차트 + "전체 보기 →" 링크만 유지
- `render.py` : `uk_fmt` Jinja2 필터 추가 — 10000억 이상 값을 "X조 Y,YYY억" 형식으로 변환 (−44664억 → `-4조 4,664억`)
- `market_signals.py` : `fetch_kospi_index()` 추가 — pykrx로 KOSPI 일별 종가 증분 수집 → `data/market/kospi_index.csv`
- `market_signals.py` : `_calc_correlation()` 헬퍼 (Pearson r), `check_signals()`에 `kospi_df` 파라미터 추가, `result`에 `prog_kospi_corr`/`finv_kospi_corr`/`kospi_data` 반환
- `render.py` : kospi_index.csv 로드, 차트 데이터에 `kospi_close`/`kospi_y_pct` 추가, 테이블에 KOSPI 컬럼, 상관계수 반환
- CSS flex 막대 차트 → SVG 인라인 차트 (막대 + KOSPI 꺾은선 polyline) 교체 (market_signals.html, index.html)
- `market_signals.html` 용어 설명 카드 추가: 프로그램 비차익 순매수 / 금융투자 순매수 정의·활용법·출처
- `market_signals.html` 상관관계 시각화 추가: −1~+1 그라디언트 게이지 바 + 강도 뱃지 + r값 해석 테이블

## 2026-05-16 13:00 ~ 16:22 (3h 22m) [tool: vscode-copilot / session: eac70b04-1c02-4033-a86d-3c01f01ca2b7]
- `src/candle/fetch/market_signals.py` 신규: KRX MDCSTAT02601 프로그램 비차익 데이터 fetch + pykrx 투자자별 매매 fetch
- 퍼센타일 기반 시그널 임계값 구현: 하위 10%(프로그램) / 하위 20% × 3일 연속(금융투자) — 고정 3000억 기준 대신 역사적 분포 활용
- `_get_trading_days()`: KOSPI 인덱스 OHLCV로 실제 거래일만 루프 → 332거래일 54.8초 수집
- `run()`을 incremental 방식으로 개선: 기존 CSV 마지막 날짜 다음부터만 추가 수집, `--days` 파라미터 제거
- `check_signals()`에 `program_max_sell` / `program_max_ratio` 추가 (역사적 최대 순매도 대비 비율)
- `src/candle/cli.py`: `candle market-signals` CLI 명령 추가 (--today, --quiet 옵션만)
- `Makefile`: `v2-market-signals` 타겟 추가 (v2-all 파이프라인 포함), `--days 360` 제거
- `render.py`: `_load_market_signals()` 추가 — 3개월 차트 데이터 + 1개월 테이블(최신순, MAX/비율 컬럼), `common_ctx`에 `market_signals=` 추가
- `index.html`: 시장 시그널 섹션 추가 — 🇰🇷 KR 배지, 3개월 CSS 막대 차트, 1개월 테이블(날짜/순매수/역사적MAX/MAX비율%), owner 옆 GitHub 소스 링크

## 2026-05-12 22:08 ~ 22:19 (0h 11m) [tool: vscode-copilot / session: 99bd5bbc-96aa-4a2e-b28b-f689149eaee3]
- `dashboard/templates/index.html` 변곡점 테이블 개선: Ticker 셀에 종목명(한글/영문) 부제목 표시
- 변곡점 inflection 신호(`-→+`/`+→-`) 색상 구분 추가 (초록/빨강)
- 기간 수익률(best) 컬럼 추가: 기간별 최고전략 수익률 인라인 표시 + 그룹 내 Rank 표시
- 상세 링크 컬럼 추가: 📊 수익률(해당 그룹 backtest 페이지), ⚙ 최적화(optimize.html) 버튼
- `dashboard/render.py`: `name_map`(ticker→종목명) 및 `period_table_by_ticker`(ticker→수익률row)를 `common_ctx`에 추가

## 2026-05-11 01:19 ~ 09:54 (8h 35m) [tool: vscode-copilot / session: unknown]
- `optimize/streak_grid.py`: `_debug_log()` 헬퍼 추가 — debug 모드일 때만 streak 로딩/완료/그룹별 진행 로그 출력 (일반 실행 시 노이즈 제거)
- `dashboard/templates/optimize.html`: 종목별 최적화 테이블에 RANK(`rank_in_group`) 컬럼 및 정렬 버튼 추가, `RANK_MAP` JS 변수 주입
- `config/recipients.yml`: `cheoljoo.lee@lge.com` 메일 수신자 추가
- `README.md`: Motivation 섹션 추가 — 10월이평선 기반 추세추종 투자 배경 설명

## 2026-04-23 10:40 ~ 11:12 (0h 32m) [tool: gemini-cli / session: unknown]
- `backtest_compare.py` 크래시 수정: 시가총액 순위 데이터(`rank_context`)가 없는 그룹(예: ETF)에서 `type4`, `type4_2` 전략 실행 시 발생하는 `AttributeError` 해결
- `backtest_type4.py` 공통 함수 보완: `can_buy_type4`, `simulate_type4`, `simulate_type4_capital`에 `rank_context=None` 방어 로직 및 "미지원" 상태 반환 추가
- `backtest_type4_2.py` 수정: `simulate_type4_2`에 `rank_context=None` 체크를 추가하여 통합 비교 시 안정성 확보
- 버그 재현 및 검증: `repro_bug.py`를 통한 ETF 그룹 처리 검증 완료

## 2026-04-13 13:45 ~ 15:04 (1h 19m) [tool: copilot-cli / session: ce03f93f-77b2-4490-9159-eb0aa68cbc49]
- `backtest_type4.py` 정리: 중복 함수(`normalize_symbol`, `fetch_us_marketcap_table`) 제거 후 `fetch_data` 에서 임포트, `매수일_시총순위` 컬럼 추가
- `backtest_compare.py` 확장: `최고전략_매수일_시총순위` 컬럼 추가 (최고 전략의 마지막 매수일 당시 시총 순위)
- `backtest_type1_2.py` 신규 생성: 현금 추적 type1 변형 — 첫 매수로 초기 자본 설정, 이후 보유 현금으로 최대 주수 매수
- `backtest_type4_2.py` 신규 생성: type4 시총 조건 + 현금 추적 변형
- `Makefile` 업데이트: `backtest-type1-2`, `backtest-type4-2` 타겟 추가
- `backtest_compare.py`: type1_2/type4_2 전략 비교 추가 (6개 전략으로 확장), 가변 초기자본 집계 수정
- KOSPI 200 수익률 vs 시가총액 상관관계 분석: 피어슨 +0.071, 스피어만 +0.310 (약한 양의 상관), Q4 평균 38.5% vs Q1 14.3%


- `backtest_type4.py` 매수 타이밍 수정: 기간 시작 시 이미 `+` 인 종목은 매수하지 않고, type1과 동일하게 기간 내 `-→+` 전환이 생길 때만 매수하도록 보정
- 삼성전자(`005930`) 검증: 상시 top 30 종목 기준으로 type1/type4의 사고·파는 횟수가 같아야 함을 확인하고, 수정 후 `15회 매수 / 14회 매도`로 일치함을 확인
- 문서 정리: `README.md`, `report.md`, session `plan.md`에 type4 규칙과 type4 전용 자금 기준을 최신 동작에 맞게 반영

## 2026-04-12 23:01 ~ 23:26 (0h 25m) [tool: copilot-cli / session: f2c11256-1494-4558-ae54-888c7b541e32]
- `fetch_data.py` 확장: 저장 CSV에 `Volume` 컬럼을 포함하고, 기존 파일도 `make fetch` 재실행 시 거래량을 자동 보강하도록 수정
- `backtest_type2.py` 확장: 평가거래량, 20일평균거래량, 거래량배수를 출력하고 거래량과 수익률 관계를 실전형 `33/5` 기준으로 분석
- `backtest_compare.py` 추가: `2020-01-01 ~ latest` 기본값으로 동일 초기자금 기준 `type1 / type2 / type3` 총자산 비교 구현
- `backtest_type4.py` 추가: KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 `+` 신호만 매수하는 전략 구현
- `backtest_compare.py` 확장: type4까지 함께 비교하도록 변경하고, 현재 구현은 type4도 종목당 초기자금을 그대로 쓰며 30/100 분할 총자금 방식은 아직 아님을 문서화

## 2026-04-12 01:07 ~ 01:28 (0h 21m) [tool: copilot-cli / session: f2c11256-1494-4558-ae54-888c7b541e32]
- type2 파라미터 전수 탐색: `plus_days/minus_days=1~40` 조합을 비교해 총수익 최적(`23/40`)과 실전형 균형안(`33/5`)을 분리 정리
- 시장별 종목 선정 기준 정리: 현재 `+` 상태, 현재 `+` 연속일수, 전환 빈도, 매수 횟수, KOSPI 시가총액/배당률을 조합해 core/watchlist 후보를 선별
- 운용 방식 정리: 시장별 10개 이하 제한을 전제로 주간 점검, 최대 2종목 교체, 신규는 core 후보만 편입하는 rotation 규칙을 `report.md`에 추가
- 데이터 한계 정리: 저장된 종목 CSV에는 과거 거래량 이력이 없어 거래량 기반 실전 필터는 후속 데이터 수집 확장이 필요함을 명시

## 2026-04-11 11:16 ~ 19:24 (8h 8m) [tool: copilot-cli / session: f2c11256-1494-4558-ae54-888c7b541e32]
- `backtest_type1.py` 추가: MA10M `-→+` 10주 매수 / `+→-` 전량 매도 규칙으로 KOSPI 200, S&P500, ETF 백테스트 구현
- 평가 기준 정리: `--from`, `--to`, `--output_csv` CLI 추가, `--to`를 평가기준일로 사용하고 평가가격일 별도 기록
- 지표 확장: 사고판수익/사고판수익률(닫힌 거래만), 총손익/수익률(평가손익 포함), 그룹별 합계 행 추가
- 실행 환경 정리: `Makefile`에 type1 프리셋 타겟 추가, `README.md`와 `--help`에 사용법/기준/출력 컬럼 문서화
- `backtest_reason.py` 추가: 상/하위 수익률 종목의 차이, 첫 매수일, 거래량 배수, 구간 지속 길이 분석
- 현재 거래일 기준 `+` 상태가 40거래일 이상인 종목 312개를 집계해 `data/current_plus_40.csv` 생성
- `report.md` 생성: 이번 세션의 결과, 핵심 수치, 해석, 재현 방법 정리
- `.github/instructions/global.worklog.instructions.md` 업데이트: 이후 `일 정리` 시 `report.md`도 기본 생성/갱신하도록 규칙 추가

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
