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

---

## 2026-05-11

### streak_grid.py — debug 전용 로그 분리 (`_debug_log()`)
- **사용자 요청** : optimize 실행 시 로그가 너무 많아 노이즈 발생.
- **수정** : `_debug_log(enabled, message)` 헬퍼 추가. `debug=True` 일 때만 streak 로딩/완료/그룹별 진행/종목별 grid search 로그 출력. 일반 실행(`debug=False`)에서는 완전히 침묵.

### optimize.html — RANK(`rank_in_group`) 컬럼 및 정렬 추가
- **사용자 요청** : 종목별 최적화 테이블에 그룹 내 순위(rank)도 보고 싶다.
- **수정**
  - `render.py` → `opt_ctx["rank_map"]` 추가 (ticker → rank_in_group)
  - `optimize.html` → `var RANK_MAP = {{ rank_map | tojson }}` 주입
  - `tickerRank(tk)` 함수 추가, 정렬 로직에 `rank_in_group` case 분기 추가
  - "rank" 정렬 버튼 추가, 기본 정렬 방향 = 오름차순(낮은 rank = 상위 종목)
  - per-ticker 테이블 RANK 컬럼 추가

### config/recipients.yml & README.md
- `cheoljoo.lee@lge.com` 메일 수신자 추가
- `README.md` 상단에 Motivation 섹션 추가 (10월이평선 기반 추세추종 투자 배경 설명)

---

## 2026-05-12

### dashboard/templates/index.html — 변곡점 테이블 종목명·수익률·Rank·링크 개선
- **사용자 요청** : 변곡점 발생(Action Required) 테이블에서 Ticker만으로는 종목을 알 수 없다. 종목명, 기간수익률, 그룹 내 Rank, 상세 링크를 함께 보여달라.
- **수정** (`render.py`)
  - `name_map`(ticker → 종목명) 빌드 로직을 `common_ctx` 생성 전으로 이동
  - `period_table_by_ticker`(ticker → period_table row) 신규 추가
  - 두 dict 모두 `common_ctx`에 추가 → 모든 템플릿에서 공유
  - optimize.html 전용 `name_map` 중복 빌드 제거 (common_ctx 재사용)
- **수정** (`templates/index.html`)
  - "Ticker" 헤더 → "Ticker / 종목명", 종목코드 아래 종목명(한글/영문) 소자로 표시
  - `-→+` 초록(`text-emerald-600`), `+→-` 빨강(`text-rose-600`) 색상 구분
  - 기간 수익률(best) 컬럼 신규: 기간별 최고전략 수익률 `+XX.X%` 형식 + Rank 표시
  - 상세 링크 컬럼 신규: 📊 수익률 (해당 그룹 backtest 페이지), ⚙ 최적화 (optimize.html) 버튼

### gmail-etf 기능 신규 구현 — `src/candle/gmail_etf/`
- **사용자 요청** : Gmail로 ETF TICKER를 요청하면 자동으로 universe에 추가하고 결과를 답장으로 받고 싶다.
- **구현** (`src/candle/gmail_etf/__init__.py`, `reader.py`, `resolver.py`, `run.py`)
  - **reader.py** : Gmail API (gmail.readonly 스코프) — 기존 `token.json` 재사용 가능. 제목 패턴 `[candle][v2] YYYY-MM-DD 투자 리포트` 매칭, 본문 `TICKER : ...` 파싱.
  - **resolver.py** : ticker 시장 판별(`detect_market`) + 종목 정보 조회(`resolve_ticker`).
    - KR: pykrx → FDR → yfinance `.KS` 순 fallback
    - US: yfinance
  - **run.py** : 오케스트레이션. 미처리 메일 → ticker 파싱 → 등록/중복/실패 분류 → `etf_user.json` + `instruments.csv` + ETF 그룹 CSV 즉시 반영 → SMTP 답장 발송 → 상태/이력 저장
  - **SMTP 답장** : `smtplib.SMTP_SSL("smtp.gmail.com", 465)` — Gmail API `gmail.modify` 불필요. `gmail.readonly` 토큰만으로 동작.
  - **owner CC** : 답장 수신자에 발신자 + owner 모두 포함 (`To: from_email, owner`)
  - **이력 파일** : `data/gmail_etf_history.json` — `{datetime, by, ticker, name, market, group_name}` 항목 누적 저장
- **KR 알파뉴메릭 ticker 지원** (`resolver.py` 버그 수정)
  - 기존: `_KR_RE = re.compile(r"^\d{6}$")` — 순수 숫자 6자리만 KR로 인식
  - 수정: `_KR_RE = re.compile(r"^[0-9A-Z]{6}$")` — 영숫자 혼합 6자리도 KR 인식
  - 배경: `0190Y0` (TIGER 구글밸류체인 ETF, 2026-05-12 신규 상장) 처리 불가 → pykrx 미지원 → yfinance `.KS` fallback으로 `Mirae Asset Tiger Google Value Chain Etf` 조회 성공
- **Makefile** : `v2-gmail-etf`, `v2-gmail-etf-dry` 타겟 추가
- **cli.py** : `gmail-etf` subcommand 추가 (`--dry-run`, `--debug` 옵션)

### dashboard — ETF 등록 이력 페이지 신규 추가
- **사용자 요청** : dashboard 홈에 "이력" 탭을 추가해 gmail-etf로 추가된 종목의 등록 일시·등록자를 볼 수 있게 해달라.
- **수정**
  - `templates/_nav.html` : "문서" 다음 "이력" 링크 추가
  - `templates/history.html` 신규: 요약 카드(총 건수/KR/US/등록자 수) + 시장·등록자 필터 + 최신순 테이블
  - `render.py` : `_load_etf_history()` 추가, `history.html` 렌더 (총 10개 파일)
  - `data/gmail_etf_history.json` : `0190Y0` 초기 항목 수동 추가 (2026-05-13, cheoljoo@gmail.com)

### README.md — ETF 종목 등록 섹션 추가
- `claude/register_etf_ticker.md` 신규 생성: 이메일 형식, 처리 실행, 답장 예시(성공/실패), 지원 ticker 형식 표
- `README.md` 맨 끝에 "ETF 종목 등록" 섹션 추가 (동일 내용)
- dashboard `docs.html` 문서 목록에 "ETF 종목 등록" 항목 추가 (`_DOC_LABELS`, `_DOC_ORDER` 갱신)

### analyze/run.py — FutureWarning 수정
- **증상** : `uv run candle analyze --market all` 실행 시 `FutureWarning: Setting an item of incompatible dtype` 반복 출력
- **원인** : `out[col] = pd.NA`로 초기화된 컬럼(object dtype)에 float64 DataFrame의 새 값을 `iloc` 할당할 때 dtype 불일치
- **수정** : `import numpy as np` 추가. `iloc` 할당 전 컬럼 dtype 확인 후 명시적 캐스팅 — float 컬럼은 `to_numpy(dtype=float, na_value=np.nan)`, object 컬럼은 `to_numpy(dtype=object)`

---

## 2026-05-13

### dashboard index.html — owner 이메일 표시
- **사용자 요청** : dashboard 홈 헤더에 owner 이름과 이메일 주소 표시 (이철주, cheoljoo@gmail.com).
- **수정**
  - `render.py` : `common_ctx`에 `owner_name="이철주"`, `owner_email=cfg.recipients.get("owner", "")` 추가 (`config/recipients.yml` 의 `owner` 값 자동 반영).
  - `templates/index.html` : 헤더 기준일/생성 시각 아래에 `Owner: 이철주 <cheoljoo@gmail.com>` 표시 (mailto 링크 포함).
  - `dashboard_site/index.html` : 현재 생성된 파일에도 동일하게 반영.

### candle.sh — make v2-all 실행 + 날짜별 log backup
- **사용자 요청** : `candle.sh`를 `make v2-all`을 수행하도록 변경. 실행 로그를 날짜별로 backup.
- **수정** (`candle.sh` 전면 재작성)
  - 기존 pvs_crawler 관련 코드 전부 제거.
  - `CANDLE_DIR=/home/cheoljoo/code/candle` 로 이동 후 `make v2-all 2>&1 | tee v2-all.log`.
  - 실행 후 `v2-all_YYYY_MM_DD.log` 형태로 날짜 백업. 같은 날 여러 번 실행 시 `-1`, `-2` 번호 자동 부여.

### dashboard group_returns.html — 신규 상장/데이터 부족 종목 표시 (하단 섹션)
- **사용자 요청** : `0190Y0`처럼 최근 상장되어 MA10M 계산(최소 200행)이 불가한 종목도 ETF_KR 등 그룹 페이지에 표시하되 이유를 설명해 달라. 매일 fetch가 쌓이면 자동으로 수익률 테이블로 이동.
- **배경** : `0190Y0` (TIGER 구글밸류체인 ETF)는 2일치 데이터만 존재 → ma10m=NaN → backtest 신호 없음 → period_table 미포함.
- **수정** (`render.py`)
  - `MA10M_MIN_ROWS = 200` 상수 정의.
  - `instruments.csv`에 있지만 `period_table`에 없는 종목을 순회.
  - `data/daily/{market}/{ticker}.csv` 행 수(헤더 제외)를 직접 세어 200행 미만이면 `new_listings_by_group[grp]`에 추가 (`{ticker, name, row_count, needed}` dict).
  - 그룹 렌더 컨텍스트에 `new_listings` 전달.
- **수정** (`templates/group_returns.html`)
  - 기존 수익률 테이블 아래 황색(amber) 섹션 신규 추가 (`{% if new_listings %}`).
  - 종목명, 보유 데이터(일수), 필요 데이터(200일), 진행률 바(%) 표시.
  - 200일 도달 시 자동으로 수익률 테이블에 포함됨을 안내.

### dashboard group_returns.html — 종목명 표시 개선 + 데이터부족 뱃지 (수익률 테이블 내)
- **사용자 요청** : 수익률 테이블에서 종목명이 너무 짧게 잘린다(10자). 2.5배(25자)로 늘리고 회색 대신 보라색으로 변경. 데이터가 부족한 종목에는 테이블 내에도 뱃지를 표시해 달라.
- **수정** (`render.py`)
  - instruments 순회 루프 1회로 통합: `ticker_rc: dict[str, int]` 구축 (모든 ticker CSV 행 수).
  - `new_listings_by_group` 구성도 동일 루프에서 처리.
  - `period_table` 각 행에 `data_lacking` (bool, row_count < 200), `row_count` (int) 필드 추가.
- **수정** (`templates/group_returns.html`)
  - 종목명 표시 길이: `row.name[:10]` → `row.name[:25]`.
  - 종목명 색상: `text-slate-400` → `text-violet-600`.
  - `data_lacking=True` 행에 주황색 인라인 뱃지 `데이터부족 N일` 표시 (수익률 테이블 종목 칸 내부).

---

## 2026-05-15

### gmail_sender.py — 수신자 중복 제거
- **배경** : `config/recipients.yml`의 `recipients` 목록에 `owner`(cheoljoo@gmail.com)가 중복 포함돼 있어 일반 발송 시 owner가 2통 수신.
- **수정** (`gmail_sender.py` `main()`)
  - `to_list = [owner] + [...]` 생성 후 `seen` 집합으로 순서를 유지하며 중복 제거.
  - 제거된 수가 1 이상이면 `[mail] 중복 수신자 N명 제거됨` 로그 출력.

### gmail_sender.py — HTML 이메일 발송 지원
- **사용자 요청** : 메일 본문을 대시보드 홈처럼 HTML 형식으로 보내고 싶다.
- **구현**
  - `_build_html_body_from_decisions(decisions_json_path, dashboard_url) -> str` 신규 함수:
    - 이메일 클라이언트 호환 **인라인 스타일 HTML** 생성 (CDN 불필요, table-based layout)
    - 파란 헤더 + "대시보드 바로가기" 버튼
    - 📈 BUY 신호 테이블 (초록 테두리·배경, 종목명/코드/그룹/순위/현재가/전략)
    - 📉 SELL 신호 테이블 (빨강 테두리·배경)
    - 전략 설명 테이블 + 푸터 (Candle 자동 발송 · 날짜 · 이메일)
  - `_send_one()` 시그니처에 `html_body: str | None = None` 추가:
    - `html_body` 있으면 `MIMEMultipart("mixed")` 안에 `MIMEMultipart("alternative")` 내포
    - alternative 안에 plain text(폴백) + HTML 순서로 첨부 → 클라이언트가 HTML 미지원 시 plain 표시
  - `main()` : `--decisions-json` 지정 시 plain body와 html body 동시 생성 후 `_send_one`에 전달.
- **검증** : `uv run python gmail_sender.py --only-me --decisions-json dashboard_site/data/decisions.json` 로 owner에게 발송 — HTML 메일 정상 수신 확인.

---

## 2026-05-16 (2차 — 시장 시그널 대시보드 고도화)

### 시장 시그널 전용 페이지 + 홈 요약 간소화
- **사용자 요청** : 홈에는 그래프와 해당 날짜 내용만 표시하고, 전체 상세 내용은 별도 "시장 시그널" 메뉴로 분리
- **수정**
  - `templates/_nav.html` : "시장 시그널" 메뉴 아이템 추가 (market_signals.html 링크)
  - `templates/market_signals.html` 신규: 독립 페이지 — 경보 배너, 요약 카드 2개, 3개월 CSS 막대 차트, 1개월 상세 테이블(날짜/순매수/역사MAX/MAX비율%)
  - `templates/index.html` : 홈 시장 시그널 섹션 간소화 — 오늘 카드 2개 + 3개월 미니 차트 + "전체 보기 →" 링크만 유지
  - `render.py` : `market_signals.html` 렌더 추가, `pages=11` 카운트 갱신

### uk_fmt Jinja2 필터 추가 (억 → 조 변환)
- **사용자 요청** : 33664억 같은 큰 숫자를 "3조 3664억" 형식으로 표시
- **구현** : `render.py`에 `_uk_fmt(v)` 함수 추가 — `abs(v) >= 10000` 이면 `X조 Y,YYY억`, 아니면 `Y,YYY억` (음수 부호 보존)
- `env.filters["uk_fmt"] = _uk_fmt` 등록 후 모든 템플릿에서 `{{ val | uk_fmt }}` 사용
- **검증** : −44,664억 → `-4조 4,664억`, +3,300억 → `+3,300억`

### KOSPI 지수 수집 + 상관관계 분석 (market_signals.py)
- **사용자 요청** : 테이블 매수 옆에 KOSPI 지수 표시, 막대+꺾은선 그래프, 상관관계 계산
- **아키텍처 결정** : 데이터 수집/상관계수 계산은 모두 `market_signals.py`에서 처리, `render.py`는 CSV 읽기만
- **구현** (`src/candle/fetch/market_signals.py`)
  - `fetch_kospi_index(start, end, save_path)` 신규: pykrx `stock.get_index_ohlcv("1001")` → `data/market/kospi_index.csv` 증분 저장
  - `_calc_correlation(s1, s2)` 헬퍼: Pearson r, `pd.Series.corr()`, 샘플 10개 미만 시 None
  - `check_signals()` 파라미터에 `kospi_df` 추가, result에 `prog_kospi_corr`, `finv_kospi_corr`, `kospi_data` 반환
  - `run()` : kospi_index.csv 증분 fetch → `check_signals(kospi_df=kospi_df)` 전달, verbose 출력에 상관계수 추가
- **검증** : `candle market-signals` 실행 → 프로그램 비차익 r=−0.373, 금융투자 r=+0.279 출력

### SVG 인라인 차트 (막대+KOSPI 꺾은선) + 테이블 KOSPI 컬럼
- **render.py** : `kospi_index.csv` 로드, `check_signals`에 `kospi_df=` 전달, 차트 데이터에 `kospi_close`/`kospi_y_pct` 필드 추가 (10~90% 정규화), 테이블에 `kospi_close`, 반환 dict에 `prog_kospi_corr`/`finv_kospi_corr` 추가
- **market_signals.html / index.html** : CSS flex 막대 차트 → SVG `<rect>` 막대 + `<polyline>` KOSPI 꺾은선으로 교체 (`viewBox="0 0 N 100" preserveAspectRatio="none"`)
- 테이블에 KOSPI 컬럼 추가, 차트 하단에 r값 인라인 표시

### 시장 시그널 페이지 — 용어 설명 + 상관관계 시각화
- **사용자 요청** : 프로그램 비차익/금융투자 용어 설명, 상관관계 의미 및 시각화 추가
- **구현** (`templates/market_signals.html`)
  - `<details open>` 용어 설명 카드: 프로그램 비차익(알고리즘 바스켓 매매, ETF 환매, 경보 로직), 금융투자(전문기관 자기계정, 연속 순매도 의미), 데이터 출처
  - 상관관계 분석 섹션: `−1.0 ~ +1.0` 그라디언트 게이지 바 + 검정 마커(`left: pct%`), 강도 뱃지(강함/중간/약한) 자동 표시
  - `<details>` "해석 방법": r 범위 해석표 + 현재 수치 활용법 (언제 경계가 필요한지 포함)

---

## 2026-05-16 (3차 — Makefile KR/US 분리 + candle.sh 개선)

### Makefile — v2-all-kr / v2-all-us 시장별 파이프라인 분리
- **사용자 요청** : 한국장(~16:00 KST)과 미국장(~09:00 KST)이 끝나는 시간이 다르므로 각각 끝날 때마다 KR/US 전용 파이프라인을 실행할 수 있게 분리
- **설계**
  - `fetch`, `analyze`, `backtest` 는 `--market kr|us|all` 옵션 지원을 확인
  - `simulate`, `dashboard` 는 `--market` 없이 전체 실행 (양쪽 파이프라인에서 공통 사용)
  - `market-signals` 는 KRX 데이터이므로 KR 파이프라인에만 포함
  - `gmail-etf` 는 KR 파이프라인에만 포함 (하루 1회 체크로 충분)
- **추가된 Makefile 타겟** (`.PHONY` 포함)
  - `v2-fetch-kr` : `candle fetch --market kr`
  - `v2-fetch-us` : `candle fetch --market us`
  - `v2-analyze-kr` : `candle analyze --market kr` + 진행 메일
  - `v2-analyze-us` : `candle analyze --market us` + 진행 메일
  - `v2-backtest-compare-full-kr/us` : backtest(--market kr/us) + compare 순차
  - `v2-backtest-compare-5y-kr/us` : 5년 rolling backtest(--market kr/us) + compare
  - `v2-backtest-kr` : full-kr + 5y-kr 병렬(`-j`) + 진행 메일
  - `v2-backtest-us` : full-us + 5y-us 병렬(`-j`) + 진행 메일
  - `v2-all-kr` : `gmail-etf → fetch-kr → analyze-kr → backtest-kr → simulate → market-signals → dashboard → sendmail`
  - `v2-all-us` : `fetch-us → analyze-us → backtest-us → simulate → dashboard → sendmail`
- **help 섹션** : "시장별 분리 파이프라인" 항목 추가 (v2-all-kr/v2-all-us 설명)
- **검증** : `make -n v2-all-kr` / `make -n v2-all-us` dry-run으로 실행 순서 확인

### candle.sh — 인자(kr/us)에 따라 파이프라인 분기
- **사용자 요청** : `candle.sh` 뒤에 `kr` 또는 `us`를 붙여 해당 파이프라인 실행, 로그 파일명도 맞게 변경
- **수정** (`candle.sh` 전면 개선)
  - 인자 `$1` 파싱: `kr` → `v2-all-kr` / `us` → `v2-all-us` / 없음 → `v2-all`
  - 로그 파일: `candle-v2-kr.log` / `candle-v2-us.log` / `candle-v2.log`
  - 날짜 백업 파일 패턴: `candle-v2-kr-YYYY_MM_DD.log` / `candle-v2-us-YYYY_MM_DD.log` / `candle-v2-YYYY_MM_DD.log`
  - 잘못된 인자 시 `Usage: $0 [kr|us]` 출력 후 exit 1
- **사용법**
  ```bash
  ./candle.sh        # v2-all  (기존 동작 유지)
  ./candle.sh kr     # v2-all-kr  (한국장 종료 후 ~16:00 KST)
  ./candle.sh us     # v2-all-us  (미국장 종료 후 ~09:00 KST)
  ```
- **crontab 예시**
  ```
  0 16 * * 1-5  /home/cheoljoo/code/candle/candle.sh kr >> /tmp/candle-kr-cron.log 2>&1
  0  9 * * 2-6  /home/cheoljoo/code/candle/candle.sh us >> /tmp/candle-us-cron.log 2>&1
  ```
- **검증** : `bash -n candle.sh` → syntax OK 확인

---

## 2026-05-16

### Feature 3: 리스크 지표 도입 (MDD·승률·평균보유일)
- **무엇을** : `compare/run.py`에 `_win_rate_and_hold()`, `_mdd_from_trades()`, `_compute_risk_map()` 추가. `_strategy_summary()`에 `avg_mdd`, `avg_win_rate`, `avg_hold_days` 컬럼 추가. `_per_ticker()`에 종목별 리스크 지표 평균 추가.
- **템플릿** : `compare.html` 테이블 헤더·행에 MDD(색상: ≤10%=초록, ≤25%=주황, >25%=빨강), 승률(≥60%=초록), 보유일 컬럼 추가.
- **접근법** : MDD는 trade ledger의 holding_value(+cash for cash-tracking types)로 equity curve 구성 → peak 대비 낙폭 최대값. 승률은 직전 buy row와 sell row를 페어링해 sell_price ≥ buy_price 여부 판정.

### Feature 8: 백테스트 거래 상세 페이지
- **무엇을** : `render.py`에 `_generate_trade_jsons()` 추가 → `dashboard_site/data/trades/{ticker}.json` 생성 (full period 우선). `ticker_trades.html` 신규 템플릿 (hash URL: `ticker_trades.html#005930`). `group_returns.html` 상세 행에 "📋 거래 이력 상세 →" 링크 추가. `_nav.html`에 "거래 이력" 메뉴 추가.
- **구조** : 정적 HTML 셸 + JS fetch(`data/trades/{ticker}.json`) → 요약 카드(전략별 MDD/승률/보유일) + 접기/펼치기 거래 상세 테이블.

### Feature 10: 미국 시장 시그널 (VIX + 미국채 수익률)
- **무엇을** : `fetch/market_signals_us.py` 신규 (yfinance `^VIX`, `^TNX`, `^IRX`). VIX 퍼센타일 경보 + 10Y-3M spread 역전 시그널. `cli.py`에 `candle market-signals-us` 추가. `render.py`에 `_load_market_signals_us()` + `_load_foreign_snapshot()`. `market_signals.html`에 KR/US Alpine.js 탭 추가. `Makefile`에 `v2-market-signals-us` 타겟 추가.

### Feature 13: 외국인/기관 종목별 매매 (KOSPI200)
- **무엇을** : `fetch/foreign_trading.py` 신규 — pykrx `get_market_trading_value_by_date` per-ticker. ThreadPoolExecutor 병렬 수집. `load_latest_snapshot()` 헬퍼. `cli.py`에 `candle foreign-trading` 추가. `Makefile`에 `v2-foreign-trading` 타겟. `render.py`에 `_load_foreign_snapshot()` + `group_ctx["foreign_snapshot"]`. `group_returns.html` 상세 행에 KOSPI200 종목 외국인/기관 5일 순매수 합산 표시.

### Feature 8 수정 — 거래 이력 링크 정확도 개선
- **문제** : KOSPI200 종목 클릭 시 "HTTP 404" 오류 — 해당 종목의 backtest `_all.csv` 데이터가 없으면 `data/trades/{ticker}.json` 파일이 생성되지 않아 fetch 실패.
- **원인** : `_generate_trade_jsons()`는 `output/backtest/full/{type}/_all.csv`에 있는 종목만 JSON 생성. backtest가 부분 실행된 경우 일부 KOSPI200 종목이 누락됨.
- **수정**
  - `render.py`: `_generate_trade_jsons()` 호출을 group_returns 렌더 **전**으로 이동. 실행 후 `tickers_with_trades = {p.stem for p in trades_dir.glob("*.json")}` 집합 구성.
  - `group_returns.html`: `row.ticker in tickers_with_trades` 조건으로 링크 표시 여부 분기. 없으면 "거래 이력 없음 (백테스트 데이터 필요)" 텍스트 표시.
  - `ticker_trades.html`: 404 catch 시 "백테스트가 실행되지 않은 종목" 안내 메시지로 개선.

### UI 개선 — compare.html MDD·승률 설명 섹션
- **수정** : `compare.html` 테이블 상단에 `<details open>` 섹션 추가.
  - MDD: 개념·색상 기준(≤10%초록/10~25%주황/>25%빨강)·활용법
  - 승률: 개념·색상 기준(≥60%초록)·주의사항(승률 단독 판단 금지)
  - 평균 보유일: 개념·type별 특성·계산 방식

### UI 개선 — 거래 이력 nav 메뉴 제거
- **사유** : `ticker_trades.html`은 URL 해시(`#ticker`)가 있어야 동작. 독립 메뉴로 진입 시 항상 빈 화면 → 불필요.
- **수정** : `_nav.html`에서 "거래 이력" 링크 삭제. group_returns 상세 행의 "📋 거래 이력 상세 →" 링크(backtest 데이터 보유 종목만)로만 접근 가능.

### Feature 10 보완 — US 시장 시그널 SVG 차트 추가
- **수정** : `market_signals.html` US 탭에 3개월 SVG 차트 2종 추가.
  - VIX 막대 차트: 경보 기준선(빨강 점선) + 공포(빨강)/주의(노랑)/안정(초록) 색상 바.
  - Spread 꺾은선 차트: 10Y-3M spread, 0 기준선(회색 점선), 역전 구간 포인트(빨강 원).


---

## 2026-05-17

### enabled_types / disabled_types — strategies.yml 연동

- **배경** : `config/strategies.yml`에 `enabled_types: [type1_2, type2_2, type2_2b, type3]` 항목이 있지만, CLI에서 types를 항상 전체 7개로 하드코딩해 무시되던 문제.
- **수정** (`src/candle/config.py`)
  - `ALL_TYPES` 상수 추가 (type1_1~type3 고정 순서).
  - `enabled_types` 프로퍼티: `strategies.yml`의 `enabled_types`를 ALL_TYPES 순서로 필터링. 없으면 전체 7개 하위호환.
  - `disabled_types` 프로퍼티: enabled에 없는 비활성 type 목록.
- **수정** (`src/candle/cli.py`)
  - `_DEFAULT_WORKERS = max(1, (os.cpu_count() or 4) // 2)` 추가 — Worker 기본값 CPU×1/2.
  - `backtest`, `compare` 명령의 `--types` 옵션: 미지정 시 `cfg.enabled_types` 사용.
  - `simulate` 명령: `rule_types=cfg.enabled_types` 전달.
  - `fetch`, `optimize-streak` 명령: workers 기본값 `_DEFAULT_WORKERS`로 변경.
- **수정** (`src/candle/simulate/run.py`, `src/candle/dashboard/templates/_type_legend.html`)
  - simulate/run.py: `rule_types` 파라미터 수용, 해당 types만 신호 평가.
  - _type_legend.html: enabled/disabled 뱃지 스타일 분리.

### enabled_types 기반 ON/OFF 뱃지 + best_return 필터링 (dashboard)

- **수정** (`src/candle/dashboard/render.py`)
  - `enabled_types`, `disabled_types` → `common_ctx`에 추가.
  - `_build_period_table()`: `best_return` 집계 시 enabled_types 기준으로 best_type 결정.
  - `_load_decisions()`: 신호 날짜(`date`) = `cur_row["date"]`(마지막 거래일)로 사용.
  - `DOW_KR`, `_dow_fmt` Jinja2 필터 추가 (날짜→요일 변환).
  - type 설명 수정:
    - `type1_1`: "변곡점 신호 · 고정수량 매수·매도"
    - `type1_2`: "변곡점 신호 · 전액매수·전량매도" (전: "전액매수")
    - `type2_1`: "연속일수(8/4) · 고정수량 매수·매도" (전: "고정수량")
    - `type2_2`: "연속일수(8/4) · 전액매수·전량매도" (전: "전액매수")
    - `type2_1b`, `type2_2b`: 동일 패턴 수정
- **수정** (`src/candle/dashboard/templates/group_returns.html`)
  - 전략 열에 ON/OFF 뱃지: disabled type은 `opacity-50 bg-slate-300` 스타일.
- **결과** : disabled type 행이 시각적으로 흐릿하게 표시 → enabled type의 best_type이 강조됨.

### -4일 연속 계산 거래일 기준 확인

- **검증** : CJ대한통운(000120) daily 데이터 확인.
  - 2026-05-12(화, -), 05-13(수, -), 05-14(목, -), 05-15(금, -) = 4일 연속.
  - 2026-05-16(토), 05-17(일) — daily CSV에 없음 → 토/일 포함 아님 ✓.
  - streak 계산은 daily CSV 기반이므로 이미 거래일 기준.

### v2-optimize 진행 상황 표시 (--debug 없이도 가시화)

- **문제** : `streak_grid.py` 핵심 진행 메시지들이 `_debug_log(debug, ...)` 함수 내부에서만 출력 → `--debug` 없으면 아무것도 출력 안 됨.
- **수정** (`src/candle/optimize/streak_grid.py`)
  - 로딩 시작/완료(100개 단위), 그룹별 grid search 시작/완료, combo 진행(20개 단위 elapsed+ETA), per-ticker 종목별 완료 메시지를 `print()` 직접 호출로 변경.
  - 예: `[streak_grid] 전체 ticker streak 로딩 중... (823개, workers=2)`
  - `_grid_search()` 내 `elif done % 20 == 0` → `tprint(...)` 직접 호출.

### market calendar 수집 기능 추가

- **수정** (`src/candle/storage/paths.py`)
  - `market_calendar_csv(data_dir)` 경로 함수 추가 → `data/market_calendar.csv`.
- **수정** (`src/candle/fetch/run.py`)
  - `_build_market_calendar(data_dir, market)` 추가:
    - 기존 calendar max_date 이후만 증분 집계.
    - 속도 최적화: 파일별 마지막 줄만 읽어 비교 (22초 → 1.5초).
    - 컬럼: `date, is_kr_trading(bool), is_us_trading(bool)`.
    - KR/US 각 컬럼 병합 upsert.
  - fetch 완료 후 `if market in ("all", "KR"): _build_market_calendar(...)` 자동 호출.
- **결과** : `data/market_calendar.csv` — KR 6595일, US 6632일 거래일 기록.

### 의사결정 날짜 = 마지막 거래일(신호 확인일)로 변경

- **배경** : `on_date=2026-05-17(일)` 실행 시 date=2026-05-17이 표시되던 문제.
  - 신호는 2026-05-15(금) 기준 → date도 2026-05-15가 맞아야 함.
- **수정** (`src/candle/simulate/engine.py`)
  - rule decisions: `"date": on_date.isoformat()` → `"date": str(cur_row.get("date", on_date.isoformat()))`.
  - `event_date` 컬럼 추가: type1=변곡점 발생일, type2=streak 시작일 (연속 시작 행의 날짜).
  - manual decisions: `on_date` 유지 (변경 없음).
  - settlement 로직: `decision_date=2026-05-15` → `nxt > 2026-05-15` → 2026-05-18 체결 ✓.
  - `decisions.csv` 스키마: `decision_id, date, ticker, source, action, qty, price, reason, event_date, raw_json_path`.
- **수정** (`src/candle/dashboard/templates/decisions.html`)
  - 기준일 헤더: `event_date` → `date` (마지막 거래일).
  - 날짜 칼럼: `date (요일)` 주 표시, `event_date`(연속 시작일)를 괄호로 부 표시 (다를 때만).
  - `dow_fmt` 필터 적용 (YYYY-MM-DD → YYYY-MM-DD (요일)).

### ticker String 강제화 — csv_io.read()

- **배경** : KR ticker(`000120` 등)는 숫자만으로 구성되어 pandas가 int로 읽을 수 있음. 이로 인해 `str(ticker)` 비교 시 불일치 발생.
- **수정** (`src/candle/storage/csv_io.py`)
  - `read()` 함수: `pd.read_csv()` 후 `"ticker"` 컬럼이 있으면 항상 `.astype(str)` 강제.
  - 모든 CSV 읽기 경로(decisions, instruments, daily 등)에 자동 적용.

### decisions.csv stale rows 정리 + engine.py 검증 가드

- **배경** : 수정 전 `engine.py`가 `on_date.isoformat()` 사용 → 일요일 실행 시 date=2026-05-17 등 비거래일 기록. 수정 후에도 기존 stale rows가 남아 대시보드에 주말 날짜 표시.
- **처리 흐름**:
  1. 첫 번째 일회성 cleanup 스크립트: 주말(토/일) 날짜의 rule decisions 중 동일 (ticker, source)에 평일 날짜가 있는 행 제거 (7262 → 4114 rows).
  2. engine.py에 aggressive stale cleanup 추가 → 역사적 decisions 행까지 삭제하는 버그 발견(4114 → 1251 rows).
  3. engine.py에서 stale cleanup 코드 **제거** (cur_row["date"] 사용으로 근본 해결).
  4. 두 번째 cleanup: 주말 날짜 rows 완전 제거 (`dayofweek >= 5`) → 1251 → 1181 rows.
  5. 000120 type2_1 event_date NaN → 2026-05-12 수동 수정 (type2_2와 동일 streak 시작일).
- **추가** (`src/candle/simulate/engine.py`)
  - `_load_trading_days(data_dir)`: market_calendar.csv → `{'KR': {날짜 set}, 'US': {날짜 set}}` 로드. 파일 없으면 빈 dict(검증 skip).
  - rule decisions 생성 후 market_calendar 기반 비거래일 date 검증: 비거래일이면 `log.warning` + 출력 후 skip.
  - **설계 원칙**: `cur_row["date"]` = 실데이터 날짜이므로 정상 운영 시 항상 통과. fetch 없이 실행하거나 데이터 이상 시 방어 필터로 작동.
- **결과**: `decisions.csv` 1181 rows, 주말 날짜 없음. KR/US 공휴일(평일)도 fetch 데이터에 없으면 자동 제외됨.

### 변곡점 발생 테이블에 날짜 컬럼 추가

- **수정** (`src/candle/dashboard/render.py`, `src/candle/dashboard/templates/index.html`)
  - `_load_inflections()` 반환 dict에 `"date": target` 추가 (KR/US 시장별 유효 날짜).
  - `index.html` 변곡점 테이블: `날짜` 헤더 컬럼 추가, 각 행에 `{{ r.date | dow_fmt }}` 표시.
  - KR 종목은 KR 거래일, US 종목은 US 거래일 기준으로 각자 정확한 날짜 표시.

### decisions 테이블 — 백테스트 마지막 action 비교 컬럼 + 거래이력 링크

- **배경** : decisions.csv의 오늘 action이 backtest 최근 신호와 다른 경우(stale 또는 데이터 불일치)를 직접 표시.
- **수정** (`src/candle/dashboard/render.py`)
  - `_load_last_backtest_actions(cfg)` 신규: `output/backtest/full/{type}/_all.csv` 에서 `mark_to_market` 제외 후 (ticker, type_name) → 마지막 buy/sell action을 dict로 반환.
  - `_load_decisions()` : `last_bt_actions` 파라미터 추가. rule decisions의 각 row에 `last_bt_action` 필드 추가.
  - `render()` : `_load_last_backtest_actions(cfg)` 호출 후 `_load_decisions()`에 전달.
- **수정** (`src/candle/dashboard/templates/decisions.html`)
  - Action 컬럼 색상 코딩: `last_bt_action != action` 이면 굵은 빨간색 + `← 직전: buy/sell` 표시.
  - 거래이력 컬럼 신규: `📋 TICKER` → `ticker_trades.html#TICKER:type_name` 링크.
  - 테이블 헤더에 "거래이력" 컬럼 추가.
- **수정** (`src/candle/dashboard/templates/ticker_trades.html`)
  - `#TICKER:type_name` URL hash 지원: `const [ticker, focusType]` 파싱.
  - focusType 지정 시: `section-{tname}` id 기준 자동 펼침 + indigo ring + smooth scroll.

### decisions 테이블 — enabled_types 기반 rule decisions 필터링

- **배경** : `type1_1`처럼 `strategies.yml`의 `enabled_types`에서 제외된 type의 stale decisions rows가 decisions.csv에 남아 대시보드에 표시되던 문제.
- **원인 분석** : `run.py`는 이미 `cfg.enabled_types`를 사용하지만 기존 decisions.csv의 과거 stale rows가 남아 있음.
- **수정** (`src/candle/dashboard/render.py` `_load_decisions()`)
  - `cfg.enabled_types`가 있으면 `enabled_set` 구성.
  - `source.startswith("rule:")` 인 rows 중 `source[5:]`(type 이름)가 `enabled_set`에 없는 것은 today에서 제외.
  - `ai`, `manual` source는 영향받지 않음.
- **효과** : decisions.csv에 type1_1 stale rows가 남아 있어도 dashboard에 미표시. config에서 enabled_types 변경 시 즉시 반영.

### decisions 테이블 — 직전 날짜 신호 비교로 교체 (prev_action)

- **배경** : 기존 `_load_last_backtest_actions()` 방식은 backtest 마지막 action vs 오늘 simulate를 비교했으나, 정상 운영 시(매일 `make v2-all`) 둘 다 같은 데이터 기반이라 항상 일치 → 정보 가치 없음.
- **사용자 제안** : decisions.csv 직전 날짜의 action과 비교해야 "오늘 신호가 바뀌었는지"를 알 수 있음.
- **수정** (`src/candle/dashboard/render.py`)
  - `_load_last_backtest_actions()` 함수 **삭제** (backtest _all.csv 기반 비교 제거).
  - `_load_decisions()` 파라미터에서 `last_bt_actions` 제거.
  - 내부에서 decisions.csv의 `actual_date` 직전 날짜(`prev_date`) 로우를 읽어 `(ticker, source) → action` 매핑 구성.
  - 각 row에 `prev_action` (직전 날짜 같은 rule의 action), `signal_changed` (prev_action이 있고 오늘 action과 다를 때 True) 필드 추가.
  - `render()` 호출부에서 `last_bt_actions` 로딩 코드 제거.
- **수정** (`src/candle/dashboard/templates/decisions.html`)
  - Action 컬럼 색상 로직 교체:
    - `signal_changed=True` + `action=buy` → **빨간 굵은 글씨** + `← 직전: sell` (매수 전환, 액션 필요)
    - `signal_changed=True` + `action=sell` → **파란 굵은 글씨** + `← 직전: buy` (매도 전환, 액션 필요)
    - `signal_changed=False` → 일반 pill 표시. `prev_action` 있으면 회색 소자로 직전 action 표시.
- **검증** : `actual_date=2026-05-15, 77건` 중 `signal_changed=1건` — `HSY rule:type1_2 prev=buy → today=sell` 정상 감지 확인.

### backtest 거래 이력 — Buy-Sell 수익률(사이클별 수익률) 컬럼 추가

- **배경** : 기존 `return_pct`(수익률)은 초기자본 대비 누적 수익률. 각 Buy→Sell 사이클별 개별 수익률을 별도 표시하는 요청.
  - `return_pct` 예시: Cycle2 sell = −4.59% (초기 1000 기준 누적)
  - `buy_sell_return_pct` 예시: Cycle2 = (954.12−987.75)/987.75 = −3.41% (해당 사이클만)
- **계산 공식** : `buy_total = buy_row.holding_value + buy_row.cash`, `sell_total = sell_row.holding_value + sell_row.cash`, `return = (sell_total − buy_total) / buy_total × 100`
- **수정** (`src/candle/backtest/base.py`)
  - `TRADE_COLUMNS`에 `buy_sell_return_pct` 추가.
  - `Portfolio.__post_init__()`: `self._last_buy_total: float | None = None` 초기화.
  - `buy()`: 매수 직후 `self._last_buy_total = holding_value + cash` 기록.
  - `sell()`: `sell_total = self.qty * price + self.cash` → `(sell_total − _last_buy_total) / _last_buy_total × 100` → `_record()` 전달. 전량 매도 후 `_last_buy_total = None` 리셋.
  - `from_trades()` (증분 복원): 미결 buy 포지션이 있으면 마지막 buy 행의 `holding_value + cash` → `_last_buy_total` 복원.
- **수정** (`src/candle/dashboard/render.py`)
  - `_compute_buy_sell_returns(records)` 헬퍼 추가: buy-sell 쌍으로 in-place 계산 (기존 CSV 폴백).
  - `_generate_trade_jsons()`: `buy_sell_return_pct` cols에 추가. CSV에 없으면 `_compute_buy_sell_returns()` 자동 호출.
- **수정** (`src/candle/dashboard/templates/ticker_trades.html`)
  - "현금" 컬럼 옆 "**Buy-Sell 수익률**" 컬럼 추가.
  - sell 행에만 표시: **이익(+) = 빨간색 굵은 글씨**, **손실(−) = 파란색 굵은 글씨**. 나머지 행은 `—`.
- **검증** : `HSY type1_2`
  - Cycle1: buy_total=1000 → sell=987.75 → `−1.2245%` ✓
  - Cycle2: buy_total=987.75 → sell=954.12 → `−3.4052%` ✓ (누적 −4.59%와 다름 — 정상)

### 거래 이력 차트 — Chart.js 종가·10월MA·매수/매도 마커·보유수량

- **사용자 요청** : 거래 이력 상세 페이지 각 type별 차트 추가 (종가, 10월이평선, 매수/매도 시점, 보유수량).
- **데이터 준비** (`src/candle/dashboard/render.py`)
  - `inst_map`에 `market` 필드 추가 (`instruments.csv` → `row["market"]`).
  - `_load_ticker_prices(data_dir, market, ticker, months=12)` 헬퍼 신규:
    - `data/daily/{KR|US}/{ticker}.csv`에서 최근 12개월 데이터 로드.
    - 반환: `{dates: [...], closes: [...], ma10m: [...]}`
    - 데이터 없거나 예외 시 빈 dict 반환.
  - `_generate_trade_jsons()` payload에 `prices` 키 추가: `prices_data = _load_ticker_prices(...)`.
- **Chart.js CDN 추가** (`templates/ticker_trades.html` `<head>`)
  - `chart.js@4.4.4` CDN script 추가.
- **`buildTradeChart()` 함수 신규** (`templates/ticker_trades.html`)
  - 5개 dataset: 종가(slate line), 10월MA(orange dash), 매수(green triangle↑), 매도(red triangle↓, rotation=180), 보유수량(green step-fill, right y-axis).
  - `tradeByDate` 맵으로 prices window 내 거래만 마커 표시.
  - tooltip: 매수 행 → `현금, 보유수량`; 매도 행 → `현금, Buy-Sell 수익률`.
  - 가격 데이터 없으면 canvas 자동 제거.
- **섹션 HTML 수정**: 각 type 섹션에 `<canvas id="chart-{tname}">` 추가.
- **ON 전략만 차트 표시** : `isOn = !ENABLED_TYPES.size || ENABLED_TYPES.has(tname)` — OFF 전략은 canvas 미삽입 + `buildTradeChart()` 미호출.
- **전략 설명 표시** : `TYPE_DESCRIPTIONS` JS Map (Jinja2 `type_descriptions | items`) 주입.
  - 각 섹션 헤더에 `short — detail` 설명 라인 + ON/OFF 뱃지 표시.
- **차트 구간 1년** : `_load_ticker_prices` 기본값 `months=6` → `months=12` 변경.
- **리스크 지표 설명 섹션 기본 접힘** : `risk-body` div에 `hidden` 클래스 추가, 버튼 텍스트 `접기` → `펼치기`.
- **검증** : `make v2-dashboard` 정상 완료. `dashboard_site/data/trades/000100.json`의 `prices.dates` 248개(1년치) 확인.

---

## 2026-05-18

### analyze 버그 수정 — `ValueError: could not convert string to float: '-'`

- **증상** : `candle analyze --market kr` 실행 시 `ValueError: could not convert string to float: '-'` 발생. `analyze/run.py:183` 의 `out.iloc[...] = vals` 에서 object → float 강제 변환 실패.
- **원인** : `out[col] = pd.NA` 로 신규 컬럼 초기화 시 pandas 가 해당 컬럼 dtype 을 `float64` 로 설정. 이후 `is_float_dtype(col_dtype)` 체크가 True 가 되어 문자열 컬럼(`ma10m_updown`, `inflection`)에도 `to_numpy(dtype=float)` 를 시도.
- **수정** : dtype 검사 대신 `_STRING_COLS = {"ma10m_updown", "inflection"}` 하드코딩 set 으로 판별. set 에 있으면 `to_numpy(dtype=object)`, 나머지는 `to_numpy(dtype=float, na_value=np.nan)`.

### 대시보드 테이블 정렬 기능 추가 — 공유 JS 유틸리티 (data-sortable)

- **사용자 요청** : 모든 대시보드 페이지 테이블에 컬럼 헤더 클릭 시 오름차순/내림차순 정렬 기능 추가.
- **수정**
  - `src/candle/dashboard/templates/_nav.html` 에 공유 JS 정렬 유틸리티 추가 (모든 템플릿이 `{% include "_nav.html" %}` 사용).
    - `cellText()`, `parseVal()` (숫자/문자열 자동 판별), `sortTableBody()`, `updateIcons()` (⇕/↑/↓), `initSortableTable()`, `initAll()` 함수.
    - `window.initSortableTable`, `window.initAllSortableTables` 노출.
    - `data-sortable` 속성이 있는 `<table>` 에 자동 초기화 (DOMContentLoaded 또는 즉시).
  - 7개 템플릿에 `data-sortable` 추가: `compare.html`(기간 탭별 4개), `decisions.html`, `group_returns.html`, `history.html`, `index.html`, `market_signals.html`(4개), `ticker_trades.html`(JS 생성 테이블 포함).
  - `ticker_trades.html` : JS `renderTrades()` 완료 후 `initAllSortableTables()` 호출.

### compare 전략별 요약 — 정렬 후 전략명 빈칸 수정

- **증상** : 승률 컬럼 클릭으로 정렬 시 전략 컬럼이 빈칸으로 보임.
- **원인** : Jinja2 템플릿에서 `strategy_changed` 시에만 전략명 출력 → 각 전략 그룹의 첫 행에만 전략명, 나머지는 빈 문자열. 클라이언트 정렬 후 행이 섞여도 HTML 셀 값은 고정.
- **수정** : `compare.html` 전략 컬럼 `{% if strategy_changed %}{{ r.strategy }}{% endif %}` → `{{ r.strategy }}` 로 변경. 모든 행에 전략명 항상 표시.

### compare 전략 요약 CSV — KR/US 병합 저장

- **증상** : `v2-all-kr` 실행 후 대시보드 전략별 요약에 ETF_KR/KOSPI200 만 표시; SP500/ETF_US 누락. `v2-all-us` 실행 시 반대.
- **원인** : `compare/run.py` 에서 `strategy_summary.csv` 를 항상 새 데이터로 덮어씀. KR 실행 시 USD 행(SP500, ETF_US) 소실, US 실행 시 KRW 행 소실.
- **수정** : `strategy_summary.csv` 저장 직전, 기존 파일이 있으면 `currency` 컬럼 기준으로 현재 실행에 없는 통화의 행을 보존 후 병합 저장.
  - KR 실행(`currency=KRW`): 기존 USD 행 보존, KRW 행만 교체.
  - US 실행(`currency=USD`): 기존 KRW 행 보존, USD 행만 교체.
  - 최초 실행(파일 없음): 기존 로직과 동일.
  - **주의**: 최초에는 `v2-backtest-kr` / `v2-backtest-us` 양쪽을 1회씩 실행해야 4개 그룹 모두 표시됨. 이후부터는 각각 따로 실행해도 데이터 유지.

---

## 2026-05-17

### backtest 기간 설정 config화 — config/periods.yml + candle backtest-all

- **배경** : Makefile에 `2000-2015`, `2010-2020`, `5y`, `full` 4개 기간이 하드코딩되어 있어 기간 추가 시 Makefile 직접 수정이 필요했던 문제.
- **신규 파일** (`config/periods.yml`)
  - `workers`: 0 = 기간 수 만큼 병렬(기본), 1 = 순차 실행.
  - 기간별 필드: `label`, `from`, `to`, `rolling`, `markets`.
  - `rolling: "5y"` 형식: 실행 시점 기준 N년 전 날짜 자동 계산.
  - `markets` 필드: `[all, kr, us]` 중 해당 시장에만 실행 (v2-backtest-kr 실행 시 `kr` 기준 필터).
  - **기간 추가 방법**: 이 파일에 항목 하나 추가하면 Makefile 수정 불필요.
- **수정** (`src/candle/config.py`)
  - `Config.periods: dict[str, Any]` 필드 추가.
  - `_load_periods()`: `config/periods.yml` 로드 (파일 없으면 `{}`).
  - `backtest_periods` 프로퍼티: 전체 기간 목록.
  - `backtest_periods_for_market(market)`: `markets` 필드 기준 필터링 반환.
- **수정** (`src/candle/cli.py`)
  - `_resolve_rolling("5y")` 헬퍼: 실행 시점 N년 전 `date` 반환.
  - `_period_task(task: dict) → str` 모듈레벨 함수: `ProcessPoolExecutor` worker 용.
    - `task` 키: `label, start_str, end_str, type_list, market, debug`.
    - 프로세스별 `config.load()` 재호출 → backtest + compare 순차 실행.
  - `candle backtest-all` 커맨드 신규:
    - `--market [all|kr|us]`, `--workers N` (0 = yml값, 1 = 순차), `--debug`.
    - workers 우선순위: CLI `--workers` > `periods.yml workers` > `len(periods)` (병렬 최대).
    - `workers > 1` 시 `ProcessPoolExecutor` 병렬 실행 → 기존 `make -j` 동작과 동일.
- **수정** (`Makefile`)
  - `v2-backtest` → `uv run candle backtest-all --market all`
  - `v2-backtest-kr` → `uv run candle backtest-all --market kr`
  - `v2-backtest-us` → `uv run candle backtest-all --market us`
  - 기존 `v2-backtest-compare-{label}` 개별 타겟은 수동 단일 실행용으로 유지.
- **검증** : `uv run candle backtest-all --help` 정상. workers 동작 확인(`market=all` 시 `effective workers=4`).

---

## 2026-05-19

### compare instruments.csv 미등록 ticker 필터링 (UNKNOWN 그룹 제거)

- **증상** : compare 전략별 요약 및 상위 10% 섹션에 `UNKNOWN` 그룹이 나타남.
- **원인** : `instruments.csv`가 업데이트되면서 기존 백테스트에서 사용한 일부 ticker(예: 삼성전자우, 맥쿼리인프라, SK가스 등 편출 종목)가 신규 instruments.csv에서 제외. 이들이 group_name을 찾지 못해 UNKNOWN으로 분류.
- **수정** (`src/candle/compare/run.py`)
  - `run()` 진입부에서 `instruments.csv` 로드 후 `ticker` set 구성.
  - `summary_df`를 해당 set에 있는 ticker만 필터링 (`_valid_tickers`).
  - 제외된 건수 tprint 출력.
- **검증** : 2000-2015 기간에서 22개 ticker 제외 → UNKNOWN 그룹 사라짐.

### compare 상위 10% 섹션 전면 개편

- **배경** : 기존 팝업 패널 방식 → 각 전략 행 클릭 시 토글. 분모도 비영리 수익률 종목만 사용(valid_df).
- **수정** (`src/candle/dashboard/render.py` `_load_compare_top10`)
  - 반환 구조: `{period: {type_col: {group_name: {group_size, top_n, tickers}}}}`
  - 분모: `len(grp_df)` (그룹 전체 종목 수, 비영리 필터 제거)
  - NaN 포함 전체 정렬 후 상위 10% 추출.
- **수정** (`src/candle/dashboard/templates/compare.html`)
  - 기존 팝업/CMP_TOP10 JS 변수 완전 제거.
  - 독립 `<section>` 으로 분리.
  - **2단계 탭**: 1단계=기간 탭(border-b 스타일) / 2단계=전략 탭(pill 스타일, Alpine.js nested x-data).
  - **2×2 그리드 레이아웃**: 행1=(ETF_KR|ETF_US, amber 헤더) / 행2=(KOSPI200|SP500, sky 헤더, max-h-96 스크롤+sticky thead).
  - 각 종목에 거래이력 버튼 (ticker_trades.html#TICKER:type_col 링크).

### compare 상위 10% 테이블 — 매수/매도/보유일/RANK 컬럼 추가

- **배경** : 상위 10% 표에 수익률 외 추가 지표 요구.
- **수정** (`src/candle/dashboard/render.py` `_load_compare_top10`)
  - `output/backtest/{period}/{type_col}/_summary.csv` 로드 → `bt_buy_sell` dict: `{type_name: {ticker: (buy_count, sell_count)}}`.
  - `output/compare/{period}/best_strategy.csv` 로드 → `rank_by_ticker` dict: `{ticker: 최고전략_매수일_시총순위}`.
  - 각 ticker dict에 `buy_count`, `sell_count`, `avg_hold_days`, `market_rank` 추가.
- **수정** (`src/candle/dashboard/templates/compare.html`)
  - ETF / KOSPI200·SP500 두 블록 모두 thead에 `매수`, `매도`, `보유일`, `RANK` 컬럼 추가.
  - None/0 fallback은 `—` 표시.

### 거래 이력 차트 — equity 라인(평가액+현금) + 축 색상 적용

- **사용자 요청** : 보유수량×종가+현금 equity 라인 표시 + 차트 축별 색상 구분.
- **수정** (`src/candle/dashboard/templates/ticker_trades.html`)
  - `cashArr`: trades의 마지막 cash 값을 날짜별로 forward-fill.
  - `equityArr`: `holdingQty × close + cash` (cash null이면 null).
  - 새 dataset `평가액+현금`: `borderColor=rgb(99,102,241)`, `yAxisID='yEquity'`, `order=6`.
  - tooltip: 매수/매도 마커에 `평가액+현금` 값 표시.
  - `yPrice` 축: 라벨 색 `rgb(71,85,105)` (slate).
  - `yQty` 축: `display: false` → **`true`**, 색 `rgba(34,197,94,0.85)` (green), 제목 '보유수량'.
  - `yEquity` 축: 색 `rgb(99,102,241)` (indigo), 제목 '평가액+현금'.
