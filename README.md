# CANDLE

캔들차트 하나로 끝내는 추세추종 투자 — 책 내용 구현

KOSPI 200 · S&P500 · 주요 ETF 종목의 10월 이동평균 대비 현재가 위치를 분석하고,  
최근 7거래일 이격률 추이와 변곡점 종목을 자동으로 추출합니다.

## 구조

```
candle/
├── fetch_data.py       # 일봉 종가 + MA10M 수집 (증분, 당일 재실행 시 스킵)
├── analyze.py          # 10월 이평 분석 + 7일 이격률 + 변곡점 출력
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
