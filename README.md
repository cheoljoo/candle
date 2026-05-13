# Motivation
> 캔들차트 하나로 끝내는 추세추종 투자 — 책 내용 구현

- 10월이평선을 아래로 뚫거나 , 위로 뚫을때 주식시장의 심리가 변한다고 본 것으로 파악됩니다. 여기에 추가로 패턴에 대한 설명들이 나와있습니다.
- 제가 주목하는 부분은 10월이평선과 만나는 부분과 그 이후의 진행상황에 대해서 이고 , 이를 backtest로 구현해보았습니다.
- KOSPI 200 · S&P500 · 주요 ETF 종목의 10월 이동평균 대비 현재가 위치를 분석하고,  최근 7거래일 이격률 추이와 변곡점 종목을 자동으로 추출합니다.

---

# Candle — 추세추종 자동 투자 시스템 (v2)

KOSPI200 · S&P500 · 주요 ETF 종목의 10월 이동평균 기반 추세추종 전략을  
자동 수집 → 분석 → 백테스트 → AI 의사결정 → 대시보드까지 일괄 처리합니다.

> **데이터 소스**: yfinance (KR/US 공용) + pykrx fallback (KR)  
> **저장 포맷**: CSV only · **실행 환경**: Python 3.13+ · `uv`  
> **대시보드**: http://psncs.iptime.org/stock_candle

---

## 빠른 시작

```bash
# 의존성 설치
uv sync

# 최초 1회: 전체 백필 (2000-01-01~)
make v2-universe
make v2-fetch-full
make v2-analyze-refresh
make v2-backtest-compare-full

# 이후 매일: 증분 실행
make v2-all

# 디버그 출력 포함
make v2-all DEBUG=--debug
```

---

## 디렉터리 구조

```
candle/
├── pyproject.toml               # 의존성: typer, pyyaml, pykrx, yfinance,
│                                #   jinja2, anthropic, FinanceDataReader, requests
├── Makefile                     # v2-* 타겟 (아래 참조)
├── config/
│   ├── universe.yml             # 그룹 정의 (KOSPI200/SP500/ETF_KR/ETF_US) + small_universe
│   ├── strategies.yml           # 전략별 파라미터, 초기자본(KRW/USD)
│   └── runtime.yml              # cron, 경로, history_start, fetch timeout
├── src/candle/
│   ├── cli.py                   # typer 진입점
│   ├── universe/                # KOSPI200·SP500·ETF 종목 목록 갱신
│   ├── fetch/                   # 일봉 증분 수집 (yfinance batch + pykrx fallback)
│   ├── analyze/                 # 지표 계산 (MA10D/50D/10M, 변곡점, 시총순위) — 증분
│   ├── backtest/                # 5종 전략 백테스트 — 증분
│   ├── compare/                 # 전략×그룹 수익률 비교
│   ├── simulate/                # 매일 rule+AI+manual 의사결정
│   ├── optimize/                # plus_days/minus_days 그리드 서치
│   ├── dashboard/               # Jinja2 → 정적 HTML (Tailwind + Alpine.js)
│   ├── storage/                 # atomic CSV write, 증분 판단
│   └── io_report.py             # announce() · tprint() (타임스탬프 출력)
├── data/                        # CSV 저장소 (.gitignore)
│   ├── instruments.csv          # 전체 종목 마스터
│   ├── analyze_meta.csv         # analyze 증분 판단용
│   ├── daily/{KR|US}/{ticker}.csv
│   └── events/dividends.csv
├── output/
│   ├── backtest/{label}/{type}/  # label = full | 5y | 2010-2020 | 2000-2015
│   ├── compare/{label}/
│   ├── simulate/
│   └── optimize/
├── dashboard_site/              # 생성된 정적 HTML
└── claude/                      # Claude 작업 문서
    ├── claude-opus-4-7_guide.md # 현행 아키텍처 레퍼런스
    ├── claude-work.md           # 작업 이력
    └── req.md                   # 요구사항 원문
```

---

## CLI 명령

```bash
candle universe   --market all [--small] [--debug]
candle fetch      --market all [--from DATE] [--workers 4] [--timeout 10] [--debug]
candle analyze    --market all [--refresh] [--debug]
candle backtest   --market all [--from DATE] [--to DATE] [--label LABEL]
                              [--types type1_1,...] [--debug]
candle compare    [--from DATE] [--to DATE] [--label LABEL] [--debug]
candle simulate   [--no-ai] [--debug]
candle dashboard  [--out DIR] [--debug]
candle optimize-streak --market all
                       [--plus-min 4] [--plus-max 40] [--plus-step 2]
                       [--minus-min 4] [--minus-max 10] [--minus-step 2]
                       [--workers 4] [--top 30] [--output CSV경로]
```

| 옵션 | 설명 |
|------|------|
| `fetch --from 2000-01-01` | 기존 파일 유무 관계없이 이 날짜부터 백필 |
| `fetch --workers 4` | 병렬 worker 수 (기본 4) |
| `fetch --timeout 10` | 종목당 HTTP timeout 초 (기본 10) |
| `analyze --refresh` | meta 무시, 전체 행 강제 재계산 |
| `backtest --label 5y` | 출력 경로를 날짜 대신 고정 label 로 지정 |
| `optimize-streak --plus-step 2` | plus_days 탐색 간격 |

---

## Makefile 타겟

### 전체 파이프라인

```bash
make v2-all                    # universe→fetch(full)→analyze→backtest→simulate→dashboard
make v2-all DEBUG=--debug      # 위 + 단계별 상세 출력
```

### 단계별 실행

```bash
make v2-universe               # 종목 목록 갱신
make v2-fetch                  # 오늘치 증분 fetch
make v2-fetch-full             # 2000-01-01부터 전체 fetch
make v2-analyze                # 새 row 자동 감지 증분 분석
make v2-analyze-refresh        # 전체 재분석 (백필 후 1회 실행)
make v2-backtest               # 기간별 backtest+compare 병렬 실행
make v2-simulate               # 오늘 의사결정 (rule+AI+manual)
make v2-simulate-noai          # AI 없이 rule+manual만
make v2-dashboard              # HTML 대시보드 재생성
```

### Backtest 기간별 타겟 (병렬)

```bash
make v2-backtest               # full + 5y + 2010-2020 + 2000-2015 동시 실행
make v2-backtest-compare-full        # 2000-01-01~ backtest+compare
make v2-backtest-compare-5y          # 최근 5년 backtest+compare
make v2-backtest-compare-2010-2020   # 2010~2020 고정 기간
make v2-backtest-compare-2000-2015   # 2000~2015 고정 기간
```

### 파라미터 최적화 (v2-all 미포함 — 수동 실행)

```bash
make v2-optimize               # plus 4~40 step2 × minus 4~10 step2 = 76 조합
make v2-optimize DEBUG=--debug
# 결과: output/optimize/streak_grid.csv + 상위 30개 터미널 출력
```

### 기타

```bash
make v2-smoke                  # 소규모 universe로 전체 파이프라인 빠른 검증
make v2-universe-small         # dev용 소규모 universe만 빌드
```

---

## 분석 대상

| 그룹 | 종목 수 | 통화 | 소스 |
|------|---------|------|------|
| KOSPI200 | ~200개 | KRW | pykrx index 1028 → FDR fallback |
| SP500 | ~503개 | USD | Wikipedia → FDR fallback |
| ETF_KR | 11개 | KRW | config/universe.yml 고정 |
| ETF_US | 7개 | USD | config/universe.yml 고정 (VOO·SPY·QQQ·SCHD·JEPI·SOXX·XLE) |

---

## 백테스트 전략

| 코드 | 설명 | 매수 | 매도 |
|------|------|------|------|
| `type1_1` | 변곡점 · 고정수량 | MA10M 교차 `-→+` 시 10주 | `+→-` 시 10주 |
| `type1_2` | 변곡점 · 전액매수 | MA10M 교차 `-→+` 시 전액 | `+→-` 시 전량 |
| `type2_1` | 연속일수(8/4) · 고정수량 | +8일 연속 → 10주 | -4일 연속 → 10주 |
| `type2_2` | 연속일수(8/4) · 전액매수 | +8일 연속 → 전액 | -4일 연속 → 전량 |
| `type2_1b` | 연속일수(33/5) · 고정수량 | +33일 연속 → 10주 | -5일 연속 → 10주 |
| `type2_2b` | 연속일수(33/5) · 전액매수 | +33일 연속 → 전액 | -5일 연속 → 전량 |
| `type3` | 적립식 90일 주기 | 90일마다 정액 입금 후 전액 매수 | 없음 |

> `type2_1b`/`type2_2b` 의 최적 `plus_days`/`minus_days` 탐색 → `make v2-optimize`

### 증분 처리 (backtest)

| 조건 | 처리 | 예: KR 208종목 |
|------|------|----------------|
| from/to 동일 | skip (기존 CSV 읽기만) | ~9s |
| to 늘어남 | Portfolio 상태 복원 + 새 구간만 계산 | 수초 |
| from 달라짐 / 첫 실행 | 전체 재계산 | ~72s |

---

## 데이터 모델 (주요 파일)

### 일봉 + 지표
**`data/daily/{KR|US}/{ticker}.csv`**
```
date, open, high, low, close, volume, per, pbr, shares_out, market_cap,
ma10d, ma50d, ma10m, ma10m_updown, inflection, rank_in_group
```
- `ma10m_updown`: `+` / `-`
- `inflection`: `-→+` / `+→-` (교차일만, 나머지 빈값)
- 신규 ticker: `history_start: "2000-01-01"` 부터 수집

### Backtest 결과
**`output/backtest/{label}/{type}/{ticker}.csv`**
```
type, date, ticker, side, price, qty, amount, holding_qty, holding_value, cash, return_pct
```
`{label}` = `full` | `5y` | `2010-2020` | `2000-2015`

### Compare 결과
**`output/compare/{label}/strategy_summary.csv`**
```
strategy, group, currency, tickers, 총자산, 현금, 보유주식수, 초기자본, 손익, 수익률, 매수횟수, 매도횟수
```
- `group`: `KOSPI200` / `SP500` / `ETF_KR` / `ETF_US` / `TOTAL (KRW)` / `TOTAL (USD)`

### 의사결정
**`output/simulate/decisions.csv`**
```
decision_id, date, ticker, source, action, qty, price, reason, raw_json_path
```
- `source`: `rule:{type}` | `ai` | `manual`

---

## 대시보드

`make v2-dashboard` 로 `dashboard_site/` 에 정적 HTML 7개 생성.

| 파일 | 내용 |
|------|------|
| `index.html` | KPI 카드 + 페이지 링크 + 오늘의 변곡점 |
| `kospi200.html` | KOSPI200 종목 × 기간 수익률 (RANK 포함) |
| `sp500.html` | S&P500 종목 × 기간 수익률 (RANK 포함) |
| `etf_kr.html` | ETF_KR 종목 × 기간 수익률 |
| `etf_us.html` | ETF_US 종목 × 기간 수익률 |
| `compare.html` | 전략×그룹 수익률 비교 (period 탭) |
| `decisions.html` | 오늘의 의사결정 (Rule/AI/Manual 탭 + type 필터) |

---

## AI Advisor

`candle simulate` 실행 시 Claude Opus 4.7 API 호출 (선택적).

- **입력**: 종목 메타 + 최근 60거래일 시세/MA/UPDOWN + PER + 시총순위 + 룰 신호
- **출력**: `action: buy|sell|hold` + `confidence` + 근거/리스크 (JSON)
- **비용 통제**: `runtime.yml` → `ai.daily_limit` (기본 50). `ANTHROPIC_API_KEY` 없으면 자동 skip.
- **Prompt caching**: system + 종목 메타·60일 시세 → `cache_control: ephemeral`

수동 의사결정: `output/simulate/manual_input.csv` 직접 편집 후 `candle simulate` 재실행.

---

## KRX 인증 (선택)

pykrx 정확도 향상을 위해 KRX MDC 계정 설정 가능 (무료):

```bash
# https://data.krx.co.kr 회원가입 후
export KRX_ID=your_id
export KRX_PW=your_pw
```

인증 없이도 FinanceDataReader fallback으로 정상 동작.

---

## 운영 주의사항

| 항목 | 내용 |
|------|------|
| 최초 백필 후 분석 | `make v2-fetch-full` → `make v2-analyze-refresh` (1회) |
| 새 backtest 기간 추가 | Makefile에 `v2-backtest-compare-<label>` 타겟 추가 + `-j` 줄 포함 |
| AI 비용 | `runtime.yml` `ai.daily_limit` 조정 |
| yfinance 속도 | US batch는 80개씩 chunk × 3 병렬 실행. 전체 510종목 기준 ~46~145s |
| 로그 확인 | 모든 일반 출력에 타임스탬프(`2026-05-10 19:07:07,928`) 포함 |

---

## 환경

- Python 3.13+  · 패키지 관리: `uv`
- 주요 라이브러리: `yfinance`, `pykrx`, `FinanceDataReader`, `pandas`, `typer`, `jinja2`, `anthropic`

---

## ETF 종목 등록

Gmail을 통해 이메일 한 통으로 ETF 종목을 시스템에 자동 등록할 수 있습니다.  
등록된 ETF는 `data/universe/etf_user.json`에 저장되고 이후 일괄 분석에 즉시 반영됩니다.

### 이메일 작성 규칙

**받는 사람**: `cheoljoo@gmail.com`  
**제목**: `[candle][v2] YYYY-MM-DD 투자 리포트` 형식이면 됩니다  
(Re:, Fw: 등 접두사는 무시됩니다)

**본문**:
```
TICKER : 종목코드1, 종목코드2, 종목코드3
```

- `TICKER :` 뒤에 쉼표(`,`)로 구분해 여러 종목을 한 번에 요청할 수 있습니다.
- **한국 ETF**: KRX 6자리 코드 (숫자 `069500`, 또는 영숫자 혼합 `0190Y0` 모두 가능)
- **미국 ETF**: 알파벳 1~5자리 심볼 (예: `VOO`, `SCHD`, `QQQ`)

**예시 이메일**:
```
제목: [candle][v2] 2026-05-13 투자 리포트

TICKER : 069500, 0190Y0, SCHD, VOO
```

### 처리 실행

```bash
# 미처리 메일 확인 + 처리 (실제 등록)
make v2-gmail-etf

# 처리 내용만 출력 (실제 등록 없음)
make v2-gmail-etf-dry
```

처리 후 자동으로 발신자에게 결과 답장이 발송됩니다.

---

### 답장 예시 — 등록 성공

```
Re: [candle][v2] 2026-05-13 투자 리포트

안녕하세요. ETF 등록 처리 결과를 알려드립니다.

요청 ticker: 069500, 0190Y0, SCHD, VOO

✅ 신규 등록 (2건):
  • 0190Y0 — Mirae Asset Tiger Google Value Chain Etf (KR / ETF_KR)
  • SCHD — Schwab US Dividend Equity ETF (US / ETF_US)

⏭ 이미 등록됨 (2건):
  • 069500 — KODEX 200
  • VOO — Vanguard S&P 500 ETF

처리 일시: 2026-05-13 00:06:24
```

---

### 답장 예시 — 일부 실패

```
Re: [candle][v2] 2026-05-13 투자 리포트

안녕하세요. ETF 등록 처리 결과를 알려드립니다.

요청 ticker: 0190Y0, ABCDE, 999999

✅ 신규 등록 (1건):
  • 0190Y0 — Mirae Asset Tiger Google Value Chain Etf (KR / ETF_KR)

❌ 등록 실패 (2건):
  • ABCDE — 시장 판별 실패 또는 종목 정보 없음
  • 999999 — 종목 정보를 찾을 수 없습니다

처리 일시: 2026-05-13 00:06:24
```

실패 원인은 주로 다음과 같습니다:
- 존재하지 않는 종목 코드
- 7자리 이상이거나 형식이 맞지 않는 코드 (예: `TOOLONG`, `123`)
- 신규 상장 직후 데이터 미제공 기간 (수 영업일 후 재요청 권장)

---

### 상태 및 목록 파일

| 파일 | 내용 |
|------|------|
| `data/universe/etf_user.json` | 등록된 사용자 ETF 목록 |
| `data/gmail_etf_state.json` | 처리 완료된 메시지 ID (중복 방지) |
