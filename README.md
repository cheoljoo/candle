# CANDLE

캔들차트 하나로 끝내는 추세추종 투자 — 책 내용 구현

KOSPI 200 · S&P500 · 주요 ETF 종목의 10월 이동평균 대비 현재가 위치를 분석하고,  
최근 7거래일 이격률 추이와 변곡점 종목을 자동으로 추출합니다.

## 구조

```
candle/
├── fetch_data.py       # 일봉 종가 + MA10M 수집 (증분, 당일 재실행 시 스킵)
├── analyze.py          # 10월 이평 분석 + 7일 이격률 + 변곡점 출력
├── backtest_type1.py   # MA10M 돌파/이탈 기반 type1 백테스트
├── main.py             # fetch + analyze 통합 초기 버전 (참고용)
├── Makefile
└── data/               # .gitignore 등록 — 커밋하지 않음
    ├── kospi_list.csv
    ├── sp500_list.csv
    ├── stocks/{code}.csv       # Date, Close, MA10M
    └── stocks_us/{symbol}.csv  # Date, Close, MA10M
```

## 사용법

```bash
make fetch    # 데이터 수집 (당일 이미 수집 시 스킵, MA10M 자동 백필)
make analyze  # 분석 실행
make backtest-type1  # type1 백테스트 실행 (기본: 올해 01-01 ~ 오늘)
make backtest-type1-2020-2025  # 2020-01-01 ~ 2025-12-31 결과 저장
make backtest-type1-2025-now   # 2025-01-01 ~ 오늘 결과 저장
make all      # fetch → analyze 순서 실행
make clean    # data/ 초기화
```

## 분석 대상

| 그룹 | 종목 수 | 비고 |
|------|---------|------|
| KOSPI 200 | 200개 | 시가총액 상위 200 |
| S&P500 | ~503개 | 전 종목 |
| ETF | 7개 | VOO, SPY, QQQ, SCHD, JEPI, SOXX, XLE |

## 분석 출력

각 그룹별로 다음 두 섹션 출력:

1. **★ 변곡점 종목** — 최근 7거래일 내 이격률 부호가 바뀐 종목 (`+→-` / `-→+`)  
   컬럼: 티커 · 종목명 · 시가총액 · 방향 · 현재가 · **10월이평** · 현재이격률(%) · 날짜별이격률
2. **전체 분석** — 종목별 현재가, 10월이평, 최근 7거래일 이격률(%)

## Type1 백테스트

`backtest_type1.py` 는 저장된 일봉 `Close`, `MA10M` 데이터를 이용해 아래 규칙으로 종목별 백테스트를 수행합니다.

- **매수:** 종가가 10월이평 아래(`-`)에서 위(`+`)로 바뀐 날 종가에 **10주 매수**
- **매도:** 종가가 10월이평 위(`+`)에서 아래(`-`)로 바뀐 날 종가에 **보유 10주 전량 매도**
- **체결 가정:** 신호가 나온 당일 종가를 매매 가격으로 사용
- **미청산 평가:** 기간 종료 시 아직 매도 신호가 없으면 **`--to` 기준 평가 종가**로 평가손익 계산
- **초기 상태:** 시작 시점 보유 주식 없음, 수수료/세금/슬리피지 미반영

CLI 옵션:

- `--from`: 시작일 (`YYYY-MM-DD`, 기본값: **2년 전 `01-01`**)
- `--to`: 종료일이자 **평가 기준일** (`YYYY-MM-DD`, 기본값: 오늘)
- `--output_csv`: 결과 CSV 저장 경로 (기본값: `backtest_type1.csv`)

예시:

```bash
uv run python backtest_type1.py
uv run python backtest_type1.py --from 2020-01-01 --to 2025-12-31 --output_csv data/backtest_type1_2020_2025.csv
uv run python backtest_type1.py --from 2025-01-01 --to 2026-04-11 --output_csv data/backtest_type1_2025_now.csv
```

결과는 KOSPI 200 / S&P500 / ETF 각각에 대해 종목별로 아래 항목을 출력합니다.

- 평가종가 / 평가기준일 / 평가가격일
- 매수횟수 / 매도횟수 / 보유주식수
- 총매수금액
- 사고판수익 / 사고판수익률(%) = **매수 후 매도까지 끝난 거래만** 대상으로 계산
- 실현손익 / 미실현손익 / 총손익
- 수익률(%) = `총손익 / 총매수금액 × 100`
- 마지막매수일 / 마지막매도일
- 각 그룹(KOSPI 200 / S&P500 / ETF) 마지막 줄에는 **금액 합계와 합계 기준 전체 수익률**이 추가됨

`Makefile` 에는 자주 쓰는 두 구간을 바로 생성하는 프리셋도 포함되어 있습니다.

- `make backtest-type1-2020-2025`
- `make backtest-type1-2025-now`

## 분석 로직

- **MA10M(10월이평)**: 월말 종가 기준 `rolling(10)` 이동평균 → 일봉 인덱스에 `forward-fill`
- **이격률(%)** = `(현재가 − MA10M) / MA10M × 100`
- MA10M은 `fetch_data.py` 수집 시 CSV에 사전 계산 저장 → `analyze.py`는 재계산 없이 바로 사용
- 주가 3,000원 미만 KOSPI 종목 제외
- 한글 종목명 터미널 정렬: `unicodedata.east_asian_width()` 기반 전각문자 너비 보정

## 환경

- Python 3.13+
- 패키지 관리: `uv`
- 주요 라이브러리: `finance-datareader`, `pandas`
