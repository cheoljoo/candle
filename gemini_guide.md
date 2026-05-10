# Gemini CLI Project Guide: Candle Chart Backtest System

이 문서는 `candle-new` 프로젝트의 구조, 로직 및 운영 방법을 설명합니다. 나중에 다른 Gemini 에이전트나 개발자가 프로젝트를 이어서 작업할 때 참고할 수 있도록 작성되었습니다.

## 1. 프로젝트 개요 (Overview)
본 프로젝트는 한국(KOSPI 200) 및 미국(S&P 500, ETF) 주식 데이터를 수집하고, 정해진 기술적 지표(특히 10개월 이동평균선)를 기반으로 다양한 백테스트 전략을 수행하며, 매일의 시뮬레이션 결과를 대시보드로 시각화하는 시스템입니다.

## 2. 디렉토리 구조 (Directory Structure)
```
candle-new/
├── .gemini/            # 프로젝트 관리 및 플랜
│   ├── GEMINI.md       # 프로젝트 기본 규칙 (시간 출력, uv 사용 등)
│   └── plan.md         # 초기 구현 계획서
├── data/               # 수집된 주식 데이터 (CSV)
│   ├── stocks_kr/      # 한국 종목 (KOSPI 200 + ETF)
│   ├── stocks_us/      # 미국 종목 (S&P 500 + ETF)
│   └── rank/           # 시가총액 순위 데이터 (추후 확장용)
├── backtest/           # 백테스트 전략별 구현체
│   ├── type1/          # 변곡점(Inflection Point) 기반 (MA10M 교차)
│   ├── type2/          # 추세 유지(Trend Maintenance) 기반
│   └── type3/          # 적립식(DCA) 기반
├── simulation/         # 일일 시뮬레이션 및 대시보드
│   ├── dashboard/      # 대시보드 웹 페이지 (HTML/CSS/JS)
│   ├── engine.py       # 시뮬레이션 실행 엔진
│   └── dashboard_data.json # 대시보드용 데이터 소스
├── fetch_data.py       # 데이터 수집 및 지표 계산 스크립트
├── backtest_compare.py # 백테스트 결과 비교 및 요약
├── gemini_guide.md     # 본 가이드 문서
└── pyproject.toml      # uv 패키지 관리 설정
```

## 3. 핵심 모듈 설명 (Core Modules)

### 3.1. 데이터 수집 (`fetch_data.py`)
- **수집 대상**: KOSPI 200(시총 상위 200), S&P 500, 지정된 한국/미국 ETF 리스트.
- **주요 지표**: OHLCV 외에 MA10D, MA50D, MA10M(10개월 이평선)을 계산합니다.
- **특수 컬럼**:
    - `MA10M_UPDOWN`: 종가가 MA10M보다 위면 `+`, 아래면 `-`.
    - `Inflection`: `MA10M_UPDOWN`이 변하는 시점(변곡점)을 Boolean으로 표시.
- **증분 업데이트**: 기존 파일이 있으면 마지막 날짜 이후의 데이터만 가져와서 합칩니다.

### 3.2. 백테스트 엔진 (`backtest/`)
- **Type 1**: MA10M 변곡점 매매.
    - `- → +` 전환 시 매수, `+ → -` 전환 시 매도.
- **Type 2**: 추세 확인 매매.
    - `plus_days` 연속 `+` 유지 시 매수, `minus_days` 연속 `-` 유지 시 매도.
- **Type 3**: 3개월 주기 적립식 매수 (DCA).

### 3.3. 비교 및 분석 (`backtest_compare.py`)
- 모든 백테스트 결과 CSV를 읽어 종목별/전략별 **ROI(수익률)**, **최종 자산**, **매매 횟수**를 집계합니다.
- `backtest_compare.csv` 파일로 전체 순위를 저장합니다.

### 3.4. 시뮬레이션 및 대시보드 (`simulation/`)
- `engine.py`는 매일 실행되어 현재 포트폴리오 상태를 업데이트하고 `dashboard_data.json`을 생성합니다.
- `dashboard/index.html`은 생성된 JSON 데이터를 읽어 시각적으로 보여줍니다. (Rule-base, AI, 수동 의사결정 그룹화 지원 구조)

## 4. 운영 및 실행 방법 (How to Run)

모든 실행은 `uv`를 사용합니다.

1. **데이터 업데이트**:
   ```bash
   uv run fetch_data.py
   ```
2. **백테스트 수행** (필요 시):
   ```bash
   uv run backtest/type1/type1_2.py
   # 등등...
   ```
3. **결과 비교**:
   ```bash
   uv run backtest_compare.py
   ```
4. **일일 시뮬레이션 실행**:
   ```bash
   uv run simulation/engine.py
   ```
5. **대시보드 확인**:
   `simulation/dashboard/index.html` 파일을 브라우저에서 엽니다.

## 5. 향후 확장 및 주의사항 (Notes for Future)
- **AI 의사결정**: `engine.py`에 LLM API(OpenAI/Gemini) 호출 로직을 추가하여 `AI` 그룹에 의사결정을 자동 할당할 수 있습니다.
- **수동 입력**: 대시보드에 HTML Form을 추가하고 `engine.py`에서 이를 처리하는 API(간이 Flask/FastAPI 등)를 연동하면 수동 입력 기능을 완성할 수 있습니다.
- **데이터 소스**: `FinanceDataReader`와 `yfinance`를 혼용하므로, API 변경 시 `fetch_data.py`의 정규화 로직 확인이 필요합니다.
- **시간 출력**: `.gemini/GEMINI.md` 규칙에 따라 모든 작업 시작 시 현재 시간을 출력해야 합니다.
