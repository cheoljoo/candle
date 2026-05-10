---
model: claude-opus-4-7
date: 2026-05-10 (2차)
source: req.md + claude-work.md
purpose: 구현 완료 상태 기준 현행화 — 계획(plan) + 실제 동작 구조
---

# Candle Backtest Program — 진행 가이드 (claude-opus-4-7)

> **2026-05-10 현재 Phase 1~6 전체 구현 완료.**
> 이 문서는 최초 계획(req.md 기반)을 실제 구현 결과로 업데이트한 **현행 아키텍처 레퍼런스**입니다.
> 변경 이력은 `claude-work.md` 를 참고하세요.

---

## 0. 결정된 사항 (Decision Points — 확정)

| # | 결정 항목 | 확정값 |
|---|----------|--------|
| Q1 | KR/US 분리 방식 | **단일 프로그램 + `--market kr/us/all` 옵션** |
| Q2 | 데이터 소스 | **yfinance 우선 (KR/US 공용), pykrx fallback (KR only)** ※변경 |
| Q3 | 저장 포맷 | **CSV only** |
| Q4 | type 번호 정합성 | **req.md type3 = 기존 type4 (적립식)** |
| Q5 | plus_days/minus_days 기본값 | **8/4** (config/strategies.yml) |
| Q6 | 적립식 시작일 | **from 날짜 + interval_days(90) 단위 누적** |
| Q7 | 종목 편출입 처리 | 현재 멤버십 필터 적용. 강제매도 미구현(향후) |
| Q8 | 시간대/실행시각 | **KR: 16:30 KST, US: 익일 06:00 KST** (runtime.yml cron) |
| Q9 | dashboard | **static HTML (Jinja2 + Tailwind + Alpine.js)** 1차 구현 완료 |
| Q10 | AI 모델 | **Claude Opus 4.7 API + prompt caching** |
| Q11 | 통화 환산 | **KRW/USD 분리, % 비교만** |
| Q12 | 수동 의사결정 | **CSV** (`output/simulate/manual_input.csv`) — DB 미사용 |

> **Q2 변경 이유**: pykrx가 KRX 인증(KRX_ID/KRX_PW) 없이 hang/노이즈가 심해 yfinance(.KS/.KQ)를 primary로 전환. pykrx는 yfinance에서 빈 결과가 나올 때만 fallback.

---

## 1. 현행 아키텍처

### 1.1 디렉터리 구조 (구현 완료 기준)

```
candle/
├── pyproject.toml               # uv 의존성: typer, pyyaml, pykrx, yfinance,
│                                #   jinja2, anthropic, FinanceDataReader, requests
├── Makefile                     # v2-* 타겟 + DEBUG 변수
├── config/
│   ├── universe.yml             # 그룹 정의 + ETF 고정 list + small_universe
│   ├── strategies.yml           # type별 파라미터, 초기자본(KRW/USD)
│   └── runtime.yml              # cron, 경로, log level, history_start, fetch timeout
├── src/candle/
│   ├── cli.py                   # typer 진입점 (모든 subcommand)
│   ├── config.py                # YAML loader
│   ├── io_report.py             # announce() · tprint() — 타임스탬프 포함 출력
│   ├── universe/
│   │   ├── build.py             # update() — KOSPI200/SP500/ETF 통합 갱신
│   │   ├── kospi200.py          # pykrx → FDR fallback
│   │   ├── sp500.py             # Wikipedia → FDR fallback
│   │   ├── etf.py               # ETF ticker resolve
│   │   └── _quiet.py            # quiet_pykrx() context manager (노이즈 차단)
│   ├── fetch/
│   │   ├── run.py               # _fetch_kr() 5단계 + _fetch_us_batch()
│   │   ├── kr.py                # yfinance(.KS→.KQ) 우선, pykrx fallback
│   │   └── us.py                # fetch_daily_batch(), fetch_fast_info(), fetch_dividends()
│   ├── analyze/
│   │   ├── run.py               # 증분 처리 (analyze_meta.csv 기반)
│   │   ├── indicators.py        # MA10D/50D/MA10M, MA10M_UPDOWN
│   │   ├── inflection.py        # 변곡점 (-→+/+→-)
│   │   └── ranking.py           # 그룹 내 시총 순위
│   ├── storage/
│   │   ├── paths.py             # 표준 경로 + list_backtest_periods/compare_periods
│   │   ├── csv_io.py            # atomic write, upsert_by_keys
│   │   └── incremental.py       # fetch_window(from_date, history_start 지원)
│   ├── backtest/
│   │   ├── base.py              # Portfolio (+ from_trades() classmethod)
│   │   ├── type1_1.py           # inflection 신호, 고정수량
│   │   ├── type1_2.py           # inflection 신호, 전액매수
│   │   ├── type2_1.py           # streak 신호, 고정수량 (_init_streak 포함)
│   │   ├── type2_2.py           # streak 신호, 전액매수
│   │   ├── type3.py             # 적립식 90일 주기
│   │   └── run.py               # 증분 처리 (_meta.csv 기반) + 진행률 출력
│   ├── compare/
│   │   └── run.py               # strategy_summary / per_ticker / best_strategy / volume
│   ├── simulate/
│   │   ├── engine.py            # rule + AI + manual → decisions.csv
│   │   ├── ai_advisor.py        # Claude Opus 4.7 + prompt caching
│   │   └── manual.py            # manual_input.csv 로드
│   └── dashboard/
│       ├── render.py            # Jinja2 렌더 · _load_docs() · _load_rank_snapshot()
│       └── templates/
│           ├── index.html · _nav.html · _type_legend.html
│           ├── group_returns.html · compare.html · decisions.html
│           └── docs.html        # 문서 뷰어 (marked.js + highlight.js)
├── data/                        # CSV 저장소 (gitignore)
│   ├── instruments.csv
│   ├── analyze_meta.csv         # ticker별 analyzed_from/to (증분 판단용)
│   ├── universe/
│   ├── daily/{KR|US}/{ticker}.csv
│   └── events/dividends.csv
└── output/
    ├── analyze/{date}/summary.csv
    ├── backtest/{label}/{type}/{ticker}.csv   # label = "full"|"5y"|"2010-2020"|...
    │                    /{type}/_all.csv
    │                    /{type}/_summary.csv
    │                    /_meta.csv            # 증분 판단용 (type,ticker,from,to)
    ├── compare/{label}/strategy_summary.csv
    │                  /per_ticker.csv
    │                  /best_strategy.csv
    │                  /evaluation_volume.csv
    ├── simulate/decisions.csv + trades.csv
    └── ai_cache/{date}/{ticker}.json
```

### 1.2 CLI 전체 옵션 (현행)

```bash
candle universe --market all [--small] [--debug]
candle fetch    --market all [--from DATE] [--workers 4] [--timeout 10] [--debug]
candle analyze  --market all [--refresh] [--debug]
candle backtest --market all [--from DATE] [--to DATE] [--label LABEL]
                             [--types type1_1,...] [--debug]
candle compare  --from DATE [--to DATE] [--label LABEL] [--debug]
candle simulate [--no-ai] [--debug]
candle dashboard [--out DIR] [--debug]
candle optimize-streak --market all
                       [--plus-min 4] [--plus-max 40] [--plus-step 2]
                       [--minus-min 4] [--minus-max 10] [--minus-step 2]
                       [--workers 4] [--top 30] [--output CSV경로]
                       [--from DATE] [--to DATE]
```

**주요 옵션 설명**

| 옵션 | 설명 |
|------|------|
| `fetch --from 2000-01-01` | 기존 파일 유무 관계없이 이 날짜부터 백필 |
| `fetch --workers 4` | 병렬 fetch worker 수 (기본 4) |
| `fetch --timeout 10` | 종목당 HTTP timeout 초 (기본 10) |
| `analyze --refresh` | meta 무시, 전체 행 강제 재계산 |
| `backtest --label 5y` | 출력 경로를 날짜가 아닌 고정 label 로 지정 |
| `optimize-streak --plus-step 2` | plus_days 탐색 간격 (기본 2씩 건너뜀) |
| `optimize-streak --minus-step 2` | minus_days 탐색 간격 (기본 2씩 건너뜀) |
| `DEBUG=--debug` | `make v2-all DEBUG=--debug` 로 전체 디버그 |

---

## 2. 데이터 모델 (CSV 파일 레이아웃)

> 모든 파일은 UTF-8, 헤더 첫 줄, ISO 날짜(`YYYY-MM-DD`).
> write 시 atomic(tmp → os.replace) + sort + dedup.

### 2.1 마스터

**`data/instruments.csv`**
```csv
ticker,name,market,group_name,currency,active
005930,삼성전자,KR,KOSPI200,KRW,1
AAPL,Apple Inc.,US,SP500,USD,1
```

**`data/universe/{kospi200,sp500}_membership.csv`**
```csv
ticker,from_date,to_date
005930,2010-01-01,
```

**`data/universe/etf_{kr,us}.csv`** — ETF 고정 리스트

### 2.2 일봉 + 지표

**`data/daily/{KR|US}/{ticker}.csv`**
```csv
date,open,high,low,close,volume,per,pbr,shares_out,market_cap,
ma10d,ma50d,ma10m,ma10m_updown,inflection,rank_in_group
```
- `ma10m_updown`: `+`/`-`
- `inflection`: 빈값 / `-→+` / `+→-` (종가 MA10M 교차일만)
- KR: PER/PBR/시총 일별 (pykrx) 또는 마지막 row 스냅샷 (yfinance fallback)
- US: PER/시총/발행주식 마지막 row 스냅샷 (yfinance fast_info)
- 신규 ticker: `history_start: "2000-01-01"` (runtime.yml) 부터 fetch

### 2.3 증분 meta

**`data/analyze_meta.csv`** — analyze 증분 판단
```csv
ticker,market,analyzed_from,analyzed_to
005930,KR,2000-01-04,2026-05-08
```

**`output/backtest/{label}/_meta.csv`** — backtest 증분 판단
```csv
type,ticker,backtest_from,backtest_to
type1_1,005930,2023-01-01,2026-05-08
```

### 2.4 Backtest 결과

**`output/backtest/{label}/{type}/{ticker}.csv`**
```csv
type,date,ticker,side,price,qty,amount,holding_qty,holding_value,cash,return_pct
type1_1,2024-03-04,005930,buy,72000,10,720000,10,720000,,
type1_1,2026-05-08,005930,mark_to_market,72500,0,0,10,725000,,0.69
```

> `{label}` = `"full"` (2000~) | `"5y"` (최근 5년) | `"2010-2020"` (고정 기간) | 없음(flat)

### 2.5 Compare 결과

**`output/compare/{label}/`**
- `strategy_summary.csv` — 전략×통화 합산 (총자산/수익률/매수·매도)
- `per_ticker.csv` — 종목 × 전략 수익률 pivot
- `best_strategy.csv` — 종목별 최고전략 + 매수일 시총순위
- `evaluation_volume.csv` — 평가일 거래량 panel

### 2.6 Simulate / Decisions

**`output/simulate/decisions.csv`**
```csv
decision_id,date,ticker,source,action,qty,price,reason,raw_json_path
```
- `source`: `rule:{type}` | `ai` | `manual`

**`output/simulate/trades.csv`** — D+1 시작가 체결 결과

---

## 3. 구현 완료 로드맵

### ✅ Phase 0 — 합의 & 베이스라인
- Q1~Q12 결정 완료
- pyproject.toml 의존성 정리
- CSV-only 아키텍처 확정

### ✅ Phase 1 — Universe & Fetch
- `universe/build.py`: KOSPI200(pykrx→FDR)/SP500(Wiki→FDR)/ETF 갱신
- `universe/_quiet.py`: pykrx 노이즈 차단 context manager
- `storage/{paths,csv_io,incremental}.py`: atomic write, 증분
- `fetch/kr.py`: yfinance(.KS→.KQ) 배치 우선, pykrx fallback
- `fetch/us.py`: `fetch_daily_batch()`, `fetch_fast_info()`
- `fetch/run.py`: `_fetch_kr()` 5단계 + `_fetch_us_batch()` + requests monkey-patch timeout + watchdog

**fetch 핵심 구조:**
```
_fetch_kr():
  Step 1: yfinance batch .KS (전체 KR 1회 호출)
  Step 2: .KQ retry (빈 ticker만)
  Step 3: fast_info thread pool (PER/시총)
  Step 4: pykrx fallback (여전히 빈 ticker만)
  Step 5: CSV upsert

_fetch_us_batch():
  Phase 1: (start,end) window 별 _us_batch_download_chunked()
           └ 80개씩 chunk × 3 병렬 yf.download (US_BATCH_CHUNK_SIZE=80, US_BATCH_PARALLEL=3)
  Phase 2: fast_info/dividends thread pool (idx/total 진행 번호 표시)
  Phase 3: CSV upsert
  → 각 Phase 소요시간 + 전체 summary 항상 출력 (--debug 불필요)
```

**SOX 제거**: `SOX` 는 PHLX Semiconductor 인덱스 (yfinance `^SOX`) 로 거래 ETF 아님. `SOXX` 가 동일 인덱스 ETF 로 등록돼 있어 `config/universe.yml` 및 `fetch_data.py` 에서 제거.

### ✅ Phase 2 — Analyze (증분)
- `indicators.py`: MA10D/50D/MA10M, MA10M_UPDOWN
- `inflection.py`: -→+ / +→- 변곡점
- `ranking.py`: 그룹 내 시총 순위
- `run.py`: **`analyze_meta.csv` 기반 증분** — from/to 비교 → skip/부분계산/전체재계산

**analyze 증분 모드:**

| 조건 | 처리 | 효과 |
|------|------|------|
| from/to 동일 | skip | ~0s |
| to 만 늘어남 | context(220행)+새 row만 계산 | ~30배 빠름 |
| from 당겨짐 | new_start=0 전체 재계산 | - |
| `--refresh` | 강제 전체 재계산 | 백필 직후 1회 |

### ✅ Phase 3 — Backtest (증분)
- `base.py`: Portfolio + `from_trades()` 상태 복원
- `type1_1/2`, `type2_1/2`, `type3`: `portfolio=` 파라미터 (resume 지원)
- `type2_1.py`: `_init_streak()` — resume 시 streak 상태 lookback으로 초기화
- `run.py`: **`_meta.csv` 기반 증분** + 진행률 출력 (항상)

**backtest 증분 모드:**

| 조건 | 처리 | 예: KR 208종목 |
|------|------|----------------|
| from/to 동일 | skip (기존 CSV 읽기만) | 9.2초 |
| to 늘어남 | Portfolio 복원 + 새 구간 append | 수초 |
| from 달라짐 / 첫 실행 | full 재계산 | 71.7초 |

**backtest 출력 경로 (label 기반):**
```
output/backtest/full/     ← --label full (2000-01-01~, 매일 갱신)
output/backtest/5y/       ← --label 5y (5년전~, 매일 갱신)
output/backtest/2010-2020/ ← --label 2010-2020 (고정 기간)
```

### ✅ Optimize — plus_days / minus_days 그리드 서치 (별도 실행)

> `v2-all` 에 미포함. `make v2-optimize` 로 수동 실행.

- **목적**: type2_2 계열(N일 연속 상승 → 전액 매수 / M일 연속 하락 → 전량 매도)의 최적 `plus_days` / `minus_days` 탐색.
- **구현**: `src/candle/optimize/streak_grid.py`
- **알고리즘 (3단계)**:
  1. **streak 사전 계산** (ticker당 1회): 각 일봉의 `ma10m_updown` 연속 방향(streak_sign)·연속 일수(streak_len) 산출. Thread pool으로 병렬 로딩.
  2. **이벤트 추출**: `streak_len==P` 인 날 = "P일째 첫 매수 신호", `streak_len==M` = "M일째 첫 매도 신호". 미리 분류해 (P, M) 조합 반복 비용 최소화.
  3. **그리드 서치**: 모든 (P, M) 조합 × 전 ticker 시뮬레이션. 결과 = `(plus_days, minus_days, avg_return, median_return, n_positive, n_total, hit_rate)`.
- **기본 탐색 범위**: `plus 4~40 step 2` (19가지) × `minus 4~10 step 2` (4가지) = **76 조합**.
- **출력**: 상위 30개 터미널 출력 + `output/optimize/streak_grid.csv` 전체 저장.

```
make v2-optimize            # 기본 범위 실행 (76 조합)
make v2-optimize DEBUG=--debug  # 상세 출력 포함
```

**결과 CSV 컬럼:**
```
plus_days, minus_days, avg_return, median_return, n_positive, n_total, hit_rate
```
- `avg_return`: 전 ticker 평균 수익률(%). 이 값으로 정렬.
- `hit_rate`: 수익 플러스 비율(%).

**최적 파라미터 적용 방법** — `config/strategies.yml` 에서 type2_1b/type2_2b 값 수정:
```yaml
type2_1b:
  plus_days: <최적값>
  minus_days: <최적값>
type2_2b:
  plus_days: <최적값>
  minus_days: <최적값>
```

### ✅ Phase 4 — Compare
- `compare/run.py`: strategy_summary / per_ticker / best_strategy / evaluation_volume
- **period 연동**: `--label` 과 동일하게 지정해야 같은 경로 읽음
- `output/compare/{label}/` 에 결과 저장
- **strategy_summary 구조** (2026-05-10 개편): `(type, group_name)` 별 행 + `TOTAL (KRW/USD)` 행
  - 컬럼: `strategy, group, currency, tickers, 총자산, 현금, 보유주식수, 초기자본, 손익, 수익률, 매수횟수, 매도횟수`
  - `group` 값: `KOSPI200` / `SP500` / `ETF_KR` / `ETF_US` / `TOTAL (KRW)` / `TOTAL (USD)`

### ✅ Phase 5 — Simulate + Dashboard
- `simulate/engine.py`: rule×5type + AI + manual → decisions.csv
- `simulate/ai_advisor.py`: Claude Opus 4.7 + prompt caching (system+종목메타 cached, 오늘 신호 uncached)
- `dashboard/render.py`:
  - `_load_compare_all()`: 모든 label 디렉터리 스캔 → {period: rows}
  - `_load_rank_snapshot()`: `data/{kospi,sp500}_daily_rank.csv` 의 최신 row → ticker→rank 매핑 (674개). 데이터 없으면 빈 dict.
  - `_build_period_table()`: backtest label × ticker → best_return 테이블. `rank_in_group` 포함. 그룹별로 분리.
  - `_load_inflections()`: 오늘 변곡점 발생 종목 (전체 ticker 스캔, ~30초)
  - `_load_decisions()`: type3(적립식) 제외, 종목명/그룹명 추가, type별 건수 계산. `rank_map` 전달 받아 비ETF 그룹에 `rank_in_group` 포함.
  - `_load_docs()`: `claude/` 디렉터리 `.md` 파일 읽기. `_DOC_LABELS`(친화적 이름) + `_DOC_ORDER`(표시 순서) 로 정렬.
  - `io_report.tprint()`: 모든 일반 출력에 `2026-05-10 19:07:07,928` 형식 타임스탬프 자동 부여.
  - 진행 출력: 각 단계 `[dashboard] ... 완료 (Xs)` 형식
- **8개 파일** (2026-05-10 개선):

| 파일 | 내용 |
|------|------|
| `index.html` | KPI 카드 + 페이지 링크 + 변곡점 |
| `kospi200.html` | KOSPI200 종목 × 기간 수익률 (RANK 포함) |
| `sp500.html` | S&P500 종목 × 기간 수익률 (RANK 포함) |
| `etf_kr.html` | ETF_KR 종목 × 기간 수익률 |
| `etf_us.html` | ETF_US 종목 × 기간 수익률 |
| `compare.html` | 전략×그룹별 요약 (period 탭, TOTAL 행 포함) |
| `decisions.html` | 오늘의 의사결정 (RANK 컬럼, rule/AI/manual + type 필터) |
| `docs.html` | 문서 뷰어 (claude/ .md 파일, Markdown/Raw 토글) |

- **공통 템플릿**:
  - `_nav.html`: 모든 페이지 공통 내비게이션
  - `_type_legend.html`: 전략 코드 설명 범례 (`<details>` 접기)
  - `group_returns.html`: 그룹별 수익률 테이블 (공통)
- **decisions 페이지 기능**:
  - 탭: Rule / AI / Manual (탭 전환 시 type_filter 리셋)
  - Rule 탭 선택 시 type 필터 버튼 표시: `전체 | type1_1(N) | type1_2(N) | type2_1(N) | type2_2(N)`
  - type3 (적립식) rule 신호는 표시에서 제외
  - 컬럼: 그룹, **RANK**(비ETF만), Ticker, 종목명, 전략(코드+설명), Action, Qty, Price, Reason
- **docs 페이지 기능**:
  - 왼쪽 사이드바: claude/ 내 .md 목록 선택 (Alpine.js)
  - 오른쪽: **Markdown**(marked.js + highlight.js) / **Raw** 토글
  - 표시 순서: README → 아키텍처 가이드 → 요구사항 → 작업 이력 → Gemini 분석

### ✅ Phase 6 — 자동화
- `Makefile` `v2-all` 전체 파이프라인
- `DEBUG` 변수로 debug 모드 제어: `make v2-all DEBUG=--debug`
- cron 설정: runtime.yml 참고

---

## 4. Makefile 운영 가이드

### 4.1 주요 타겟 구조

```
v2-all: v2-universe v2-fetch-full v2-analyze v2-backtest v2-simulate v2-dashboard

v2-backtest (병렬):
  ├── v2-backtest-compare-full   → backtest --label full + compare --label full
  ├── v2-backtest-compare-5y     → backtest --label 5y  + compare --label 5y
  └── v2-backtest-compare-2010-2020 → backtest/compare --label 2010-2020
```

### 4.2 자주 쓰는 명령

```bash
# 파라미터 최적화 (v2-all 과 별개 — 필요 시 수동 실행)
make v2-optimize                # plus 4~40 step2, minus 4~10 step2, 76 조합
make v2-optimize DEBUG=--debug  # 상세 출력

# 일별 운영 (증분)
make v2-fetch       # 오늘치만 fetch
make v2-analyze     # 새 row 자동 감지 + 계산
make v2-backtest    # skip=대부분, 신규 row만 resume
make v2-dashboard   # HTML 재생성

# 최초 전체 백필 (1회)
make v2-fetch-full              # 2000-01-01부터 전체 fetch
make v2-analyze-refresh         # 전체 재분석 (--refresh)
make v2-backtest-compare-full   # 2000년 이후 전체 backtest+compare

# 새 기간 추가 시
# 1) v2-backtest-compare-<label> 타겟 정의
# 2) v2-backtest 의 $(MAKE) -j 줄에 추가

# 디버그
make v2-all DEBUG=--debug
make v2-fetch DEBUG=--debug
```

### 4.3 단독 실행 (특수 케이스)

```bash
# 특정 label/기간만
uv run candle backtest --from 2010-01-01 --to 2021-01-01 --label 2010-2020 --market all
uv run candle compare  --from 2010-01-01 --to 2021-01-01 --label 2010-2020

# KRX 인증 설정 (pykrx 정확도 향상)
# ~/.bashrc 에 KRX_ID, KRX_PW 추가 후:
uv run candle universe --market all
```

---

## 5. 의사결정·AI 설계

### 5.1 룰베이스 (backtest types 재사용)

매일 각 종목에 대해 5개 type 신호 평가 → `decisions.csv` (`source='rule:type1_1'` 등).

### 5.2 AI Advisor — Claude Opus 4.7

**입력**: 종목 메타 + 최근 60거래일 일봉/MA/UPDOWN/inflection + PER/PBR + 시총순위 + 거래량/20일평균 + 배당이벤트 + 룰 신호 요약

**Prompt caching**: system 프롬프트 + 종목 메타·60일 시세 → `cache_control: ephemeral`. 오늘 룰 신호 + 질문 → uncached.

**출력 (JSON schema 강제)**:
```json
{
  "ticker": "005930",
  "action": "buy|sell|hold",
  "confidence": 0.0,
  "reasons_buy": [...],
  "reasons_sell": [...],
  "key_signals": {"ma10m_updown": "+", "inflection": "-→+", "rank_in_group": 7},
  "risks": [...]
}
```

**비용 통제**: `runtime.yml.ai.daily_limit` (기본 50). `ANTHROPIC_API_KEY` 없으면 자동 skip.

### 5.3 수동 입력

`output/simulate/manual_input.csv` 를 사용자가 직접 편집 후 `candle simulate` 재실행.

---

## 6. 대시보드 현행 구조

### 6.1 스택
- **Tailwind CSS CDN** + **Alpine.js** (x-show, x-data, @click)
- Jinja2 템플릿 렌더 → `dashboard_site/index.html`

### 6.2 섹션 구성

```
index.html (홈)
  KPI 카드 (Tickers / Decisions today / Best strategy)
  페이지 링크 카드 6개
  변곡점 발생 종목 (Action Required)

kospi200.html / sp500.html / etf_kr.html / etf_us.html
  전략 코드 설명 범례 (접기 가능)
  종목 × 기간 수익률 테이블
    행=ticker, 열=backtest label, 셀=최고전략 수익률(%)
    RANK 컬럼: KOSPI200/SP500 만 표시 (data/{kospi,sp500}_daily_rank.csv 기준)
               ETF_KR/ETF_US 는 RANK 컬럼 미표시
    ▶ 종목 클릭 → 기간 × 전략별 상세 수익률 펼침

compare.html
  전략 코드 설명 범례
  전략별 요약: 탭=compare label (full/5y/2010-2020 등)

decisions.html
  전략 코드 설명 범례
  오늘의 의사결정
    탭=Rule | AI | Manual (탭 전환 시 type 필터 리셋)
    Rule 탭 선택 시 type 필터: 전체 | type1_1 | type1_2 | type2_1 | type2_2
    컬럼: 그룹, Ticker, 종목명, 전략(코드+설명), Action, Qty, Price, Reason
    type3(적립식) rule은 표시 제외

4. 변곡점 발생 종목 (Action Required)
   컬럼: ticker, group, inflection, close, ma10m, per, pbr, rank
```

### 6.3 사이드 JSON 산출물

```
dashboard_site/data/
├── compare.json         # {label: [strategy rows]}
├── decisions.json       # 오늘 결정
├── inflections.json     # 오늘 변곡점
└── period_table.json    # {periods: [...], rows: [{ticker, period_returns}]}
```

---

## 7. 리스크 & 운영 주의사항

| 리스크 | 현황 & 대응 |
|--------|------------|
| pykrx hang / KRX 인증 | yfinance primary로 전환. pykrx는 fallback only. KRX 인증 시 더 정확한 데이터 가능 |
| yfinance rate limit | chunk 병렬(80×3) + timeout(기본 10초) + requests monkey-patch로 hang 방지. batch 취소 시간 145s → chunk 분산으로 꼬리 latency 완화 |
| fetch 시작일 | `history_start: "2000-01-01"` (runtime.yml). 신규 ticker는 자동으로 2000년부터 |
| 백필 후 analyze | `make v2-analyze-refresh` 1회 실행 필요 (--refresh 플래그) |
| backtest 기간 추가 | `v2-backtest-compare-<label>` Makefile 타겟 추가 + `-j` 줄에 포함 |
| portfolio 상태 복원 | `Portfolio.from_trades()` — avg_cost는 마지막 매도 이후 매수 가중평균 |
| type2 streak 재개 | `_init_streak()` — resume start 직전 lookback으로 streak 상태 초기화 |
| AI 비용 폭주 | `ai.daily_limit` + prompt cache + ANTHROPIC_API_KEY 없으면 skip |
| 환율 비교 | KRW/USD 분리. cross 비교는 % 만 허용 |
| mark_to_market | backtest 종료일 보유분 종가 평가 (실제 매도 아님) |
| 편출입 강제매도 | 현재 미구현 — 향후 `membership.to_date` 기반 자동 매도 필요 |

---

## 8. 향후 작업 후보

| 항목 | 우선순위 | 메모 |
|------|---------|------|
| **nginx /stock_candle 서비스** | 높 | `/tmp/candle_nginx.conf` 작성 완료. 일반 터미널에서 `sudo cp /tmp/candle_nginx.conf /etc/nginx/conf.d/candle.conf && sudo nginx -t && sudo systemctl reload nginx` 실행 필요 |
| 종목 편출입 강제 매도 | 중 | `membership.to_date` D-1 종가 매도 |
| dotenv 자동 로드 | 하 | `cli.py` 에 `load_dotenv()` 추가 → KRX_ID/PW `.env` 자동 인식 |
| analyze ranking 증분 | 중 | 현재 그룹 전체 재계산 → 신규 date만 처리로 최적화 |
| dashboard inflection 스캔 속도 | 중 | 변곡점 lookup이 30초+ (719 ticker × CSV 전체 읽기) → analyze_meta 기반 최적화 가능 |
| dashboard FastAPI 2차 | 낮 | 수동 입력 폼 UI (현재는 CSV 직접 편집) |
| v2 market_cap 저장 수정 | 중 | yfinance fast_info 가 현재 None 반환 → US/KR daily CSV 의 market_cap/rank_in_group 비어 있음. dashboard RANK 는 legacy `data/{kospi,sp500}_daily_rank.csv` 로 workaround 중 |
| 백테스트 편입 전 종목 필터 | 중 | 매수 시점에 KOSPI200/SP500 구성원인 종목만 매수 |
| gmail 리포트 | 하 | 기존 `gmail_sender.py` 재연결 |

---

부록: 이 가이드는 `req.md §1.1.1~§1.1.4` + `claude-work.md` 모든 구현 항목을 반영합니다. 마지막 업데이트 2026-05-10 (2차).
