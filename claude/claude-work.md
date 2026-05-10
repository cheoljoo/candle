# Claude Work Log — candle backtest project

> **이 파일은 Claude가 이 프로젝트에서 한 작업을 누적 기록합니다.**
> 새 작업이 끝날 때마다 가장 아래 `## YYYY-MM-DD` 섹션에 *무엇을 했는지 / 무엇이 문제였고 무엇을 고쳤는지* 추가하세요. 기존 항목은 수정하지 말고 새 entry로 append.

---

## 2026-05-08

### req.md 기반 진행 가이드 작성 — `claude/claude-opus-4-7_guide.md`
- **무엇을** : req.md 의 §1.1.1~§1.1.4 (fetch / backtest / compare / simulate) 모든 항목을 cover 하는 단계적 작업 가이드 작성. 결정해야 할 12개 질문(Q1~Q12), 패키지 구조, SQLite 스키마, 6단계 로드맵, AI advisor 설계, dashboard 추천 스택, 리스크 표.
- **참고** : req.md 의 type 번호 정합성 — req.md는 type1/2/3, 기존 코드는 type1/2/4. 가이드에서 **req.md type3 = 기존 type4 (적립식)** 으로 매핑 권고.

### Q3 (저장 포맷) : SQLite + CSV → **CSV only** 로 변경
- **사용자 요청** : DB는 사용하지 말고 CSV-only.
- **수정** :
  - 가이드 §0의 Q3 권장값 변경
  - §1.1 디렉터리에서 `storage/db.py` 제거 → `storage/{paths.py, csv_io.py, incremental.py}` 로 재설계
  - §2 데이터 모델 : SQL DDL 전부 삭제 → CSV 파일별 스키마 + 예시 row 로 재작성. 2.8절에 증분/멱등성 규칙(임시파일+`os.replace` atomic write, dedup 정책, 용량 추정) 추가
  - Phase 1 task 문구 변경 ("SQLite MAX(date) 기반 증분" → "ticker별 CSV 마지막 date 기반 증분")

### Q5 (plus_days/minus_days 기본값) : 사용자가 직접 8/4 로 설정

---

## 2026-05-09

### Phase 1~3 구현 — Universe & Fetch / Analyze / Backtest
- **합의 사항 (사용자 답변)**
  - 기존 평면 .py(`fetch_data.py`, `analyze.py`, `backtest_type{1,1_2,2,4,4_2}.py`, `backtest_compare.py`, `main.py` ≈ 3,383 줄)는 폐기, `src/candle/` 패키지로 신규 작성
  - 한 세션에 Phase 1~3 까지
  - 데이터 소스 : pykrx (KR) + yfinance (US)
- **만든 것**
  - `pyproject.toml` 업데이트 — pykrx, yfinance, pyyaml, typer, pydantic, jinja2, requests, lxml, beautifulsoup4 추가. 엔트리포인트 `candle = "candle.cli:app"`
  - `config/{universe.yml, strategies.yml, runtime.yml}` — 4 그룹 정의, type별 파라미터, 시장별 cron, 초기자본
  - `src/candle/`
    - `cli.py` (typer) : `universe`, `fetch`, `analyze`, `backtest` 4개 subcommand
    - `config.py` : YAML loader
    - `storage/{paths,csv_io,incremental}.py` : atomic write, key dedup, ticker별 마지막 date 기반 증분
    - `universe/{kospi200,sp500,etf,build}.py` : KOSPI200=pykrx index 1028, SP500=Wikipedia, ETF list 고정
    - `fetch/{base,kr,us,run}.py` : KR=pykrx OHLCV+PER/PBR+시총, US=yfinance OHLCV+배당
    - `analyze/{indicators,inflection,ranking,run}.py` : MA10D/50D/10M, MA10M_UPDOWN(+/-), 변곡점(`-→+` / `+→-`), 그룹 내 시총 순위
    - `backtest/{base, type1_1, type1_2, type2_1, type2_2, type3, run}.py` : 5종 전략 + 공통 Portfolio (cash/qty/avg_cost/trade ledger), `mark_to_market` 처리
  - `Makefile` : `v2-universe`, `v2-fetch`, `v2-analyze`, `v2-backtest`, `v2-smoke`, `v2-all` 타겟
- **Smoke run** : small universe (005930, 000660, AAPL, MSFT, VOO, 1년치)
  - fetch=5, analyze=5, backtest type1_1=4 trades / type1_2=7 / type2_1=11 / type2_2=11 / type3=30
  - 검증: SK하이닉스 type2_1 +73%, AAPL type1_2 +11.7%, type3 적립식 SK하이닉스 +321% — 그럴듯하게 동작

### Phase 4~5 구현 — Compare / Simulate / AI / Dashboard
- **만든 것**
  - `src/candle/compare/run.py` : 전략 단위 요약 (총자산/현금/보유주식수/초기자본/손익/수익률/매수·매도횟수) + 종목 × 전략 cross + 종목별 최고전략 + 최고전략_매수일_시총순위 + 평가일 거래량/vol20/vol_ratio
  - `src/candle/simulate/`
    - `engine.py` : 매일 rule(=backtest types) 신호 평가 + AI + manual → `decisions.csv`. D+1 시작가에 체결 → `trades.csv`
    - `ai_advisor.py` : **Claude Opus 4.7** + prompt caching. system 프롬프트 + 종목 메타·60일 시세에 `cache_control: ephemeral`. `output_config.format` 으로 JSON schema 강제. `ANTHROPIC_API_KEY` 없으면 자동 skip. 일일 호출 상한(`runtime.yml.ai.daily_limit`, default 50). `thinking={"type":"adaptive"}` + `effort:"medium"`.
    - `manual.py` : `output/simulate/manual_input.csv` 사용자 편집 입력
  - `src/candle/dashboard/`
    - `render.py` : Jinja2 → `dashboard_site/index.html` + `data/{compare,decisions,inflections}.json`
    - `templates/index.html` : Tailwind CDN + Alpine.js. 전략 KPI 표 / 오늘 결정 (rule/ai/manual 3 그룹 탭) / 변곡점 발생 종목 (Action Required)
  - CLI 추가 : `compare`, `simulate [--no-ai]`, `dashboard`
  - Makefile : `v2-compare`, `v2-simulate`, `v2-simulate-noai`, `v2-dashboard`, `v2-smoke` 에 추가
- **Smoke run** : compare(5 strategies × 통화별 9 row, type3 KRW +252%), simulate(rule=5, ai=0 키없음, manual=0), dashboard 276줄 HTML + JSON 3개

### v2-* 명령어에 I/O 표시 — `src/candle/io_report.py`
- **사용자 요청** : `make v2-*` 으로 행해지는 모든 python code에서 input/output 파일 + 내용 설명 print
- **수정** :
  - `io_report.py` 신설 — `announce(command, inputs=[(path, desc), ...], outputs=[...])` helper. 명령 진입 시점에 입력/출력 파일 + 한 줄 설명을 ─── 박스로 출력
  - `universe/build.py`, `fetch/run.py`, `analyze/run.py`, `backtest/run.py`, `compare/run.py`, `simulate/run.py`, `dashboard/render.py` 의 `run()` 진입점에 `announce(...)` 호출 추가
  - ticker별 일봉처럼 수백~수천 파일은 패턴(`data/daily/{KR|US}/{ticker}.csv`) + 스키마 한 줄로 표시. config YAML도 입력으로 명시.

### v2-universe 에러 수정 — pykrx 1.2.x KRX 인증 정책 + 노이즈
- **증상** : `make v2-universe` 시 거대한 traceback이 화면 도배. 첫 시도는 `ValueError: The truth value of a DataFrame is ambiguous` 로 실제 crash. fallback 추가 후에도 build는 성공하나 노이즈 출력.
- **원인 4가지**
  1. **pykrx 1.2.x 가 KRX 인증을 요구** — `KRX_ID`/`KRX_PW` 환경변수 없으면 다수 endpoint(`get_index_portfolio_deposit_file`, `get_etf_ticker_list`, `get_market_cap` 등)가 빈 DataFrame 반환
  2. **DataFrame vs list 반환** — pykrx 신버전은 DataFrame, 구버전은 list 반환. 우리 코드의 `if not tickers:` 가 DataFrame 진리값에서 ambiguous error
  3. **Wikipedia HTTP 403** — User-Agent 없으면 봇 차단
  4. **pykrx 라이브러리 버그** — `pykrx/website/comm/util.py:19` 에 `logging.info(args, kwargs)` 호출. tuple 과 dict 를 그대로 전달하므로 root logger가 `msg % args` 포맷 시 `TypeError: not all arguments converted during string formatting` + 거대한 traceback. 그리고 `Error occurred in ...` 를 print로 stdout 직접 출력.
- **수정**
  - `src/candle/universe/_quiet.py` 신설 — `quiet_pykrx()` context manager. 호출 동안 (a) `sys.stdout`/`sys.stderr` 를 `StringIO` 로 redirect, (b) root logger를 `CRITICAL` 로 격하 → pykrx 노이즈 모두 차단
  - `kospi200.py` — DataFrame/list 양쪽 처리. **6일 retry 제거** (인증은 날짜 바꿔도 안 풀림). pykrx 호출은 `quiet_pykrx()` 안. 실패 시 즉시 **FinanceDataReader `StockListing('KRX')` 의 KOSPI 시총 top 200** fallback (200 종목 확보)
  - `sp500.py` — Wikipedia 요청에 User-Agent 헤더 추가. 그래도 실패 시 **`fdr.StockListing('S&P500')`** fallback (503 종목 확보)
  - `etf.py` — pykrx ETF list 호출도 `quiet_pykrx()` 안. 실패 시 **`fdr.StockListing('ETF/KR')`** 의 1099개에서 이름 정규화 매칭 (config 11개 중 8개 매칭)
  - `build.py` — 각 그룹 fetch를 `try/except` 로 감싸 한 그룹 실패해도 나머지 진행
  - `fetch/kr.py` — 평일 fetch 시에도 노이즈가 안 나오도록 OHLCV/PER/PBR/시총 호출 모두 `quiet_pykrx()` 적용
- **결과** : `universe updated: {'KOSPI200': 200, 'SP500': 503, 'ETF_KR': 8, 'ETF_US': 8, 'instruments': 719}` — 깨끗하게 통과
- **남은 한 줄 노이즈** : pykrx 가 `warnings.warn(..., stacklevel=...)` 로 직접 stderr에 토하는 `KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다.` 1줄 — `warnings.filterwarnings` 로 추가 차단 가능 (필요 시)

---

### KRX 인증 안내 — pykrx `KRX_ID`/`KRX_PW` 환경변수
- **사용자 질문**: pykrx 의 "KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다" 메시지 — 어떻게 인증받는가?
- **확인** : `pykrx 1.2.8/website/comm/auth.py:8-10` 의 `LOGIN_URL = data.krx.co.kr/.../MDCCOMS001D1.cmd` 로 보아 인증 대상은 **KRX MDC (Market Data Center) 일반 회원 계정** — 회원사/기관 계정이 아니라 누구나 무료 가입 가능. pykrx 1.2.x 가 KRX anti-bot 강화 대응으로 추가한 옵션 인증.
- **필요 여부** : 우리 fallback (FDR `StockListing('KRX')` 시총 top 200) 으로도 동작하지만, 정확한 일자별 KOSPI200 멤버십 + PER/PBR + 시총 일별 데이터를 받으려면 인증 필요.
- **방법** :
  1. https://data.krx.co.kr 접속 → "회원가입" → 본인인증 → ID/PW 설정 (~5분, 무료)
  2. `~/.bashrc` 또는 `.env` 에 `KRX_ID`/`KRX_PW` 설정
  3. 검증 : `uv run python -c "from pykrx import stock; print(len(stock.get_index_portfolio_deposit_file('1028', date='20260508')))"` 가 200을 출력하면 성공
- **추후 작업 후보** : `python-dotenv` 의존성 추가 + `cli.py` 에 `load_dotenv()` 한 줄 → `.env` 자동 로드. 사용자 요청 시 작업.

---

## 2026-05-09 (cont.)

### fetch 가속 — KR thread pool + US batch + 종목당 timeout
- **무엇을** : `make v2-all` 의 fetch 단계가 KOSPI200+SP500+ETF ≈ 720 종목을 직렬로 돌면서 매우 오래 걸리는 문제. 또한 일부 종목이 hang 되면 전체가 멈춤.
- **수정**
  - `cli.py fetch` : `--workers N` (기본 4) 와 `--timeout N` (기본 10초) 옵션 추가.
  - `fetch/run.py` 전면 재작성
    - 진입에서 `socket.setdefaulttimeout(timeout)` 적용 → pykrx/yfinance 모두 내부적으로 requests/urllib 사용하므로 종목당 네트워크 응답 N초 초과 시 `socket.timeout` raise → 기존 try/except 로 fail 처리되고 다음 종목 진행.
    - KR : `_fetch_kr_parallel` — `concurrent.futures.ThreadPoolExecutor(max_workers=workers)` 로 ticker별 fetch 병렬화. 결과는 main thread 에서 `csv_io.upsert_by_keys` 호출.
    - US : `_fetch_us_batch` — `(start, end)` window 별로 묶어 `yf.download(group_by="ticker", threads=True)` 한 번에 N개 ticker OHLCV 받음. 펀더멘털/배당은 `ThreadPoolExecutor` 로 병렬.
  - `fetch/us.py` : `fetch_daily_batch(tickers, start, end) -> dict[ticker, df]` 와 `fetch_fast_info(ticker) -> (per, shares_out, market_cap)` 추가. 기존 `fetch_daily`, `fetch_dividends` 는 유지.
- **`--debug` logging 정리** : 이전엔 debug=True 일 때 root logger 를 DEBUG 로 승격했는데 yfinance/peewee 내부 DEBUG 로그가 폭주해 → root 는 INFO 유지, candle 자체 `print()` 만 debug 출력하게 되돌림.
- **사용** : `uv run candle fetch --workers 8 --timeout 15` 처럼 가속 강도/허용시간 조절 가능. 기본은 `--workers 4 --timeout 10`.
- **검증** : `--workers 4 --timeout 10` 으로 720 ticker 처리 — 대부분 up-to-date 라 skip, 잔여 1건이 새 batch 경로로 처리됨 (delisted SOX 는 yfinance ERROR 로 빈 결과 → empty 처리). 코드 경로 정상.

### fetch debug — batch/병렬에서 "지금 어떤 종목을 받고 있는지" 출력
- **무엇이 문제** : `--debug` 켜도 `US batch download window ... — N tickers` 한 줄 찍힌 뒤 batch 가 끝날 때까지(수십초~수분) 아무 출력 없이 침묵. 어떤 종목이 fetch 중인지 알 수 없음.
- **수정** (`fetch/run.py`)
  - `_print_ticker_chunks(label, tickers, per_line=20)` 헬퍼 추가 — `[label] tickers [i-j/N]: AAA, BBB, ...` 형식으로 청크 단위 출력 (`flush=True`).
  - KR 병렬 시작 시 task ticker 전체 목록 출력. 워커 함수 `_do_one` 진입 시 `KR/{ticker} fetching...` 출력.
  - US OHLCV batch 호출 직전 window 별 ticker 목록 출력. 펀더멘털/배당 thread pool 시작 직전 ticker 목록 출력 + 워커 진입 시 `US/{ticker} info fetching...` 출력.
- **결과** : 720 종목이라도 batch 호출 직전에 어떤 종목들이 들어갔는지 보이고, 각 워커가 시작될 때마다 라인이 찍혀 진행 상황을 실시간 확인 가능.

### fetch hang 방지 — requests.Session.request monkey-patch + watchdog
- **무엇이 문제** : `--timeout 10` 을 줘도 fetch 중 일부 KR ticker 에서 30 초 넘게 응답이 없는 상태에서 `as_completed` 가 영원히 대기. `socket.setdefaulttimeout()` 만으로는 pykrx/yfinance 가 `requests` 의 connection pool 로 keep-alive 한 소켓·이미 생성된 connection 에는 적용되지 않는 케이스가 있음.
- **수정** (`fetch/run.py`)
  - `_patch_requests_timeout(timeout)` 추가 — 처음 한 번 `requests.sessions.Session.request` 를 wrap 해서 호출자가 `timeout` 미지정/`None` 인 경우 default `timeout` 을 강제 주입. 두 번째 호출부터는 `_candle_timeout` 만 갱신.
  - `run()` 진입에서 `socket.setdefaulttimeout()` 과 함께 `_patch_requests_timeout()` 도 호출.
  - KR thread pool / US 펀더멘털 thread pool 각각에 **watchdog 추가** :
    - `as_completed(futs, timeout=overall_deadline)` — `per_task_timeout × (total / workers) × 2 + per_task_timeout` 로 보수적 deadline 설정.
    - 30 초 동안 진행이 없으면 `[fetch][debug] KR heartbeat — N개 진행 중: tickers...` 출력.
    - deadline 초과 시 미완료 future 모두 `TIMEOUT` 마킹 + cancel + failed 에 추가.
  - 모든 디버그 `print` 에 `flush=True` 추가 — buffering 으로 출력이 묶이는 문제 방지.
- **사용자 시나리오** : 거래일 당일 (KRX 가 today's data 응답을 보류해 hang 되는 케이스) 에서도 10 초 후 timeout 으로 fail 처리되고 다음 종목으로 진행. Heartbeat 으로 어떤 종목이 "지금 막혀있는지" 보임.

### KR fetch: yfinance batch 우선, pykrx fallback
- **배경** : pykrx 는 KRX 서버가 불안정 할 때 hang 발생 잦음. yfinance 도 한국 주식을 `.KS` (KOSPI) / `.KQ` (KOSDAQ) 접미어로 지원하며 배치 다운로드 가능 → 훨씬 빠르고 안정적.
- **수정**
  - `fetch/kr.py` 전면 재작성
    - `fetch_daily_yf(ticker, start, end)` : `.KS` → `.KQ` 순으로 yfinance per-ticker 시도, 빈 경우 empty DataFrame 반환.
    - `to_yf_tickers(tickers, suffix)` / `strip_yf_suffix(result, suffix)` : ticker 목록 suffix 변환 헬퍼.
    - `fetch_daily_pykrx` / `fetch_etf_daily_pykrx` : 기존 pykrx 로직 private 으로 이름 변경.
    - 공개 `fetch_daily` / `fetch_etf_daily` = yfinance 우선, 실패 시 pykrx fallback.
  - `fetch/run.py` `_fetch_kr_parallel` → `_fetch_kr` 으로 재설계 (5단계)
    - **Step 1** : `us.fetch_daily_batch([ticker+".KS", ...], ...)` — 모든 KR ticker 를 yfinance 배치 1회 호출로 처리.
    - **Step 2** : Step1 에서 empty 인 ticker 들만 `.KQ` suffix 로 재시도 배치.
    - **Step 3** : yfinance 성공 ticker 에 `fast_info` (PER/shares_out/market_cap) thread pool.
    - **Step 4** : 여전히 empty 인 ticker 만 pykrx thread pool fallback (watchdog/heartbeat 포함).
    - **Step 5** : 전체 결과 CSV upsert.
- **성능** : 208개 KR ticker 기준 기존 pykrx 직렬 ~10분 → yfinance 배치 1회 ~5-10초 예상. pykrx fallback 은 예외적 상황(yfinance 에 없는 종목)에만.
- **검증** : `kr.fetch_daily_yf("005930", ...)` 및 `us.fetch_daily_batch(["005930.KS", "000660.KS"], ...)` 모두 rows 반환 확인.
- **검증** : `uv run candle fetch --debug --workers 4 --timeout 10` — patch 설치 메시지 출력, 720 ticker 처리 정상.

### v2 CLI 전체에 `--debug` 옵션 + 회사별 진행 출력 추가
- **무엇을** : `make v2-all` 시 fetch/analyze/backtest/simulate/dashboard/universe 가 회사별로 무엇을 하고 있는지 보고 싶다는 요청. 평소 출력은 그대로 두고, `--debug` 플래그가 있을 때만 회사별 start/end + 타이밍을 print.
- **수정**
  - `src/candle/cli.py` : 7개 subcommand 모두에 `--debug` 옵션 추가. `_setup_logging(cfg, debug=...)` 으로 전달해 logging level 도 DEBUG 로 승격.
  - `fetch/run.py`, `analyze/run.py`, `backtest/run.py`, `compare/run.py`, `simulate/{run.py,engine.py}`, `dashboard/render.py`, `universe/build.py` : `debug: bool = False` 인자 추가. ticker 루프에서 `[<step>][debug] (i/total) {market}/{ticker} ({group}) start` / `... end (X.XXs) — rows=N` 형식으로 print. 빈 daily / fetch window skip / fail 케이스에도 한 줄씩.
  - `analyze/run.py` : 그룹별 ranking compute 도 group×market 단위 start/end 출력.
  - `compare/run.py` : 4단계 (strategy_summary, per_ticker, best_strategy, evaluation_volume) 와 type별 summary/all 로딩에 step 라벨.
  - `dashboard/render.py` : `_load_inflections` 가 `debug` 인자를 받아 ticker별 lookup 진행 로그.
  - `universe/build.py` : KOSPI200 / SP500 / ETF_KR / ETF_US 단계별 시작·종료 + 멤버 수.
- **Makefile** : `v2-all-debug` 의 `--market all--debug`, `compare--debug`, `simulate --no-ai--debug`, `dashboard--debug` 등 띄어쓰기 누락된 8군데 수정.
- **검증** : small universe 로 `analyze --debug`, `backtest --types type1_1 --debug`, `simulate --no-ai --debug`, `compare --debug`, `dashboard --debug`, `universe --small --debug` 실행 — 모두 회사별 진행 출력 확인.
- **사용법** : `make v2-all-debug` 또는 개별로 `uv run candle <cmd> --debug`.

### fetch 시작일 2000-01-01 로 변경 + --from 백필 옵션
- **요청** : fetch 데이터를 2000년 1월 1일부터 가져오게 해달라.
- **수정**
  - `config/runtime.yml` : `default_history_days: 365` → `history_start: "2000-01-01"` + `default_history_days: 9999` (fallback).
  - `src/candle/storage/incremental.py` : `fetch_window()` 에 `from_date`, `history_start` 옵션 추가.
    - `from_date` 지정 시: 기존 파일 유무 무관, 이 날짜를 start 로 (백필).
    - `history_start` 지정 시: 신규 파일에만 적용.
  - `src/candle/fetch/run.py` : `run()` 에 `from_date` 추가. config 에서 `history_start` 파싱. `_fetch_kr` / `_fetch_us_batch` 에 전달.
  - `src/candle/cli.py fetch` : `--from DATE` 옵션 추가.
  - `Makefile` : `v2-fetch-full` 타겟 — `uv run candle fetch --from 2000-01-01 --workers 4 --timeout 30`.
- **검증** : 신규=2000-01-01~today, 기존+--from=2000-01-01~today, 기존증분=skip 모두 확인.

### analyze 증분(incremental) 처리
- **요청** : 데이터가 변하지 않았으면 skip, 새로 추가된 데이터에 대해서만 처리.
- **근거** : MA10D/50D/MA10M/MA10M_UPDOWN/inflection 모두 과거 날짜 close 가격이 확정되면 rolling 결과가 고정. rank_in_group 도 마찬가지. 따라서 과거 행을 재계산할 이유 없음.
- **수정** (`src/candle/analyze/run.py` 전면 재작성)
  - `_last_analyzed_date(df)` : ma10d가 채워진 마지막 row 의 date 반환.
  - `_build_summary_row(df, inst_row)` : 마지막 row에서 summary dict 빌드 (ticker/name/group_name/vol20/vol_ratio 포함). skip 된 ticker 도 summary 에 포함하기 위해 분리.
  - **skip 체크** : `_last_analyzed_date == last_price_date` → analyzed/write 없이 summary 만 추가. `skipped` 카운트에 포함.
  - **증분 계산** : `last_analyzed` 이후 새 row 구간만 계산.
    - context = `max(0, new_start - 220)` 부터 슬라이스 (MA10M 200행 + inflection shift 여유).
    - `indicators.compute(working)` + `inflection.compute(computed)` 를 슬라이스에만 적용.
    - 결과의 새 부분(`n_context:`)만 원본 df 의 해당 위치에 기록.
  - **rank merge 최적화** : 새 날짜에 해당하는 rank_map row 만 merge (과거 행 rank 불변).
  - 반환값 : `{"analyzed": N, "skipped": M}`.
- **성능 효과**
  - 일별 운영 (신규 row 1개/ticker) : 6500행 전체 계산 → 221행 계산. ~30배 빠름.
  - `v2-fetch-full` 직후 첫 전체 분석 : 신규 row 수에 비례 (LOOKBACK + new_rows 슬라이스).
  - 이미 분석 완료된 경우 : CSV 읽기만 하고 write 없음.
- **검증** : 005930 마지막 2행 ma10d=NA 시뮬레이션 → `new=2` 로 2행만 계산 후 값 복원 확인. 재실행 시 `analyzed=0 skipped=718`.

### analyze --refresh 추가 + skip 로직 gap 감지 보완
- **요청** : `fetch --from` 으로 과거 데이터 백필 후 analyze 를 1회 전체 재계산해야 하는 상황. `--refresh` 옵션 추가 요청.
- **문제 (기존 skip 로직 버그)** : 백필 후 앞쪽에 NA 구간이 생겨도 마지막 row 는 이미 ma10d 가 채워져 있어 `last_analyzed == last_price_date` → SKIP 되던 문제.
- **수정** (`src/candle/analyze/run.py`)
  - `_last_analyzed_date()` → `_first_unanalyzed_row()` 로 교체.
    - `df["ma10d"].isna().to_numpy().argmax()` 로 첫 NA 위치 탐지.
    - 전부 채워진 경우 `len(df)` 반환 → skip.
    - 중간 NA 구간도 자동 감지 → 처음 NA 부터 계산.
  - `run()` 에 `refresh: bool = False` 파라미터 추가.
    - `refresh=True` 이면 `new_start = 0` 강제 (skip 체크 없음, 전체 행 재계산).
    - debug 시 `REFRESH — 전체 N행 재계산` 출력.
  - 반환값 : `{"analyzed": N, "skipped": M}` (변동 없음).
- **수정** (`src/candle/cli.py`) : `analyze --refresh` 옵션 추가.
- **Makefile** : `v2-analyze-refresh` 타겟 추가 (`uv run candle analyze --market all --refresh`).
- **동작 시나리오**
  - 일별 운영 : `v2-analyze` 만으로 충분 (새 row 자동 감지).
  - `v2-fetch-full` 실행 후 : `make v2-analyze-refresh` 1회 → 2000년부터 전체 재계산.
  - 백필 gap (앞쪽 NA, 뒷쪽 filled) : `--refresh` 없이 `v2-analyze` 도 자동 감지해 처음 NA 부터 계산.
- **검증** :
  - gap 시뮬레이션(005930 앞 500행 NA): `v2-analyze` → `new=6588 rows` 전체 재계산 → NA count=9(정상, MA10D 최솟값).
  - `--refresh` : 모든 ticker `REFRESH — 전체 N행 재계산` 출력 확인.

### analyze 증분 전략 — 종목별 from/to meta 기반으로 교체
- **요청** : 종목별로 직전 분석 시 from/to 를 기록해 두고, 다음 실행에서 비교해 판단.
  - from/to 동일 → skip
  - from 이 당겨짐(백필) → 전체 재계산
  - to 만 늘어남(증분) → prev_to 다음 row 부터만 계산
- **기존 문제** : `_first_unanalyzed_row()` 는 NA 를 스캔하므로 `--from` 백필 후 앞에 NA 구간이 생기면 올바르게 감지했지만, to 가 늘어난 경우를 명시적으로 구분하지 못함. 또한 이미 분석 완료된 ticker 도 NA 스캔 비용 발생.
- **수정** (`src/candle/analyze/run.py` 전면 재작성)
  - `data/analyze_meta.csv` : ticker, market, analyzed_from, analyzed_to 4열. atomic write.
  - `_load_meta / _save_meta` : CSV 파싱 / 저장. 로드 실패 시 빈 dict(graceful).
  - 루프에서 (fetch_from, fetch_to) vs prev(analyzed_from, analyzed_to) 비교:
    1. `refresh=True` → new_start=0
    2. `prev is None` → `_first_unanalyzed_row()` fallback + meta 초기화 (전환 1회용)
    3. `prev == (fetch_from, fetch_to)` → skip
    4. `prev[0] != fetch_from` → new_start=0 (from 변경)
    5. else → new_start = prev_to 다음 row (to 변경)
  - 루프 종료 후 `{**meta, **updated_meta}` 로 전체 병합 저장 (market 필터 실행이어도 다른 market meta 보존).
- **검증**
  - meta 없음 첫 실행: 718개 이미분석완료 → meta 초기화 후 skip(0analyzed 718skipped).
  - 두 번째 실행(변동없음): analyzed=0 skipped=718.
  - 005930 to+1행(2026-05-09): `to변경(2026-05-08→2026-05-09) — new=1행` 1행만 계산.
  - 000660 from-1행(1999-12-31): `from변경(2000-01-04→1999-12-31) — new=6589행` 전체 재계산.
  - 나머지: `from=X to=Y 변동없음 → SKIP`.

### dashboard 전략별 요약 — compare period 탭 지원
- **요청** : compare 결과가 period/label 디렉터리별로 저장되므로 dashboard 도 이를 반영해달라.
- **수정**
  - `storage/paths.py` : `list_compare_periods(output_dir)` 추가 — `output/compare/` 아래 `strategy_summary.csv` 를 가진 서브디렉터리 목록 반환.
  - `dashboard/render.py`
    - `_load_compare` → `_load_compare_all` 로 교체.
      - `list_compare_periods` 로 label 디렉터리 스캔 + flat(`output/compare/strategy_summary.csv`) 도 `(기본)` 레이블로 포함.
      - 반환: `{period_label: [strategy rows]}`.
    - `render()` : `compare_all`, `compare_period_list` 를 템플릿에 전달. `compare.json` 도 새 구조로 저장.
  - `templates/index.html` : "전략별 요약" 섹션을 Alpine.js 탭으로 교체.
    - 탭 = compare period 목록 (full / 5y / 2010-2020 / (기본) 등).
    - 탭 클릭 → 해당 period의 전략×통화 수익률 테이블 표시.
    - 수익률 양수=emerald, 음수=rose 색상 적용.
- **검증** : `candle dashboard` → `compare_periods=1` (기본 flat 1개). HTML 에 `cmp_tab` Alpine 바인딩 확인.

### backtest 증분(incremental) 처리
- **요청** : 기존 처리된 구간을 기억하고, 새로 추가된 구간만 계산.
- **가능 여부** : 가능. Portfolio 상태(보유수량/현금/평균단가)를 기존 trades CSV 마지막 row에서 복원.
- **수정**
  - `backtest/base.py` : `Portfolio.from_trades()` classmethod 추가 — 기존 ledger에서 qty/cash/avg_cost/buy_count/sell_count 복원. avg_cost는 마지막 매도 이후 매수의 가중평균으로 계산.
  - `backtest/type1_1.py`, `type1_2.py` : `portfolio: Portfolio | None = None` 파라미터 추가. 제공 시 기존 Portfolio 사용.
  - `backtest/type2_1.py` : `_init_streak()` 헬퍼 추가 — resume start 이전 lookback 구간으로 streak 상태(sign/length/fired) 초기화. `portfolio` 파라미터 추가.
  - `backtest/type2_2.py` : type2_1의 `_init_streak` 재사용. `portfolio` 파라미터 추가.
  - `backtest/type3.py` : `portfolio` + `last_buy_date` 파라미터 추가. last_buy_date 제공 시 next_buy_dt = last_buy_date + interval_days 로 재개.
  - `backtest/run.py` 대폭 수정
    - `_meta.csv` (output/backtest/{label}/) : type별·ticker별 (backtest_from, backtest_to) 기록.
    - `_load_meta / _save_meta` : CSV 파싱/저장.
    - `_summary_row / _count / _print_progress` : 헬퍼 함수.
    - `_resume()` : 기존 trades에서 Portfolio 복원 → `_dispatch`에 전달.
    - `_dispatch()` : `portfolio`, `last_buy_date` 파라미터 추가해 각 type `run_one`에 전달.
    - 메인 루프 모드 결정:
      - from/to 동일 → **skip** (기존 CSV 읽어 summary 재구성, ~0s)
      - from 같고 to 늘어남 → **resume** (Portfolio 복원, 새 구간만 계산, append)
      - from 달라짐 → **full** (전체 재계산)
      - 메타 없음 → **full** (첫 실행)
    - 루프 종료 후 `_save_meta(bt_root, {**meta, **updated_meta})`.
- **검증** : type1_1 KR 208개 기준
  - 1번째 실행(full): 71.7초, skip=0, 198개 거래 발생
  - 2번째 실행(skip=198): 9.2초, skip=198, 총 5844건 동일

---

## 2026-05-10

### compare 진행 출력 추가
- **요청** : compare 도 backtest 처럼 항상 보이는 진행 출력 추가.
- **수정** (`src/candle/compare/run.py`)
  - `run()` 시작/완료: `[compare] [{label}] 시작 — period=X` / `완료 — elapsed=Xs`
  - type별 로딩: `[compare] type=X 로딩 중... (N/5)` → `완료 — rows=N, elapsed=Xs`
  - 4단계: `[compare] step N/4 ... 계산 중...` / `완료 — elapsed=Xs`
  - `_build_rank_lookup(debug=)`: 매 50개마다 `[compare] rank lookup N/719 (X%)`
  - `_best_strategy(debug=)`: rank lookup 시작 + 매 50개마다 `[compare] best_strategy ticker N/718 (X%)`
- **검증** : step 3/4 best_strategy 75초 소요 → 진행률 매 50개마다 출력 확인.

### dashboard 페이지 분리
- **요청** : 종목별 수익률 테이블이 너무 커서 렌더링 느림 → 그룹별·기능별 별도 페이지 분리.
- **수정**
  - `dashboard/render.py` : `period_table_by_group` 분리 → 7개 HTML 파일 렌더
  - `templates/_nav.html` : 공통 내비게이션 바 (모든 페이지 include)
  - `templates/group_returns.html` : 그룹별 종목 × 기간 수익률 테이블 (공통 템플릿)
  - `templates/compare.html` : 전략별 요약 (period 탭)
  - `templates/decisions.html` : 의사결정 (rule/AI/manual 탭)
  - `templates/index.html` : KPI 카드 + 페이지 링크 카드 + 변곡점만 유지
- **산출물** (dashboard_site/)
  - `index.html` (4.8KB), `kospi200.html` (1.6MB), `sp500.html` (3.9MB)
  - `etf_kr.html` (55KB), `etf_us.html` (57KB)
  - `compare.html` (35KB), `decisions.html` (406KB)
- **검증** : `candle dashboard` → `pages=7` 에러 없이 완료.

### decisions 페이지 type별 필터 추가 + nginx 설정
- **요청**
  - 오늘의 의사결정 페이지에서 type별(type1_1/type1_2/type2_1/type2_2)로 볼 수 있게 필터 추가.
  - http://psncs.iptime.org/stock_candle 에서 dashboard index.html 서비스 설정 (nginx).
- **수정** (decisions type 필터)
  - `dashboard/render.py` `_load_decisions()` : rule type별 건수 `type_counts` 딕셔너리 계산해 반환. `common_ctx`에 추가.
  - `templates/decisions.html` 전면 수정:
    - Alpine.js `x-data`에 `type_filter: 'all'` 추가.
    - tab 클릭 시 `type_filter='all'` 리셋.
    - Rule 탭 선택 시 `x-show="tab==='rule'"` 영역에 type 필터 버튼 표시 (전체 + type1_1~type2_2 각 건수 포함).
    - 각 row `x-show` 조건: `tab === d.tab && (tab !== 'rule' || type_filter === 'all' || d.source === 'rule:' + type_filter)`.
- **nginx 설정** (`/etc/nginx/conf.d/candle.conf`)
  - `location /stock_candle/` → alias `/home/cheoljoo/code/candle/dashboard_site/`
  - `location = /stock_candle` → 301 redirect to `/stock_candle/`
  - Cache-Control: no-cache (매일 재생성이므로)
  - 적용 명령: `sudo cp /tmp/candle_nginx.conf /etc/nginx/conf.d/candle.conf && sudo nginx -t && sudo systemctl reload nginx`
  - 주의: sudo는 일반 터미널에서 실행 필요 (Claude Code 터미널은 비대화형이라 암호 입력 불가).

### SOX (delisted index) 제거 + fetch 시간 단축 + 단계별 타이밍 출력

- **배경** : `yfinance: $SOX: possibly delisted` 에러가 매 fetch 마다 발생. 실제 US batch 전체가 145s 소요되는 경우 있어 개선 요청.
- **SOX 제거** (`config/universe.yml`, `fetch_data.py`)
  - `SOX` 는 PHLX Semiconductor 인덱스 — yfinance 에서 `^SOX` 여야 하며 거래 ETF 가 아님.
  - `SOXX` (iShares Semiconductor ETF) 가 동일 인덱스 추적 ETF 로 이미 등록되어 있어 중복. 두 파일에서 제거.
  - ⚠️ `data/instruments.csv` 에는 SOX 가 남아 있음 — `make v2-universe` 재실행 시 자동 제거.
- **Chunked 병렬 batch download** (`src/candle/fetch/run.py`)
  - `US_BATCH_CHUNK_SIZE = 80`, `US_BATCH_PARALLEL = 3` 상수 추가.
  - `_us_batch_download_chunked()` 신설 — 510개 ticker 를 80개씩 chunk, 3개 동시 yf.download 호출.
  - 효과: 한 chunk stall → 다른 chunk 진행 (꼬리 latency 감소), chunk 단위 완료 가시성, 실패 격리.
  - `_fetch_us_batch` 의 `us.fetch_daily_batch` 직접 호출을 `_us_batch_download_chunked` 로 교체.
- **단계별 타이밍 항상 출력** (`src/candle/fetch/run.py`)
  - Phase 1 (batch download) / Phase 2 (fast_info+dividends) / Phase 3 (CSV save) 각각 측정.
  - `--debug` 없이도 항상:
    - `[fetch] US batch window {start}..{end}: Xs (hit/total rows received)`
    - `[fetch] US summary — N tickers in Xs (batch_dl Xs / fast_info+div Xs / save Xs)`

### fetch US info 진행 번호 표시

- **요청** : `[fetch][debug] US/FFIV info fetching...` 에 몇 개 중 몇 번째인지 표시.
- **수정** (`src/candle/fetch/run.py`)
  - `_info(t)` → `_info(idx, t)` 로 변경. submit 시 `enumerate(tasks, 1)` 로 idx 전달.
  - 출력: `[fetch][debug] (123/510) US/FFIV info fetching...`

### dashboard KOSPI200/SP500 그룹 내 RANK 표시

- **요청** : ETF 가 아닌 그룹 (KOSPI200, SP500) 에서 해당 그룹 내 시총 순위(RANK) 표시.
- **수정**
  - `dashboard/render.py`
    - `_load_rank_snapshot(cfg)` 추가 — `data/kospi_daily_rank.csv` + `data/sp500_daily_rank.csv` 의 마지막 row 에서 ticker→rank 매핑 로드. 두 파일 합쳐 674개 ticker rank 반환 확인 (AAPL=3, 005930=1).
    - `_build_period_table()` : 각 row 에 `rank_in_group: rank_map.get(tk)` 추가.
  - `templates/group_returns.html`
    - `{% set show_rank = group_name in ['KOSPI200', 'SP500'] %}` 조건 추가.
    - `show_rank=True` 이면 테이블 헤더에 `RANK` 컬럼 추가, 각 행에 rank 값 출력.
    - `show_rank=False` (ETF_KR, ETF_US) 이면 컬럼 미표시.
    - 상세 펼치기 행의 `colspan` 보정 (`+3 if show_rank else +2`).
  - **데이터 소스**: `data/{kospi,sp500}_daily_rank.csv` — legacy `fetch_data.py` 산출물. v2 daily CSV 의 `rank_in_group` 은 market_cap 미저장으로 현재 비어 있어 legacy 파일 사용.
- **검증** : `candle dashboard` 정상 완료. `sp500.html` 에 RANK 컬럼 있음, `etf_us.html` 에 없음 확인.

### optimize-streak step 파라미터 추가 + Makefile `v2-optimize` 타겟

- **요청** : `plus_days 4~40 step 2`, `minus_days 4~10 step 2` 로 그리드 서치 실행. `v2-all` 미포함 별도 타겟.
- **코드 리뷰** (`src/candle/optimize/streak_grid.py`)
  - 알고리즘 정확성: `_extract_events` 는 streak_len==P 인 날만 추출 → type2_2 "첫 신호 발화" 패턴과 일치. **정확**.
  - `_simulate_one` 은 type2_2 (전액매수/전량매도) 기준 시뮬. **정확**.
  - **버그**: `range(plus_min, plus_max+1)` 에 step 없음 → step=1 고정이라 2씩 건너뛰기 불가.
- **수정**
  - `streak_grid.run()` : `plus_step: int = 1`, `minus_step: int = 1` 파라미터 추가. `range(...)` 에 step 인자 전달.
  - `cli.py optimize_streak` : `--plus-step 2`, `--minus-step 2` 옵션 추가. 기본값도 요청 범위(4~40/4~10)로 업데이트.
  - `Makefile` : `v2-optimize` 타겟 추가:
    - `plus-min 4 --plus-max 40 --plus-step 2` (19가지)
    - `minus-min 4 --minus-max 10 --minus-step 2` (4가지) → **76 조합**
    - 결과: `output/optimize/streak_grid.csv`
    - `v2-all` 에 미포함 (수동 실행 전용).
- **검증** : `candle optimize-streak --help` 에 step 옵션 정상 노출 확인.

### 일반 print에 타임스탬프 추가

- **요청** : debug가 아닌 일반 print에 `2026-05-10 19:07:07,928` 형식 타임스탬프 표시.
- **수정**
  - `io_report.py` : `_ts()` + `tprint()` 추가. `_ts()`는 `datetime.now().strftime("%Y-%m-%d %H:%M:%S,") + f"{microsecond//1000:03d}"`. `tprint()`는 첫 인자가 str 이면 `{ts} {msg}` 로 출력.
  - `announce()` 헤더 줄에도 타임스탬프 추가.
  - `fetch/run.py`, `backtest/run.py`, `compare/run.py`, `dashboard/render.py`, `optimize/streak_grid.py` : `from ..io_report import tprint` 추가, 비debug `print(...)` → `tprint(...)` 전환.
  - 규칙: `[..][debug]` 출력은 기존 `print()` 유지, 표 데이터(`to_string()`)도 `print()` 유지.
- **검증** : `candle dashboard` 출력에서 `2026-05-10 19:07:07,928 [dashboard] ...` 형식 확인.

### compare strategy_summary — 통화별 → 그룹별 + TOTAL 행

- **요청** : 전략별 비교에서 KRW/USD 구분을 Group(KOSPI200/SP500/ETF_KR/ETF_US) 단위로 세분화. 기존 합계는 TOTAL로 표시.
- **수정**
  - `compare/run.py` `_strategy_summary()` 전면 개편:
    - `instruments.csv` 에서 `group_name` 조회, summary_df 에 join.
    - `(type, group_name)` 별 집계: KOSPI200/SP500/ETF_KR/ETF_US 행 생성.
    - `(type, currency)` 별 TOTAL 행 추가 (`TOTAL (KRW)` / `TOTAL (USD)`).
    - 정렬: 전략 → 그룹(TOTAL 마지막) 순. CSV 컬럼: `strategy, group, currency, tickers, ...`.
  - `templates/compare.html` : `통화` 열 → `그룹` 열. `종목수` 열 추가. TOTAL 행 강조(`bg-slate-50 font-semibold italic`).
  - `_print_strategy()` : 그룹 컬럼 포함해 터미널 출력.
- **검증** : `output/compare/full/strategy_summary.csv` 에 `KOSPI200/SP500/ETF_KR/ETF_US/TOTAL` 행 정상 생성 확인.

### decisions 페이지 RANK 표시

- **요청** : 오늘의 의사결정 테이블에서 ETF 가 아닌 그룹(KOSPI200, SP500)에 RANK 표시.
- **수정**
  - `render.py` `render()` : `_load_rank_snapshot(cfg)` 호출 후 `_load_decisions()` 에 `rank_map` 전달.
  - `_load_decisions()` : `rank_map` 파라미터 추가. ETF_KR/ETF_US 이외 그룹에만 `rank_in_group` 값 포함(`None` for ETF).
  - `templates/decisions.html` : 그룹 열과 Ticker 열 사이에 `RANK` 열 추가. `d.rank_in_group is not none` 일 때만 숫자 출력.
- **검증** : `candle dashboard` 정상 완료. decisions.html 에 RANK 컬럼 포함 확인.

### README.md 전면 재작성 + Makefile help v2 정리

- **요청** : README.md 를 v2 기반으로 재작성. v1 내용 제거. Makefile help 도 v2 전용으로 정리.
- **수정**
  - `README.md` 전면 재작성: 빠른 시작 / 디렉터리 구조 / CLI 명령 / Makefile 타겟 / 분석 대상 / 백테스트 전략 / 데이터 모델 / 대시보드 / AI Advisor / 운영 주의사항.
  - `Makefile` `help` 타겟: v1 명령 제거 → v2 명령 카테고리별 정리 (전체/단계별/기간별/최적화/기타).

### Dashboard 문서 페이지 추가

- **요청** : 대시보드에 "문서" 항목 추가 — claude/ 안의 .md 파일을 선택해서 볼 수 있게.
- **수정**
  - `render.py` : `_DOC_LABELS`, `_DOC_ORDER` 상수 추가. `_load_docs(cfg)` — `claude/` 디렉터리의 `.md` 파일을 순서대로 읽어 `{label, filename, content}` 목록 반환.
  - `render()` : `docs.html` 렌더 추가. `docs` 를 `common_ctx` 에 포함. pages: 7→8.
  - `templates/_nav.html` : "문서" 링크 추가.
  - `templates/docs.html` (신규):
    - 왼쪽 사이드바: 문서 목록 (Alpine.js 선택 상태).
    - 오른쪽 패널: **Markdown** / **Raw** 토글.
    - Markdown 모드: `marked.js`(CDN) → HTML 렌더링 + `highlight.js` 코드 블록 syntax highlight.
    - Raw 모드: 원본 마크다운 텍스트.
    - 상단: 파일명 + 줄 수 표시.
  - 표시 순서: README → 아키텍처 가이드 → 요구사항 → 작업 이력 → Gemini 분석.
- **검증** : `candle dashboard` → `docs.html 완료 — 5개 문서`. 내비게이션에 "문서" 링크 확인.

### gmail_sender.py 전면 재작성 — 개별 To: 발송 + 자동 본문 생성

- **요청** : 수신자 목록을 config 파일로 관리. BCC→개별 To: 방식 변경. `--only-me` 플래그 추가. 의사결정 요약 자동 본문 생성.
- **수정**
  - `config/recipients.yml` (신규): `owner`, `dashboard_url`, `recipients` 목록(11명) 관리.
  - `gmail_sender.py` 전면 재작성:
    - `_load_recipients()`: `config/recipients.yml` 에서 수신자 목록 로드.
    - `_build_body_from_decisions(json_path, url)`: `decisions.json` 읽어 BUY/SELL 종목 목록 + 그룹/순위/가격/전략 + 대시보드 링크 + 전략 설명 포함 본문 자동 생성. type3(적립식) 제외.
    - `_send_one(...)`: 수신자 1인 개별 To: 발송.
    - `--only-me`: owner 에게만 발송 (테스트 용).
    - `--decisions-json`: decisions.json 경로 지정 시 본문 자동 생성.
    - `--body-file`: 기존 방식 호환.
    - 기존 BCC 하드코딩 완전 제거.
  - `Makefile` : `v2-mail` (전체 수신자) / `v2-mail-me` (owner만 테스트) 타겟 추가.
  - `v2-universe` 타겟의 잘못된 gmail 호출 제거.
- **검증** : `_build_body_from_decisions` 테스트 — BUY 10종목 (삼양식품 KOSPI200 77위 등) 정상 출력 확인.

### Dashboard 테이블 CSV 다운로드 버튼

- **요청** : dashboard 모든 테이블에 CSV 다운로드 버튼/링크 추가.
- **수정**
  - `templates/_download.html` (신규): `downloadTableCSV(tableId, filename)` 공통 JS 헬퍼. UTF-8 BOM 포함 (Excel 한글 깨짐 방지). Blob URL 방식.
  - `templates/compare.html`: 기간 탭별 테이블에 `id="cmp-tbl-N"` + "⬇ CSV 다운로드" 버튼.
  - `templates/decisions.html`: `id="dec-tbl"` + "⬇ CSV 다운로드" 버튼.
  - `templates/group_returns.html`: `id="ret-tbl"` + "⬇ CSV 다운로드" 버튼 (그룹명 포함 파일명).
  - 모든 페이지에 `{% include "_download.html" %}` 추가.
- **검증** : `candle dashboard` 정상 완료. compare/decisions/group_returns HTML 에 다운로드 버튼 포함 확인.

### nginx /news/ 서비스 복구 진단

- **상황** : `http://psncs.iptime.org/news/` 404, `http://psncs.iptime.org/stock_candle/` 200.
- **원인 분석**
  - `/etc/nginx/conf.d/candle.conf` 에 `/news/` location 없었음.
  - `/etc/nginx/sites-enabled/news-arcade` → `sites-available/news-arcade` 심볼릭 링크는 존재하나, `candle.conf`와 동일 `server_name psncs.iptime.org`로 충돌. nginx는 `conf.d/*.conf`(먼저 로드)만 사용.
  - `my-news/web/index.html` 존재, `data/news.json`(1.2MB) + `categories.json` 존재. 파일 권한(755/644) 정상.
  - `index.html`이 `fetch('/news/data/news.json')` + `fetch('/news/data/categories.json')` 사용 → `/news/data/` 별도 location 필요.
- **수정** (`/tmp/candle_nginx.conf` 작성, sudo 적용 필요)
  - `candle.conf`에 `/news/` + `/news/data/` + `location = /news` 리다이렉트 추가.
  - `/news/` → alias `/home/cheoljoo/code/my-news/web/`
  - `/news/data/` → alias `/home/cheoljoo/code/my-news/data/` (CORS 허용)
- **적용 명령** : `sudo cp /tmp/candle_nginx.conf /etc/nginx/conf.d/candle.conf && sudo nginx -t && sudo systemctl reload nginx`
- **핵심** : 설정 파일 변경 후 **반드시 `sudo systemctl reload nginx`** 실행 필요. 미실행 시 기존 설정으로 계속 서비스됨.

### Makefile SENDMAIL 플래그 — `--sendmail` 인수 방식으로 변경

- **요청** : Makefile의 조건부 `if` 블록 대신 `gmail_sender.py`에 `--sendmail "$(SENDMAIL)"` 을 항상 전달하고, py 내부에서 판단.
- **수정**
  - `gmail_sender.py` : `--sendmail` 인수 추가. 빈값/미지정이면 `"SENDMAIL 값 없음 — 건너뜀"` 출력 후 즉시 return. `--subject` 를 required → default 로 변경.
  - `Makefile` : `define SEND_MAIL` 매크로 제거. `v2-all` 에서 `--sendmail "$(SENDMAIL)"` 항상 전달. `v2-mail`/`v2-mail-me` 에 `--sendmail YES` 명시.
  - `SENDMAIL ?= YES` (기본값을 YES로 — 사용자가 변경). 미발송 시 `SENDMAIL=` 으로 빈값 전달.
  - `v2-universe` 잘못된 gmail 호출 제거. 로그 파일 `.og` 오타 → `.log` 수정.
- **검증** : `make -n v2-all SENDMAIL=YES` → `--sendmail "YES"` 정상 전달. `uv run python -u gmail_sender.py --sendmail "" --subject="test"` → 건너뜀 확인.

### Dashboard favicon 추가

- **요청** : 모든 dashboard 페이지에 촛불 아이콘 추가.
- **수정** : 5개 템플릿(index/compare/decisions/docs/group_returns) + optimize.html 에 인라인 SVG data URI favicon 추가.
  ```html
  <link rel="icon" href="data:image/svg+xml,<svg ...><text>🕯️</text></svg>">
  ```

### optimize 페이지 전면 개선 — 그룹별 + 구간 표시 + JS 버그 수정

- **요청 1** : type2_1b/type2_2b 파라미터 최적화임을 명시.
- **요청 2** : 그룹별(KOSPI200/SP500/ETF_KR/ETF_US/전체) 결과를 각기 보여주고 탭으로 선택.
- **요청 3** : 어떤 구간의 시험인지 표시.
- **버그** : Alpine.js `get` 문법이 초기 렌더 전에 JS 코드로 화면에 노출.
- **수정**
  - `streak_grid.py`
    - `run_all_groups(cfg, output_dir, ...)` 신규: ticker 1회 로딩 후 5개 그룹(all+KOSPI200/SP500/ETF_KR/ETF_US) 순차 grid search. 각 `streak_grid_{group}.csv` 저장.
    - `streak_grid_meta.json` 저장: `run_date`, `data_from/to`, `plus_range`, `minus_range`, `n_combos`, `n_tickers_total`.
    - `_grid_search()` 헬퍼 추출 (run/run_all_groups 공용).
  - `cli.py` : `--all-groups` (5개 동시 실행) + `--output-dir` 옵션 추가.
  - `Makefile` `v2-optimize` : `--all-groups --output-dir output/optimize` 사용.
  - `render.py` `_load_optimize_results()` : `{group: [rows], _meta: [...]}` dict 반환. 기존 `streak_grid.csv` → `streak_grid_all` fallback 지원.
  - `templates/optimize.html` 전면 재작성:
    - Alpine.js `get` 문법 → 일반 메서드(`sortedRows: function() {...}`)로 교체.
    - `optApp()` 함수를 `<head>` 에 배치 (Alpine.js `defer` 보다 먼저 정의).
    - `x-cloak` 추가 (Alpine 처리 전 숨김).
    - 실행 정보 카드: 실행일시/데이터구간/종목수/조합수.
    - 그룹 탭 + 히트맵 + 정렬 테이블.
    - type2_1b/type2_2b 전략 설명 + 적용 방법 가이드.
- **검증** : `candle dashboard` → `optimize.html 완료 — 전체 76개 조합`. JS 노출 없음 확인.

### Dashboard 문서 페이지 — `msg.md` 추가 + 완전 자동화

- **요청** : `./claude/msg.md` 를 대시보드 문서에 추가. 앞으로 `claude/*.md` 추가 시 자동 반영.
- **수정** (`render.py`)
  - `_DOC_LABELS` 에 `"msg": "메시지/노트"` 추가.
  - `_DOC_ORDER` 에 `"msg"` 추가 (claude-work 다음).
  - `_load_docs()` docstring 명확화: **목록에 없는 새 *.md 파일은 알파벳 순으로 자동 추가됨** (코드 수정 불필요).
- **동작** : `claude/` 에 새 `.md` 파일 추가 → `make v2-dashboard` 실행만으로 문서 페이지에 자동 노출.

---

## 2026-05-11

### ETF 종목별 optimize 대시보드 추가 — `optimize.html`

- **요청** : ETF_KR/ETF_US 탭에서 그룹 전체 결과 외에 각 종목별 최적 파라미터 히트맵 + 조합 결과도 표시.
- **배경** : 백엔드(`streak_grid.py` `run_per_ticker_group`)와 데이터 로딩(`render.py` `_load_optimize_results`)은 이미 구현 완료. 템플릿에 표시 섹션만 없었음.
- **수정** (`templates/optimize.html`)
  - `selectGroup()` JS 함수에 `this.curTicker = null;` 추가 (그룹 전환 시 종목 선택 초기화).
  - ETF 그룹 탭 선택 시 표시되는 `<section x-show="isEtfGroup()">` 블록 추가:
    - **종목 목록 뷰** (`!curTicker`): ETF 종목 요약 테이블 (ticker, 이름, 최적 plus/minus, avg_return, hit_rate). 컬럼 클릭으로 정렬.
    - **종목 상세 뷰** (`curTicker`): "← 목록으로" 버튼 + 최적값 요약 + 히트맵(plusVals×minusVals) + 전체 조합 테이블 + CSV 다운로드.
  - per-ticker 데이터 없으면 "make v2-optimize 실행 필요" 안내 메시지.
- **수정** (`render.py`)
  - ETF 종목 이름 lookup용 `etf_name_map` 구성 후 템플릿에 전달.

### `_load_decisions` 날짜 fallback + 버그 수정

- **증상** : `make v2-dashboard` 실행 시 (1) `ValueError: not enough values to unpack (expected 3, got 2)` crash. (2) 오늘의 의사결정 데이터 없음.
- **원인**
  - (1) `_load_decisions`가 `type_counts` 추가로 3→4값 반환하도록 수정됐는데, early-return 2곳만 2개 값 반환.
  - (2) `date.today()=2026-05-11`(일요일)이지만 `decisions.csv`는 `2026-05-10`(금)까지만 존재 → 필터 결과 empty.
- **수정** (`render.py` `_load_decisions`)
  - early-return에 `{}`, `on_date.isoformat()` 추가 → 4-tuple 반환.
  - `on_date` 필터 후 empty이면 `df["date"].max()` 로 **가장 최근 날짜 fallback**.
  - `actual_date` 를 반환값에 포함, 호출부에서 `as_of=actual_date` 로 대시보드 날짜 표시.
- **효과** : 주말/공휴일에 `make v2-dashboard` 실행해도 가장 최근 거래일 데이터 자동 표시.

### decisions.html type2 코드 블록 강조 카드 제거

- **요청** : "핵심: type2 계열은 정확히 N번째 날에만 선정" 코드 박스가 불필요. 아래 설명으로 충분.
- **수정** : `templates/decisions.html` 에서 `⚠️` 인디고 강조 카드 전체 제거 (약 28줄).

### streak_grid.py ETF per-ticker 병렬화

- **분석** : `run_per_ticker_group()`의 종목별 순차 루프와 `run_all_groups()`의 ETF_KR/ETF_US 순차 처리가 병렬화 가능 포인트.
- **수정**
  - `run_per_ticker_group(workers: int = 4)` 파라미터 추가. 내부 `for` 루프 → `ThreadPoolExecutor(max_workers=min(workers, n))` 로 종목별 병렬 `_grid_search` + CSV write.
  - `run_all_groups()`: ETF_KR/ETF_US 두 그룹을 `ThreadPoolExecutor(max_workers=2)` 로 동시 실행. `fut.result()`로 예외 즉시 전파.
- **효과** : ETF_KR(11개) + ETF_US(7개) per-ticker grid search가 동시·병렬 처리로 속도 향상.

### 전체 그룹 종목별 per-ticker 최적화 확장 (KOSPI200 / SP500 포함)

- **요청** : ETF_KR/ETF_US에만 적용되던 종목별 grid search를 KOSPI200/SP500까지 포함한 4개 그룹 전체로 확장. dashboard도 동일 UI로 표시.
- **수정** (`streak_grid.py`)
  - `ETF_PER_TICKER_GROUPS = ["ETF_KR", "ETF_US"]` → `PER_TICKER_GROUPS = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]`
  - `ThreadPoolExecutor(max_workers=2)` → `max_workers=4` (4개 그룹 동시 병렬)
  - `_run_etf_group` → `_run_per_ticker_group` 로 rename
- **수정** (`render.py`)
  - `ETF_PER_TICKER = ["ETF_KR", "ETF_US"]` → `PER_TICKER_GROUPS = ["KOSPI200", "SP500", "ETF_KR", "ETF_US"]`
  - `etf_name_map` (ETF만) → `name_map` (전체 instruments. ticker → name)
  - `opt_ctx["etf_name_map"]` → backward compat alias + `opt_ctx["name_map"]`
  - `_load_optimize_results()` 주석도 "ETF 종목별" → "전체 그룹 종목별" 수정
- **수정** (`templates/optimize.html`)
  - `var PER_TICKER_GROUPS = ['KOSPI200', 'SP500', 'ETF_KR', 'ETF_US']` 추가
  - `isPerTickerGroup()` 함수 추가 (`isEtfGroup()` 는 backward compat으로 유지)
  - `<section x-show="isEtfGroup()">` → `x-show="isPerTickerGroup()"`
  - 섹션 제목 "ETF 종목별 최적 파라미터" → "종목별 최적 파라미터"
  - 설명 문구에서 "ETF" 특정 제거 → 그룹 공통 문구로 변경
  - `ETF_NAME_MAP[curTicker]` → `NAME_MAP[curTicker]` (전체 종목 이름 lookup)
  - `var NAME_MAP = ETF_NAME_MAP` alias 추가 (template backward compat)
- **데이터 경로** : `output/optimize/per_ticker/{group}/{ticker}.csv` + `_summary.json` (4개 그룹 모두)
- **규모**: KOSPI200 ~200종목 + SP500 ~500종목 → `make v2-optimize` 실행 시 ~700개 per-ticker CSV 추가 생성
- **검증** : `candle dashboard --debug` 정상 완료 (pages=9, 0 traceback)
