---
model: claude-opus-4-7
date: 2026-05-20 (19차)
source: req.md + claude-work.md
purpose: 구현 완료 상태 기준 현행화 — 계획(plan) + 실제 동작 구조
---

# Candle Backtest Program — 진행 가이드 (claude-opus-4-7)

> **2026-05-20 현재 Phase 1~6 전체 구현 완료. gmail-etf 기능 추가. 전체 4개 그룹 종목별 per-ticker 최적화 지원. 시장 시그널(KR+US) 대시보드 추가. Makefile KR/US 분리 파이프라인. 리스크 지표(MDD·승률·평균보유일) + 거래 이력 상세 페이지 + 미국 시장 시그널(VIX·수익률 곡선) + KOSPI200 외국인/기관 매매 추가. Worker CPU×1/2 기본값. enabled_types ON/OFF 뱃지. market calendar 수집. decisions 신호 확인일(마지막 거래일) 표시. ticker str 강제화. market_calendar 기반 비거래일 decisions 검증 가드. 변곡점 테이블 날짜 컬럼 추가. decisions 백테스트 action 비교 컬럼 + enabled_types 필터. decisions 직전날짜 prev_action 비교(신호변화 감지, buy=빨강/sell=파랑). 거래이력 #TICKER:type_name URL hash 지원. backtest Buy-Sell 수익률(사이클별 수익률) 컬럼 추가 — ticker_trades.html 이익=빨강/손실=파랑. 거래이력 Chart.js 차트(종가·10월MA·매수↑/매도↓마커·보유수량) + 전략 설명·ON/OFF 뱃지 + 1년 구간 + ON 전략만 차트 표시. backtest 기간 config화(config/periods.yml) + candle backtest-all 커맨드(병렬 ProcessPoolExecutor, workers 설정 3단계 우선순위). analyze ValueError 버그 수정(_STRING_COLS 하드코딩). 대시보드 테이블 전체 컬럼 정렬(data-sortable + _nav.html 공유 JS). compare 전략명 항상 표시 + strategy_summary.csv KR/US 병합 저장. instruments.csv 미등록 ticker 필터링(UNKNOWN 그룹 제거). compare 상위 10% 섹션 전면 개편(2단 탭 기간×전략 + 2×2 그룹 그리드 + 매수/매도/보유일/RANK 컬럼). 거래이력 차트 평가액+현금(주식수×종가+현금) equity 라인 추가 + 차트 축 색상(yPrice=slate/yQty=green/yEquity=indigo). type0_2(매수후보유 벤치마크) + type2_2_opt(종목별 최적화 파라미터 type2_2) 신규 추가. 주식수 3개 개념 분리 — 처음주식수(첫BUY qty)·최종주식수(마지막BUY holding_qty)·마지막가진주식수(SELL 후 실제보유) + compare/거래이력 표시 개선. compare 전략별 요약 Top 10%/전체 분리 — compare.html은 수익률 상위 10% 표시, compare_full.html(신규)은 전체 종목 내림차순 표시.**
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
│   ├── runtime.yml              # cron, 경로, log level, history_start, fetch timeout
│   └── recipients.yml           # 메일 수신자 목록 (owner, recipients, dashboard_url)
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
│   │   ├── us.py                # fetch_daily_batch(), fetch_fast_info(), fetch_dividends()
│   │   └── market_signals.py    # KRX 프로그램비차익 + 투자자별매매 + KOSPI지수 증분 수집
│   │                            # check_signals(): 역사적 퍼센타일 경보 + Pearson 상관계수
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
│       ├── render.py            # Jinja2 렌더 · _load_docs() · _load_rank_snapshot() · name_map(전체 종목)
│       │                        # uk_fmt 필터(억→조 변환) · _load_market_signals(KOSPI 연동)
│       └── templates/
│           ├── index.html · _nav.html · _type_legend.html
│           ├── group_returns.html · compare.html · decisions.html
│           ├── optimize.html    # 모든 그룹 탭에서 종목별 히트맵+조합 표시 (isPerTickerGroup)
│           ├── market_signals.html  # 시장 시그널 전용 페이지 (SVG 차트+KOSPI꺾은선, 상관관계 게이지, 용어 설명)
│           └── docs.html        # 문서 뷰어 (marked.js + highlight.js)
├── data/                        # CSV 저장소 (gitignore)
│   ├── instruments.csv
│   ├── analyze_meta.csv         # ticker별 analyzed_from/to (증분 판단용)
│   ├── market/
│   │   ├── program_trading.csv  # KRX 프로그램 비차익 순매수 (date, 비차익_순매수)
│   │   ├── investor_trading.csv # 투자자별 매매 (date, 금융투자, ...)
│   │   └── kospi_index.csv      # KOSPI 일별 종가 (date, close)
│   ├── universe/
│   ├── daily/{KR|US}/{ticker}.csv
│   └── events/dividends.csv
└── output/
    ├── analyze/{date}/summary.csv
    ├── backtest/{label}/{type}/{ticker}.csv   # label = "full"|"5y"|"2010-2020"|...
    │                    /{type}/_all.csv
    │                    /{type}/_summary.csv
    │                    /_meta.csv            # 증분 판단용 (type,ticker,from,to)
    │                    /type2_2_opt/_opt_params.json  # 종목별 사용 파라미터 (변경 감지)
    ├── compare/{label}/strategy_summary.csv
    │                  /per_ticker.csv
    │                  /best_strategy.csv
    │                  /evaluation_volume.csv
    ├── simulate/decisions.csv + trades.csv
    ├── ai_cache/{date}/{ticker}.json
    └── optimize/
        ├── streak_grid_{all|KOSPI200|SP500|ETF_KR|ETF_US}.csv
        ├── streak_grid_meta.json
        └── per_ticker/
            ├── KOSPI200/{ticker}.csv + _summary.json
            ├── SP500/{ticker}.csv + _summary.json
            ├── ETF_KR/{ticker}.csv + _summary.json
            └── ETF_US/{ticker}.csv + _summary.json
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
candle market-signals [--today YYYY-MM-DD] [--quiet]
candle optimize-streak --market all
                       [--all-groups]              # 전체+4그룹 5개 파일 동시 생성
                       [--output-dir output/optimize/]
                       [--plus-min 4] [--plus-max 40] [--plus-step 2]
                       [--minus-min 4] [--minus-max 10] [--minus-step 2]
                       [--workers 4] [--top 30]
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
- `type0_2.py`: **신규** — 첫 거래일 KRW/USD 전액 매수, 이후 매도 없음, 종가만 추적 (벤치마크)
- `type1_1/2`, `type2_1/2`, `type3`: `portfolio=` 파라미터 (resume 지원)
- `type2_1.py`: `_init_streak()` — resume 시 streak 상태 lookback으로 초기화
- `type2_2_opt.py`: **신규** — type2_2 동일 로직, 종목별 최적화 파라미터 사용 (`type_name='type2_2_opt'`)
- `run.py`: **`_meta.csv` 기반 증분** + 진행률 출력 (항상)
  - `type2_2_opt` 전용: `_opt_params.json` 저장/로드, 파라미터 변경 시 강제 full 재계산

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

### ✅ Optimize — type2_1b/type2_2b plus_days/minus_days 그리드 서치 (별도 실행)

> `v2-all` 에 미포함. `make v2-optimize` 로 수동 실행.

- **목적**: type2_1b/type2_2b(연속일수 신호) 전략의 최적 `plus_days`/`minus_days` 탐색.
- **구현**: `src/candle/optimize/streak_grid.py`
- **알고리즘 (3단계)**:
  1. **streak 사전 계산** (ticker당 1회, thread pool): 각 일봉의 `ma10m_updown` 연속 방향/일수 산출.
  2. **이벤트 추출**: `streak_len==P` 인 날 = "P일째 첫 매수 신호". (P,M) 조합 반복 비용 최소화.
  3. **그리드 서치**: 76 조합 × 전 ticker 시뮬레이션.
- **기본 탐색 범위**: `plus 4~40 step 2` (19가지) × `minus 4~10 step 2` (4가지) = **76 조합**.
- **`--all-groups`**: 전체(all) + KOSPI200/SP500/ETF_KR/ETF_US 5개 그룹 **동시 실행** (ticker 1회 로딩).
  - 출력: `output/optimize/streak_grid_{all|KOSPI200|SP500|ETF_KR|ETF_US}.csv`
  - 메타: `output/optimize/streak_grid_meta.json` (실행일시, 데이터 구간, 파라미터 범위)
- **전체 4그룹 per-ticker**: KOSPI200/SP500/ETF_KR/ETF_US 모든 그룹에 **종목별 독립 grid search** 적용.
  - 4개 그룹을 `ThreadPoolExecutor(max_workers=4)`로 **동시** 처리.
  - 각 그룹 내 종목별 `_grid_search`도 `ThreadPoolExecutor`로 병렬 처리 (`workers` 파라미터).
  - 출력: `output/optimize/per_ticker/{KOSPI200|SP500|ETF_KR|ETF_US}/{ticker}.csv` + `_summary.json`

**type2_2_opt 활용** — optimize 결과를 backtest에 자동 반영:
```
# 1) 최적화 실행 (~3개월에 1회 권장)
make v2-optimize            # output/optimize/per_ticker/{group}/_summary.json 생성

# 2) type2_2_opt backtest 실행 — 종목별 최적 (plus_days, minus_days) 자동 로드
uv run candle backtest --types type2_2_opt

# 3) 파라미터가 변경되지 않으면 증분 처리, 변경 시 해당 종목만 전체 재계산
#    사용된 파라미터는 output/backtest/{label}/type2_2_opt/_opt_params.json 저장
```

`config/strategies.yml` fallback 설정:
```yaml
type2_2_opt:
  fallback_plus_days: 33   # optimize 결과 없는 종목에 적용
  fallback_minus_days: 5
```

```
make v2-optimize            # --all-groups: 5개 그룹 결과 동시 생성
make v2-optimize DEBUG=--debug
```

**결과 CSV 컬럼:**
```
plus_days, minus_days, avg_return, median_return, n_positive, n_total, hit_rate
```

**type2_1b/type2_2b 최적 파라미터 적용** — `config/strategies.yml` 수정 후 `make v2-backtest`:
```yaml
type2_1b:
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
  - `_load_decisions()`: type3(적립식) 제외, 종목명/그룹명 추가, type별 건수 계산. `rank_map` 전달 받아 비ETF 그룹에 `rank_in_group` 포함. **`on_date`에 데이터 없으면 CSV 내 최신 날짜로 자동 fallback** (주말/공휴일 대응). 반환값 4-tuple: `(rows, counts, type_counts, actual_date)`.
  - `_load_docs()`: `claude/` 디렉터리 `.md` 파일 읽기. `_DOC_LABELS`(친화적 이름) + `_DOC_ORDER`(표시 순서) 로 정렬.
  - `io_report.tprint()`: 모든 일반 출력에 `2026-05-10 19:07:07,928` 형식 타임스탬프 자동 부여.
  - 진행 출력: 각 단계 `[dashboard] ... 완료 (Xs)` 형식
- **8개 파일** (2026-05-10 개선, 2026-05-11 optimize 확장):

| 파일 | 내용 |
|------|------|
| `index.html` | KPI 카드 + 페이지 링크 + 변곡점 |
| `kospi200.html` | KOSPI200 종목 × 기간 수익률 (RANK 포함) |
| `sp500.html` | S&P500 종목 × 기간 수익률 (RANK 포함) |
| `etf_kr.html` | ETF_KR 종목 × 기간 수익률 |
| `etf_us.html` | ETF_US 종목 × 기간 수익률 |
| `compare.html` | 전략×그룹별 요약 (period 탭, TOTAL 행 포함) |
| `decisions.html` | 오늘의 의사결정 (RANK 컬럼, rule/AI/manual + type 필터) |
| `docs.html` | 문서 뷰어 (claude/ *.md 자동 수집, Markdown/Raw 토글) |
| `optimize.html` | type2 파라미터 최적화 결과 (그룹 탭 + 히트맵 + 실행 메타 + ETF 종목별) |

- **공통 템플릿**: `_nav.html` · `_type_legend.html` · `group_returns.html` · `_download.html`
- **favicon**: 모든 페이지 🕯️ SVG data URI inline
- **decisions 페이지**: RANK 컬럼(비ETF), Rule/AI/Manual 탭, type 필터, CSV 다운로드
- **docs 페이지**:
  - `claude/*.md` 파일을 **자동 수집** (새 파일 추가 → 코드 수정 없이 자동 표시)
  - `_DOC_ORDER` 에 있는 파일은 지정 순서, 없는 파일은 알파벳 순 자동 추가
  - 현재 파일: README · 아키텍처 가이드 · 요구사항 · 작업 이력 · 메시지/노트 · Gemini 분석
  - Markdown 렌더링(marked.js + highlight.js) / Raw 토글
- **optimize 페이지**:
  - type2_1b/type2_2b 전략 설명 + 파라미터 적용 가이드
  - 그룹 탭: 전체(718종목) / KOSPI200 / SP500 / ETF_KR / ETF_US
  - 실행 메타 카드: 실행일시 · 데이터 구간 · 종목수 · 조합수
  - 히트맵 (plus_days × minus_days, 색상으로 avg_return 표시)
  - **ETF_KR/ETF_US 탭 선택 시 종목별 섹션 추가 표시**:
    - 전체 종목 요약 테이블 (ticker, 이름, 최적 plus/minus, avg_return, hit_rate)
    - 종목 클릭 → 개별 히트맵 + 전체 조합 결과 테이블 (정렬·CSV 다운로드)
    - "← 목록으로" 버튼으로 복귀. 그룹 탭 전환 시 선택 ticker 초기화
- **CSV 다운로드** (`_download.html`): compare / decisions / group_returns / optimize 모두 지원

### ✅ Phase 6 — 자동화
- `Makefile` `v2-all` 전체 파이프라인
- `DEBUG` 변수로 debug 모드 제어: `make v2-all DEBUG=--debug`
- cron 설정: runtime.yml 참고

---

## 4. Makefile 운영 가이드

### 4.1 주요 타겟 구조

```
v2-all:    v2-universe v2-fetch-full v2-analyze v2-backtest v2-simulate v2-dashboard
v2-all-kr: v2-gmail-etf v2-fetch-kr v2-analyze-kr v2-backtest-kr v2-simulate v2-market-signals v2-dashboard v2-sendmail
v2-all-us: v2-fetch-us v2-analyze-us v2-backtest-us v2-simulate v2-dashboard v2-sendmail

v2-backtest (병렬, --market all):
  ├── v2-backtest-compare-full         → backtest --market all --label full  + compare
  ├── v2-backtest-compare-5y           → backtest --market all --label 5y    + compare
  ├── v2-backtest-compare-2010-2020    → backtest --market all (고정 기간)
  └── v2-backtest-compare-2000-2015    → backtest --market all (고정 기간)

v2-backtest-kr (병렬, --market kr):
  ├── v2-backtest-compare-full-kr      → backtest --market kr --label full   + compare
  └── v2-backtest-compare-5y-kr        → backtest --market kr --label 5y     + compare

v2-backtest-us (병렬, --market us):
  ├── v2-backtest-compare-full-us      → backtest --market us --label full   + compare
  └── v2-backtest-compare-5y-us        → backtest --market us --label 5y     + compare
```

### 4.2 자주 쓰는 명령

```bash
# ── 시장별 분리 파이프라인 (일별 운영 권장) ──
./candle.sh kr     # 한국장 종료 후 ~16:00 KST 실행 (v2-all-kr)
./candle.sh us     # 미국장 종료 후 ~09:00 KST 실행 (v2-all-us)

make v2-all-kr SENDMAIL=YES     # KR 파이프라인 + 메일 발송
make v2-all-us SENDMAIL=YES     # US 파이프라인 + 메일 발송

# ── 전체 파이프라인 (수동 or 초기) ──
make v2-all                     # 전체 (universe→fetch-full→analyze→backtest→simulate→dashboard)
make v2-all SENDMAIL=YES        # 전체 + 메일

# ── 파라미터 최적화 (v2-all 과 별개 — 필요 시 수동 실행) ──
make v2-optimize                # plus 4~40 step2, minus 4~10 step2, 76 조합
make v2-optimize DEBUG=--debug  # 상세 출력

# ── 개별 단계 수동 실행 ──
make v2-fetch-kr    # KR만 증분 fetch
make v2-fetch-us    # US만 증분 fetch
make v2-analyze-kr  # KR만 분석
make v2-analyze-us  # US만 분석
make v2-backtest-kr # KR만 backtest (full+5y 병렬)
make v2-backtest-us # US만 backtest (full+5y 병렬)
make v2-dashboard   # HTML 재생성

# ── 최초 전체 백필 (1회) ──
make v2-fetch-full              # 2000-01-01부터 전체 fetch
make v2-analyze-refresh         # 전체 재분석 (--refresh)
make v2-backtest-compare-full   # 2000년 이후 전체 backtest+compare

# ── 디버그 ──
make v2-all DEBUG=--debug
make v2-all-kr DEBUG=--debug
```

### 4.3 candle.sh 사용법

```bash
./candle.sh        # v2-all  (기존 동작 유지)
./candle.sh kr     # v2-all-kr  (한국장 종료 후 ~16:00 KST)
./candle.sh us     # v2-all-us  (미국장 종료 후 ~09:00 KST)
```

로그 파일:
- `candle-v2.log` / `candle-v2-kr.log` / `candle-v2-us.log` (실행 중 실시간)
- `candle-v2-YYYY_MM_DD.log` / `candle-v2-kr-YYYY_MM_DD.log` / `candle-v2-us-YYYY_MM_DD.log` (날짜별 백업)

crontab 설정 예시:
```
0 16 * * 1-5  /home/cheoljoo/code/candle/candle.sh kr >> /tmp/candle-kr-cron.log 2>&1
0  9 * * 2-6  /home/cheoljoo/code/candle/candle.sh us >> /tmp/candle-us-cron.log 2>&1
```

### 4.4 단독 실행 (특수 케이스)

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

### 5.4 메일 발송 — `gmail_sender.py`

**설정** : `config/recipients.yml`
```yaml
owner: cheoljoo@gmail.com
dashboard_url: "http://psncs.iptime.org/stock_candle"
recipients:
  - email: cheoljoo.lee@lge.com
  ...  # 11명
```

**발송 방식** : 각 수신자에게 **개별 To: (1인 1메일)** — 추후 개인별 맞춤 내용 대비

> **중복 제거**: `owner` + `recipients` 를 합친 후 순서를 유지하며 중복 이메일을 제거하여 발송.

**주요 옵션**:
| 옵션 | 설명 |
|------|------|
| `--subject TEXT` | 메일 제목 |
| `--decisions-json PATH` | decisions.json 기반 본문 자동 생성 (BUY/SELL 요약 + 대시보드 링크) |
| `--body-file PATH` | 직접 본문 파일 지정 (기존 호환) |
| `--attach-file PATH` | 첨부 파일 (선택) |
| `--sendmail TEXT` | 발송 활성화값. 빈값/미지정이면 즉시 종료 (skip). 예: YES |
| `--only-me` | owner 에게만 발송 (테스트) |

**Makefile 타겟**:
```bash
make v2-mail      # 전체 수신자 발송 (decisions.json 자동 본문)
make v2-mail-me   # owner만 테스트 발송
```

**자동 생성 본문 구조** (`--decisions-json` 사용 시):
- `multipart/alternative` 형식: plain text(폴백) + **HTML 본문** 동시 발송
- HTML 구성 (이메일 클라이언트 호환 인라인 스타일)
  - 파란 헤더 + "대시보드 바로가기" 버튼
  - 📈 BUY 신호 테이블 (초록, 종목명·코드·그룹·순위·현재가·전략)
  - 📉 SELL 신호 테이블 (빨강)
  - 전략 설명 테이블 + 푸터
- 오늘 날짜 + 대시보드 URL
- 📈 BUY 신호 N종목 (그룹·순위·가격·전략 포함)
- 📉 SELL 신호 N종목
- 전략 설명 표 (type3 적립식 제외)

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

### 6.4 gmail-etf — Gmail 기반 ETF 자동 등록

**파일**: `src/candle/gmail_etf/{__init__, reader, resolver, run}.py`

```
흐름:
  Gmail API (gmail.readonly) → 제목 패턴 매칭
    → 본문 "TICKER : ..." 파싱
    → detect_market() (KR: 6자리 영숫자, US: 영문 1~5자)
    → resolve_ticker() (pykrx → FDR → yfinance .KS 순 fallback)
    → 등록/중복/실패 분류
    → etf_user.json + instruments.csv + ETF CSV 즉시 반영
    → SMTP 답장 (발신자 + owner 둘 다 To)
    → data/gmail_etf_history.json 이력 저장
```

상태 파일: `data/gmail_etf_state.json` (처리된 msg ID), `data/gmail_etf_history.json` (등록 이력)

이메일 형식:
```
제목: [candle][v2] YYYY-MM-DD 투자 리포트
본문: TICKER : 069500, 0190Y0, SCHD, VOO
```

명령:
```bash
make v2-gmail-etf       # 실제 처리
make v2-gmail-etf-dry   # dry-run
```

### 6.5 dashboard 파일 목록 (v2)

| 파일 | 내용 |
|------|------|
| `index.html` | KPI 카드 + 변곡점(Action Required) — 종목명·수익률·Rank·링크 포함 |
| `kospi200.html` | KOSPI200 종목 × 기간 수익률 (RANK 포함) |
| `sp500.html` | S&P500 종목 × 기간 수익률 (RANK 포함) |
| `etf_kr.html` | ETF_KR 종목 × 기간 수익률 |
| `etf_us.html` | ETF_US 종목 × 기간 수익률 |
| `compare.html` | 전략×그룹 수익률 비교 (period 탭) |
| `decisions.html` | 오늘의 의사결정 (Rule/AI/Manual 탭 + type 필터) |
| `optimize.html` | 전체 그룹 종목별 최적 파라미터 히트맵 |
| `docs.html` | claude/ 문서 뷰어 (ETF 종목 등록 포함) |
| `history.html` | Gmail-etf 등록 이력 (등록 일시·등록자·시장·그룹) |

### 6.6 사이드 JSON 산출물

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
| KR 알파뉴메릭 ticker | `0190Y0` 등 영숫자 혼합 6자리 코드 지원. `_KR_RE = r"^[0-9A-Z]{6}$"` |
| gmail-etf OAuth | gmail.readonly 스코프 유지. 답장은 SMTP. 기존 token.json 재사용 가능 |

---

## 8. 향후 작업 후보

| 항목 | 우선순위 | 메모 |
|------|---------|------|
| **nginx /news/ 서비스** | 높 | `candle.conf`에 location 추가 완료. `sudo systemctl reload nginx` 실행 필요 |
| 종목 편출입 강제 매도 | 중 | `membership.to_date` D-1 종가 매도 |
| dotenv 자동 로드 | 하 | `cli.py` 에 `load_dotenv()` 추가 → KRX_ID/PW `.env` 자동 인식 |
| analyze ranking 증분 | 중 | 현재 그룹 전체 재계산 → 신규 date만 처리로 최적화 |
| dashboard inflection 스캔 속도 | 중 | 변곡점 lookup이 30초+ (719 ticker × CSV 전체 읽기) → analyze_meta 기반 최적화 가능 |
| dashboard FastAPI 2차 | 낮 | 수동 입력 폼 UI (현재는 CSV 직접 편집) |
| v2 market_cap 저장 수정 | 중 | yfinance fast_info 가 현재 None 반환 → US/KR daily CSV 의 market_cap/rank_in_group 비어 있음. dashboard RANK 는 legacy `data/{kospi,sp500}_daily_rank.csv` 로 workaround 중 |
| 백테스트 편입 전 종목 필터 | 중 | 매수 시점에 KOSPI200/SP500 구성원인 종목만 매수 (survivorship bias 해소) |
| gmail-etf 피드 연동 | 하 | 신규 ETF 등록 후 `make v2-fetch` 자동 트리거 |
| 외국인/기관 매매 대시보드 통합 | 중 | `make v2-foreign-trading` 실행 후 KOSPI200 상세 행에 5일 순매수 표시. 현재 pykrx 안정성 의존. |
| US 시장 시그널 자동 수집 | 중 | `make v2-market-signals-us` 수동 실행 필요 → v2-all 파이프라인 포함 검토 |
| 보유 포트폴리오 트래커 | 중 | 실제 계좌 입력 → 평가손익·배당 추적. `data/holdings.csv` 기반 |

---

부록: 이 가이드는 `req.md §1.1.1~§1.1.4` + `claude-work.md` 모든 구현 항목을 반영합니다. 마지막 업데이트 2026-05-20 (19차).

---

### 2026-05-16 변경 사항 (10차)

#### Makefile — KR/US 분리 파이프라인 추가
- `v2-all-kr` / `v2-all-us` 타겟 신규. 각각 KR/US 전용 fetch→analyze→backtest→simulate→dashboard 순서로 실행.
- `v2-fetch-kr/us`, `v2-analyze-kr/us`, `v2-backtest-kr/us`, `v2-backtest-compare-full/5y-kr/us` 타겟 추가.
- help 섹션에 "시장별 분리 파이프라인" 항목 추가.
- 섹션 4.1/4.2/4.3 현행화.

#### candle.sh — 인자 기반 파이프라인 분기
- `./candle.sh kr` → v2-all-kr, `./candle.sh us` → v2-all-us, 인자 없음 → v2-all.
- 로그 파일명 / 날짜 백업 파일명도 시장별로 분리.

---

### 2026-05-13 변경 사항 (9차)

#### dashboard index.html — owner 이메일 헤더 표시
- `render.py` `common_ctx`에 `owner_name`, `owner_email` 추가 → `config/recipients.yml` `owner` 값 자동 반영.
- `templates/index.html` 헤더에 `Owner: 이철주 <cheoljoo@gmail.com>` (mailto 링크) 표시.

#### candle.sh — make v2-all 래퍼
- 기존 pvs_crawler 스크립트 → `make v2-all` 실행으로 전면 교체.
- 실행 로그: `v2-all.log` 실시간 tee + `v2-all_YYYY_MM_DD[-N].log` 날짜별 백업.

#### group_returns.html — 신규 상장/데이터 누적 중 섹션
- **동작**: `instruments.csv`에 있지만 `period_table`에 없는 종목 중 daily CSV 행수 < 200인 종목을 감지.
- **표시**: 수익률 테이블 아래 amber 배경 섹션에 진행률 바(row_count / 200) 포함 표시.
- **자동화**: 매일 `make v2-all` 수행 시 fetch → analyze → backtest가 누적되면 200행 도달 시점에 수익률 테이블로 자동 이동.

---

### 2026-05-13 변경 사항 (10차)

#### group_returns.html — 종목명 표시 개선 + 데이터부족 뱃지
- `render.py`: instruments 루프 1회 통합 → `ticker_rc` 맵 구축. `period_table` 행에 `data_lacking` / `row_count` 필드 추가.
- `templates/group_returns.html`:
  - 종목명 길이 `[:10]` → `[:25]` (2.5배 확장).
  - 종목명 색상 `text-slate-400` → `text-violet-600` (보라색).
  - `data_lacking=True` 행에 주황색 인라인 뱃지 `데이터부족 N일` 표시.

---

### 2026-05-20 변경 사항 (19차)

#### compare.html — 수익률 Top 10% 상세 내역 + compare_full.html 신규

- **배경** : "내림 순위 전체 상세" 섹션이 종목 수가 많아 스크롤이 길었고, 핵심 상위 종목 확인이 불편했음.
- **compare.html 수정**
  - 섹션 제목: `"📈 내림 순위 전체 상세"` → `"📈 수익률 Top 10% 상세 내역"`
  - 각 그룹 테이블: 전체 종목 → **상위 10%만** 표시 (`n_top10 = max(group_size // 10, 1)`)
    - ETF_US(7개) → 1개, ETF_KR(11개) → 1개, KOSPI200(200개) → 20개, SP500(500개) → 50개
  - 헤더에 `"상위 N개 / 전체 M개 (Top 10%)"` 표시
  - 제목 옆에 `"📋 내림 순위 전체 종목 상세 →"` 링크 버튼 추가 (`compare_full.html`로 이동)
- **compare_full.html 신규 생성**
  - 전체 종목 수익률 내림차순 표시
  - Top 10% 구간 행: 연초록 배경 + ★ 뱃지로 구분
  - 우상단 `"← 전략별 요약 (Top 10%)"` 버튼으로 compare.html 복귀
  - 하단 요약: `"★ Top 10% = 상위 N개 · 전체 M개"`
  - max-height 600px (compare.html 396px보다 넓게)
- **render.py 수정**
  - `compare_full.html` 렌더링 추가 (compare.html 렌더 직후 실행)


---

### 2026-05-17 변경 사항 (11차)

#### 신규 기능 4종

##### Feature 3 — 리스크 지표 (compare/run.py + compare.html)
- `compare/run.py`에 `_win_rate_and_hold()`, `_mdd_from_trades()`, `_compute_risk_map()` 추가.
- `_strategy_summary()` / `_per_ticker()`에 `avg_mdd`, `avg_win_rate`, `avg_hold_days` 컬럼 추가.
- `compare.html`: MDD·승률·평균보유일 설명 섹션(`<details open>`) + 테이블에 컬럼 3개 추가(색상 인코딩 포함).
  - MDD ≤10% 초록, ≤25% 주황, >25% 빨강 / 승률 ≥60% 초록, ≥40% 주황, 미만 빨강.
- **MDD 계산**: trade ledger의 `holding_value`(현금추적타입은 +cash)로 equity curve 구성 → 고점 대비 최대 낙폭%.
- **승률 계산**: 매도 직전 매수 row 페어링 → sell_price ≥ buy_price 여부.
- **활용법**: `make v2-compare` 실행 후 `compare.html` → 전략별 요약 탭에서 확인.

##### Feature 8 — 백테스트 거래 상세 페이지 (ticker_trades.html)
- `render.py`에 `_generate_trade_jsons()` 추가 → `dashboard_site/data/trades/{ticker}.json` 생성.
  - 우선순위: `full` period > `5y` > 첫 번째 period.
  - JSON 구조: `{ticker, name, group_name, currency, period, types: {type_name: [trades]}}`
- `ticker_trades.html` 신규: URL 해시(`ticker_trades.html#005930`) 기반 진입. JS `fetch(data/trades/{ticker}.json)` 로드.
  - 전략별 요약 카드 (MDD, 승률, 보유일 JS 계산) + 접기/펼치기 거래 상세 테이블.
  - 404 시 "백테스트가 실행되지 않은 종목" 안내 메시지.
- `group_returns.html`: `tickers_with_trades` 집합으로 백테스트 데이터 있는 종목에만 "📋 거래 이력 상세 →" 링크 표시. 없으면 "거래 이력 없음 (백테스트 데이터 필요)" 텍스트.
- `_nav.html`: "거래 이력" 메뉴 **제거** (group_returns 상세 행 링크로만 접근).
- `render.py`: `_generate_trade_jsons()` 호출을 group_returns 렌더 **전**으로 이동하여 `tickers_with_trades` 집합을 먼저 구성.

##### Feature 10 — 미국 시장 시그널 (fetch/market_signals_us.py)
- `fetch/market_signals_us.py` 신규: yfinance `^VIX`(VIX), `^TNX`(10년), `^IRX`(3개월) 증분 수집.
  - `fetch_vix()`, `fetch_us_yields()`, `check_us_signals()` — 역사적 상위 20% VIX 경보 + 10Y-3M spread 역전 감지.
  - 저장: `data/market/us_vix.csv`, `data/market/us_yields.csv`.
- `cli.py`: `candle market-signals-us` 명령 추가.
- `render.py`: `_load_market_signals_us()` + `common_ctx["market_signals_us"]` 추가.
- `market_signals.html`: KR/US Alpine.js 탭 구조로 전환. US 탭에 VIX 막대 SVG 차트 + Spread 꺾은선 SVG 차트 (3개월) + 1개월 테이블 + 용어 설명 추가.
- `Makefile`: `v2-market-signals-us` 타겟 추가.
- **활용**: `make v2-market-signals-us` → `make v2-dashboard` → `market_signals.html` US 탭.

##### Feature 13 — KOSPI200 외국인/기관 종목별 매매 (fetch/foreign_trading.py)
- `fetch/foreign_trading.py` 신규: pykrx `get_market_trading_value_by_date` per-ticker 증분 수집.
  - `ThreadPoolExecutor` 병렬 처리 (기본 4 workers).
  - 저장: `data/market/foreign/{ticker}.csv` — date, 기관합계, 외국인합계, 개인.
  - `load_latest_snapshot()`: 여러 종목의 최근 N일 합산 스냅샷 로드 헬퍼.
- `cli.py`: `candle foreign-trading` 명령 추가.
- `render.py`: `_load_foreign_snapshot()` 추가. `group_ctx["foreign_snapshot"]` 전달.
- `group_returns.html`: KOSPI200 상세 행에 "외국인 5일", "기관 5일" 순매수 합산 표시 (양수=초록, 음수=빨강).
- `Makefile`: `v2-foreign-trading` 타겟 추가.
- **활용**: `make v2-foreign-trading` → `make v2-dashboard` → `kospi200.html` 종목 클릭.

#### 새 CLI 명령 / Makefile 타겟 요약

| 명령 | 파일 저장 위치 | 설명 |
|------|--------------|------|
| `candle market-signals-us` | `data/market/us_vix.csv`, `us_yields.csv` | VIX + 미국채 수익률 증분 수집 |
| `candle foreign-trading` | `data/market/foreign/{ticker}.csv` | KOSPI200 외국인/기관 매매 증분 수집 |
| `make v2-market-signals-us` | 위 동일 + 진행 메일 | US 시장 시그널 수동 실행 |
| `make v2-foreign-trading` | 위 동일 + 진행 메일 | KOSPI200 외국인 매매 수동 실행 |

#### 파일 변경 목록

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `src/candle/compare/run.py` | 수정 | 리스크 지표 함수 추가, strategy_summary/per_ticker에 컬럼 추가 |
| `src/candle/dashboard/render.py` | 수정 | generate_trade_jsons, load_market_signals_us, load_foreign_snapshot, tickers_with_trades |
| `src/candle/dashboard/templates/compare.html` | 수정 | MDD·승률·보유일 설명 섹션 + 테이블 컬럼 추가 |
| `src/candle/dashboard/templates/group_returns.html` | 수정 | tickers_with_trades 조건 링크, 외국인/기관 5일 표시 |
| `src/candle/dashboard/templates/market_signals.html` | 수정 | KR/US 탭 분리, US 탭 VIX/Spread SVG 차트 추가 |
| `src/candle/dashboard/templates/_nav.html` | 수정 | "거래 이력" 메뉴 제거 |
| `src/candle/dashboard/templates/ticker_trades.html` | **신규** | 거래 이력 상세 페이지 |
| `src/candle/fetch/market_signals_us.py` | **신규** | VIX + 미국채 수익률 수집 |
| `src/candle/fetch/foreign_trading.py` | **신규** | KOSPI200 외국인/기관 매매 수집 |
| `src/candle/cli.py` | 수정 | market-signals-us, foreign-trading 명령 추가 |
| `Makefile` | 수정 | v2-market-signals-us, v2-foreign-trading 타겟 추가 |

