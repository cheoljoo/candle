# CANDLE

캔들차트 하나로 끝내는 추세추종 투자 — 책 내용 구현

KOSPI 200 · S&P500 · 주요 ETF 종목의 10월 이동평균 대비 현재가 위치를 분석하고,  
최근 7거래일 이격률 추이와 변곡점 종목을 자동으로 추출합니다.

## 구조

```
candle/
├── fetch_data.py       # 일봉 종가 + 거래량 + MA10M 수집 (증분, 당일 재실행 시 스킵)
├── analyze.py          # 10월 이평 분석 + 7일 이격률 + 변곡점 출력
├── backtest_type1.py   # MA10M 돌파/이탈 기반 type1 백테스트
├── backtest_type2.py   # 연속 +/- 확인 후 매매하는 type2 백테스트
├── backtest_reason.py  # type1 결과의 상/하위 수익률 차이 원인 분석
├── main.py             # fetch + analyze 통합 초기 버전 (참고용)
├── Makefile
└── data/               # .gitignore 등록 — 커밋하지 않음
    ├── kospi_list.csv
    ├── sp500_list.csv
    ├── stocks/{code}.csv       # Date, Close, Volume, MA10M
    └── stocks_us/{symbol}.csv  # Date, Close, Volume, MA10M
```

## 사용법

```bash
make fetch    # 데이터 수집 (당일 이미 수집 시 스킵, MA10M/Volume 자동 보강)
make analyze  # 분석 실행
make backtest-type1  # type1 백테스트 실행 (기본: 올해 01-01 ~ 오늘)
make backtest-type2  # type2 백테스트 실행 (기본: plus/minus 연속일수 1)
make backtest-type4  # 시가총액 상위 조건 기반 type4 백테스트
make backtest-compare  # 동일 초기자금 기준 type1/type2/type3/type4 비교
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

## Type2 백테스트

`backtest_type2.py` 는 type1과 같은 매매 규칙 구조를 사용하지만, 부호가 바뀐 당일 즉시 매매하지 않고
**연속된 `+` / `-` 일수 확인 후** 매매합니다.

- **매수:** `-→+` 전환 후 `--plus_days`일 연속 `+` 가 유지되면 10주 매수
- **매도:** `+→-` 전환 후 `--minus_days`일 연속 `-` 가 유지되면 보유 10주 전량 매도
- `--plus_days=1`, `--minus_days=1` 이면 type1과 동일한 규칙
- 저장된 `Volume` 이 있으면 **평가거래량 / 최근 20일 평균 거래량 / 거래량배수**도 함께 출력

CLI 옵션:

- `--from`: 시작일 (`YYYY-MM-DD`, 기본값: **2년 전 `01-01`**)
- `--to`: 종료일이자 **평가 기준일** (`YYYY-MM-DD`, 기본값: 오늘)
- `--plus_days`: 매수 전 확인할 연속 `+` 일수 (기본값: `1`)
- `--minus_days`: 매도 전 확인할 연속 `-` 일수 (기본값: `1`)
- `--output_csv`: 결과 CSV 저장 경로 (기본값: `backtest_type2.csv`)

예시:

```bash
uv run python backtest_type2.py
uv run python backtest_type2.py --plus_days 3 --minus_days 2
uv run python backtest_type2.py --from 2024-01-01 --to 2026-04-11 --plus_days 5 --minus_days 3 --output_csv data/backtest_type2.csv
```

추가 출력 컬럼:

- `평가거래량`: 평가가격일의 거래량
- `20일평균거래량`: 평가가격일까지 최근 20거래일 평균 거래량
- `거래량배수`: `평가거래량 / 20일평균거래량`

## Type1 결과 원인 분석

`backtest_reason.py` 는 `backtest_type1.csv` 를 읽어 수익률 상위/하위 종목의 차이를 정리합니다.
기간 주가상승률, 최대상승률, 종료 시점 낙폭, **첫 매수일**, **첫 매수일 거래량/직전 20일 평균 거래량 배수**, 매수/매도 횟수,
사고판수익률, 미실현손익 비중을 함께 보고
왜 성과 차이가 났는지 종목별 원인 문구로 출력합니다.

```bash
uv run python backtest_reason.py
uv run python backtest_reason.py --input_csv backtest_type1.csv --top_n 5
```

## Type4 백테스트

`backtest_type4.py` 는 **시가총액 상위 조건**을 매수 필터로 추가한 전략입니다.

- **KOSPI:** 시가총액 상위 `30`
- **S&P500:** 시가총액 상위 `100`
- **매수:** `+` 신호이고, 현재 상위 종목이거나 그 시점의 추정 시가총액 순위가 상위 조건 안이면 매수
- **매도:** `-` 신호가 나오면 매도

시점별 시가총액은 정확한 과거 시총 데이터가 아니라,
**현재 시가총액 ÷ 현재가 = 유통주식수 근사치**를 구한 뒤
이를 과거 종가에 곱해 근사 계산합니다.

기본 기간은 `2020-01-01 ~ 오늘` 입니다.

```bash
uv run python backtest_type4.py
uv run python backtest_type4.py --to 2026-04-12 --output_csv data/backtest_type4.csv
```

## 동일 초기자금 기준 type1 / type2 / type3 / type4 비교

`backtest_compare.py` 는 종목마다 동일한 초기자금으로 아래 4가지 전략의 **현재 총자산**을 비교합니다.

- **type1:** `-→+` 전환 시 가용 현금 전액으로 가능한 최대 주수 매수, `+→-` 전환 시 전량 매도
- **type2:** `plus_days/minus_days` 확인 후 가용 현금 전액 매수 / 전량 매도
- **type3:** 신호와 무관하게 **3개월마다 동일 금액 적립식 매수 후 계속 보유**
- **type4:** KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 종목만 `- -> +` 전환에서 매수, `+ -> -` 전환에서 매도

기본값:

- 기간: `2020-01-01 ~ 오늘`
- type2: `plus_days=33`, `minus_days=5`
- 초기자금:
  - `KOSPI 200`: `10,000,000 KRW`
  - `S&P500`, `ETF`: `10,000 USD`
- 단, **type4만 별도 자금 배분**:
  - `KOSPI 200`: `10,000,000 / 30`
  - `S&P500`: `10,000 / 100`
  - ETF: 미지원

```bash
uv run python backtest_compare.py
uv run python backtest_compare.py --to 2026-04-12 --plus_days 33 --minus_days 5
uv run python backtest_compare.py --output_csv data/backtest_compare.csv
```

주요 출력:

- `type1_총자산`, `type2_총자산`, `type3_총자산`
- `type4_총자산`
- `type4_초기자금`
- 각 전략별 `현금`, `보유주식수`, `손익`, `수익률(%)`, `매수횟수`, `매도횟수`
- `최고전략`
- 평가일 `거래량`, `20일평균거래량`, `거래량배수`

참고:

- `type4` 는 현재 KOSPI 200 / S&P500 에만 적용되고, ETF는 미지원입니다.

## 분석 로직

- **MA10M(10월이평)**: 월말 종가 기준 `rolling(10)` 이동평균 → 일봉 인덱스에 `forward-fill`
- **이격률(%)** = `(현재가 − MA10M) / MA10M × 100`
- MA10M과 Volume은 `fetch_data.py` 수집 시 CSV에 함께 저장 → `analyze.py`, `backtest_type2.py`에서 바로 사용
- 주가 3,000원 미만 KOSPI 종목 제외
- 한글 종목명 터미널 정렬: `unicodedata.east_asian_width()` 기반 전각문자 너비 보정

## 환경

- Python 3.13+
- 패키지 관리: `uv`
- 주요 라이브러리: `finance-datareader`, `pandas`
