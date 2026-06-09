SHELL := /bin/bash

# ── 플래그 ────────────────────────────────────────────────────────────────────
# debug 켜기:    make <target> DEBUG=--debug
# 메일 발송 켜기: make <target> SENDMAIL=YES
DEBUG    ?=
SENDMAIL ?= YES


.PHONY: fetch analyze backtest-type1 backtest-type1-2020-2025 backtest-type1-2025-now \
        backtest-type1-2 backtest-type2 backtest-type4 backtest-type4-2 backtest-compare \
        all clean help \
        v2-universe v2-universe-small \
        v2-fetch v2-fetch-full v2-fetch-kr v2-fetch-us \
        v2-analyze v2-analyze-refresh v2-analyze-kr v2-analyze-us \
        v2-backtest v2-backtest-full v2-backtest-5y \
        v2-backtest-kr v2-backtest-us \
        v2-compare v2-compare-full v2-compare-5y \
        v2-backtest-compare-full v2-backtest-compare-5y \
        v2-backtest-compare-2010-2020 v2-backtest-compare-2000-2015 \
        v2-backtest-compare-full-kr v2-backtest-compare-5y-kr \
        v2-backtest-compare-full-us v2-backtest-compare-5y-us \
        v2-simulate v2-simulate-noai \
        v2-dashboard \
        v2-mail v2-mail-me \
        v2-optimize \
        v2-gmail-etf v2-gmail-etf-dry \
        v2-market-signals v2-market-signals-us \
        v2-foreign-trading \
        v2-smoke v2-all v2-all-kr v2-all-us \
        v2-check-traceback

# ── 도움말 ────────────────────────────────────────────────────────────────────
help:
	@echo "=== Candle v2 — 추세추종 자동 투자 시스템 ==="
	@echo ""
	@echo "전체 파이프라인:"
	@echo "  make v2-all                         - universe→fetch(full)→analyze→backtest→simulate→dashboard"
	@echo "  make v2-all SENDMAIL=YES            - 위 + 완료 후 전체 수신자에게 메일 발송"
	@echo "  make v2-all DEBUG=--debug           - 위 + 단계별 상세 출력"
	@echo "  make v2-all DEBUG=--debug SENDMAIL=YES - 디버그 + 메일 발송"
	@echo ""
	@echo "시장별 분리 파이프라인:"
	@echo "  make v2-all-kr                      - KR 전용: fetch→analyze→backtest→simulate→market-signals→dashboard (한국장 종료 ~16:00 KST)" 
	@echo "  make v2-all-us                      - US 전용: fetch→analyze→backtest→simulate→dashboard (미국장 종료 ~09:00 KST)"
	@echo "  make v2-all-kr SENDMAIL=YES         - 위 + 완료 후 메일 발송"
	@echo "  make v2-all-us SENDMAIL=YES         - 위 + 완료 후 메일 발송"
	@echo ""
	@echo "단계별 실행:"
	@echo "  make v2-universe                    - 종목 목록 갱신 (KOSPI200/SP500/ETF)"
	@echo "  make v2-fetch                       - 오늘치 증분 fetch (all)"
	@echo "  make v2-fetch-kr                    - KR 증분 fetch만"
	@echo "  make v2-fetch-us                    - US 증분 fetch만"
	@echo "  make v2-fetch-full                  - 2000-01-01부터 전체 fetch"
	@echo "  make v2-analyze-kr                  - KR 증분 분석만"
	@echo "  make v2-analyze-us                  - US 증분 분석만"
	@echo "  make v2-backtest-kr                 - KR backtest+compare (full/5y 병렬)"
	@echo "  make v2-backtest-us                 - US backtest+compare (full/5y 병렬)"
	@echo "  make v2-analyze                     - 증분 분석 (새 row 자동 감지)"
	@echo "  make v2-analyze-refresh             - 전체 재분석 (백필 후 1회 실행)"
	@echo "  make v2-backtest                    - 기간별 backtest+compare 병렬 실행"
	@echo "  make v2-simulate                    - 오늘 의사결정 (rule+AI+manual)"
	@echo "  make v2-simulate-noai               - AI 없이 rule+manual만"
	@echo "  make v2-dashboard                   - HTML 대시보드 재생성"
	@echo ""
	@echo "Backtest 기간별 타겟 (수동 단일 실행용):"
	@echo "  make v2-backtest-compare-full       - 2000-01-01~ backtest+compare"
	@echo "  make v2-backtest-compare-5y         - 최근 5년 backtest+compare"
	@echo "  make v2-backtest-compare-2010-2020  - 2010~2020 고정 기간"
	@echo "  make v2-backtest-compare-2000-2015  - 2000~2015 고정 기간"
	@echo "  (기간 추가: config/periods.yml 에만 항목 추가 → Makefile 수정 불필요)"
	@echo ""
	@echo "메일 발송 (config/recipients.yml 기반 개별 To:):"
	@echo "  make v2-mail                        - 전체 수신자 발송 (decisions.json 자동 본문)"
	@echo "  make v2-mail-me                     - owner 에게만 테스트 발송"
	@echo ""
	@echo "파라미터 최적화 (v2-all 미포함 — 수동 실행):"
	@echo "  make v2-optimize                    - plus 4~40 step2 × minus 4~10 step2 = 76조합"
	@echo ""
	@echo "시장 시그널 (수동 실행):"
	@echo "  make v2-market-signals              - 프로그램 비차익 순매도 + 금융투자 연속 순매도 확인 (증분 포집)"
	@echo ""
	@echo "기타:"
	@echo "  make v2-smoke                       - 소규모 universe로 전체 파이프라인 검증"
	@echo "  make v2-universe-small              - dev용 소규모 universe 빌드"
	@echo ""
	@echo "에러 감지:"
	@echo "  make v2-check-traceback             - crontab.log에 Traceback 존재 시 owner에게 경보 메일 발송"
	@echo ""
	@echo "옵션:"
	@echo "  DEBUG=--debug    단계별 상세 출력  (예: make v2-fetch DEBUG=--debug)"
	@echo "  SENDMAIL=YES     완료 후 메일 발송 (예: make v2-all SENDMAIL=YES)"

# ── 구형 v1 타겟 (하위 호환) ──────────────────────────────────────────────────
fetch:
	set -o pipefail; uv run python -u fetch_data.py | tee log-fetch.log

analyze:
	set -o pipefail; uv run python -u analyze.py | tee log-analyze.log
	uv run python -u gmail_sender.py --subject="[candle] 변곡점 분석" --body-file="./log-analyze.log" --attach-file="./data/inflection_points.csv"

backtest-type1:
	set -o pipefail; uv run python -u backtest_type1.py | tee log-backtest-type1.log
	uv run python -u gmail_sender.py --subject="[candle] backtest type1 :  2024.01.01~  규칙: -→+ 10주 매수 / +→- 전량 매도 / 미청산은 --to 기준 평가" --body-file="./log-backtest-type1.log" --attach-file="./backtest_type1.csv"

backtest-type1-2020-2025:
	set -o pipefail; uv run python -u backtest_type1.py --from 2020-01-01 --to 2025-12-31 --output_csv data/backtest_type1_2020_2025.csv | tee log-backtest-type1-2020-2025.log

backtest-type1-2025-now:
	set -o pipefail; uv run python -u backtest_type1.py --from 2025-01-01 --to $$(date +%F) --output_csv data/backtest_type1_2025_now.csv | tee log-backtest-type1-2025-now.log

backtest-type1-2026-04--now:
	set -o pipefail; uv run python -u backtest_type1.py --from 2026-04-01 --to $$(date +%F) --output_csv data/backtest_type1_2026_04_now.csv | tee log-backtest-type1-2026-04-now.log

backtest-type2:
	set -o pipefail; uv run python -u backtest_type2.py | tee log-backtest-type2.log
	uv run python -u gmail_sender.py --subject="[candle] backtest type2" --body-file="./log-backtest-type2.log" --attach-file="./backtest_type2.csv"

backtest-type1-2:
	set -o pipefail; uv run python -u backtest_type1_2.py | tee log-backtest-type1-2.log

backtest-type4:
	set -o pipefail; uv run python -u backtest_type4.py | tee log-backtest-type4.log
	uv run python -u gmail_sender.py --subject="[candle] backtest type4" --body-file="./log-backtest-type4.log" --attach-file="./backtest_type4.csv"

backtest-type4-2:
	set -o pipefail; uv run python -u backtest_type4_2.py | tee log-backtest-type4-2.log

backtest-compare:
	set -o pipefail; uv run python -u backtest_compare.py | tee log-backtest-compare.log
	uv run python -u gmail_sender.py --subject="[candle] backtest compare" --body-file="./log-backtest-compare.log" --attach-file="./backtest_compare.csv"

all: fetch analyze backtest-type1 backtest-type2 backtest-type4 backtest-compare

clean:
	rm -rf data/stocks data/kospi_list.csv

# ── v2 (src/candle 패키지) ────────────────────────────────────────────────────
# 모든 v2 명령에 $(DEBUG) 가 붙습니다.
# debug 켜기:    make <target> DEBUG=--debug
# 메일 발송 켜기: make <target> SENDMAIL=YES

v2-universe:
	set -o pipefail; uv run candle universe --market all $(DEBUG) | tee v2-universe.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-universe.log" --body-file="./v2-universe.log" --only-me --sendmail "$(SENDMAIL)"

v2-universe-small:
	set -o pipefail; uv run candle universe --small $(DEBUG) | tee v2-universe-small.log

v2-fetch:
	set -o pipefail; uv run candle fetch --market all $(DEBUG) | tee v2-fetch.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-fetch.log" --body-file="./v2-fetch.log" --only-me --sendmail "$(SENDMAIL)"

v2-fetch-full:
	# --from DATE 옵션을 명시적으로 지정하면 기존 파일이 있어도 그 날짜부터 재수집합니다. make v2-fetch-full이 이 방식(--from 2000-01-01)을 사용합니다.
	set -o pipefail; uv run candle fetch --market all --from 2000-01-01 --timeout 30 $(DEBUG) | tee v2-fetch-full.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-fetch-full.log" --body-file="./v2-fetch-full.log" --only-me --sendmail "$(SENDMAIL)"

v2-analyze:
	set -o pipefail; uv run candle analyze --market all $(DEBUG) | tee v2-analyze.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-analyze.log" --body-file="./v2-analyze.log" --only-me --sendmail "$(SENDMAIL)"

v2-analyze-refresh:
	set -o pipefail; uv run candle analyze --market all --refresh $(DEBUG) | tee v2-analyze-refresh.log

# ── backtest 단독 (수동 실행용) ────────────────────────────────────────────────
v2-backtest-full:
	set -o pipefail; uv run candle backtest --from 2000-01-01 --label full --market all $(DEBUG) | tee v2-backtest-full.log

v2-backtest-5y:
	set -o pipefail; uv run candle backtest --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y --market all $(DEBUG) | tee v2-backtest-5y.log

# ── compare 단독 (수동 실행용) ─────────────────────────────────────────────────
v2-compare:
	set -o pipefail; uv run candle compare $(DEBUG) | tee v2-compare.log

v2-compare-full:
	set -o pipefail; uv run candle compare --from 2000-01-01 --label full $(DEBUG) | tee v2-compare-full.log

v2-compare-5y:
	set -o pipefail; uv run candle compare --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y $(DEBUG) | tee v2-compare-5y.log

# ── backtest + compare 묶음 (label 기반, 순차 실행) ───────────────────────────
# --label 로 고정 디렉터리명 사용 → 내년에도 같은 label 이 같은 디렉터리에 갱신됨
# 새 기간 추가 시:
#   1) v2-backtest-compare-<label> 타겟 정의
#   2) v2-backtest 의 $(MAKE) -j 줄에 추가

# output/backtest/full/       ← 2000-01-01 ~ 오늘 (매일 갱신, 롤링)
v2-backtest-compare-full:
	uv run candle backtest --from 2000-01-01 --label full --market all $(DEBUG)
	uv run candle compare  --from 2000-01-01 --label full $(DEBUG)

# output/backtest/5y/         ← 5년 전 ~ 오늘 (매일 갱신, 롤링)
v2-backtest-compare-5y:
	uv run candle backtest --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y --market all $(DEBUG)
	uv run candle compare  --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y $(DEBUG)

# output/backtest/2010-2020/  ← 고정 기간 (2010-01-01 ~ 2021-01-01)
v2-backtest-compare-2010-2020:
	uv run candle backtest --from 2010-01-01 --to 2021-01-01 --label 2010-2020 --market all $(DEBUG)
	uv run candle compare  --from 2010-01-01 --to 2021-01-01 --label 2010-2020 $(DEBUG)

# output/backtest/2000-2015/  ← 고정 기간 (2000-01-01 ~ 2016-01-01)
v2-backtest-compare-2000-2015:
	uv run candle backtest --from 2000-01-01 --to 2016-01-01 --label 2000-2015 --market all $(DEBUG)
	uv run candle compare  --from 2000-01-01 --to 2016-01-01 --label 2000-2015 $(DEBUG)

# ── 전체 기간 실행 (config/periods.yml 기반) ─────────────────────────────────────
# 기간 추가/변경: config/periods.yml 만 수정하면 자동 반영 (Makefile 수정 불필요)
v2-backtest:
	set -o pipefail; uv run candle backtest-all --market all $(DEBUG) | tee v2-backtest.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-backtest.log" --body-file="./v2-backtest.log" --only-me --sendmail "$(SENDMAIL)"

v2-simulate:
	set -o pipefail; uv run candle simulate $(DEBUG) | tee v2-simulate.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-simulate.log" --body-file="./v2-simulate.log" --only-me --sendmail "$(SENDMAIL)"

v2-simulate-noai:
	set -o pipefail; uv run candle simulate --no-ai $(DEBUG) | tee v2-simulate-noai.log

v2-dashboard:
	set -o pipefail; uv run candle dashboard $(DEBUG) | tee v2-dashboard.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-dashboard.log" --body-file="./v2-dashboard.log" --only-me --sendmail "$(SENDMAIL)"

# ── 전체 파이프라인 ────────────────────────────────────────────────────────────
# SENDMAIL=YES 설정 시 완료 후 전체 수신자에게 메일 발송
# 예) make v2-all SENDMAIL=YES
#     make v2-all DEBUG=--debug SENDMAIL=YES
v2-all-sendmail: v2-gmail-etf v2-universe v2-fetch v2-analyze v2-backtest v2-simulate v2-market-signals v2-dashboard v2-sendmail
v2-all: v2-gmail-etf v2-universe v2-fetch v2-analyze v2-backtest v2-simulate v2-market-signals v2-dashboard
v2-sendmail:
	uv run python -u gmail_sender.py \
		--sendmail "$(SENDMAIL)" \
		--subject="[candle][v2] $$(date +%Y-%m-%d) 투자 리포트" \
		--decisions-json="./dashboard_site/data/decisions.json"


# ── optimize (v2-all 에 미포함 — 수동 실행) ───────────────────────────────────
# type2_1b / type2_2b 의 plus_days(4~40 step2) × minus_days(4~10 step2) = 76 조합
# --all-groups: 전체 + KOSPI200/SP500/ETF_KR/ETF_US 5개 결과 파일 생성
#     전체 ticker를 1회만 로딩 (병렬)
#     ("all", 전체), ("KOSPI200", 필터), ("SP500", 필터), ("ETF_KR", 필터), ("ETF_US", 필터) 순서로 grid search 5번 실행
#     각 그룹별 streak_grid_{group}.csv 저장
#     추가로 각 그룹의 종목별(per-ticker) grid search도 실행 → output/optimize/per_ticker/{group}/{ticker}.csv
#     즉, --all-groups 없이 실행하면 전체 통합 결과(streak_grid_all.csv) 1개만 생성됩니다.
# 결과: output/optimize/streak_grid_{all|KOSPI200|SP500|ETF_KR|ETF_US}.csv
v2-optimize:
	mkdir -p output/optimize
	set -o pipefail; uv run candle optimize-streak \
		--all-groups \
		--output-dir output/optimize \
		--plus-min 1 --plus-max 39 --plus-step 2 \
		--minus-min 1 --minus-max 15 --minus-step 2 \
		--top 30 --workers 2  \
		$(DEBUG) | tee v2-optimize.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-optimize.log" --body-file="./v2-optimize.log" --only-me --sendmail "$(SENDMAIL)"
	make v2-dashboard

# ── gmail-etf (메일로 ETF ticker 등록 처리) ───────────────────────────────────
v2-gmail-etf:
	uv run candle gmail-etf $(DEBUG) | tee v2-gmail-etf.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-gmail-etf.log" --body-file="./v2-gmail-etf.log" --only-me --sendmail "$(SENDMAIL)"

v2-gmail-etf-dry:
	uv run candle gmail-etf --dry-run $(DEBUG)

# ── market-signals (프로그램/투자자 매매 시그널) ──────────────────────────────
v2-market-signals: v2-market-signals-kr v2-market-signals-us
v2-market-signals-kr:
	set -o pipefail; uv run candle market-signals $(DEBUG) | tee v2-market-signals-kr.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) market-signals-kr" --body-file="./v2-market-signals-kr.log" --only-me --sendmail "$(SENDMAIL)"

# ── foreign-trading (KOSPI200 종목별 외국인/기관 매매) ───────────────────────
v2-foreign-trading:
	set -o pipefail; uv run candle foreign-trading $(DEBUG) | tee v2-foreign-trading.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) foreign-trading" --body-file="./v2-foreign-trading.log" --only-me --sendmail "$(SENDMAIL)"

# ── market-signals-us (VIX + 미국채 수익률 곡선) ─────────────────────────────
v2-market-signals-us:
	set -o pipefail; uv run candle market-signals-us $(DEBUG) | tee v2-market-signals-us.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) market-signals-us" --body-file="./v2-market-signals-us.log" --only-me --sendmail "$(SENDMAIL)"

# ── KR 전용 단계 (한국장 종료 후 ~16:00 KST) ─────────────────────────────────
v2-fetch-kr:
	set -o pipefail; uv run candle fetch --market kr $(DEBUG) | tee v2-fetch-kr.log

v2-analyze-kr:
	set -o pipefail; uv run candle analyze --market kr $(DEBUG) | tee v2-analyze-kr.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-analyze-kr.log" --body-file="./v2-analyze-kr.log" --only-me --sendmail "$(SENDMAIL)"

v2-backtest-compare-full-kr:
	uv run candle backtest --from 2000-01-01 --label full --market kr $(DEBUG)
	uv run candle compare  --from 2000-01-01 --label full $(DEBUG)

v2-backtest-compare-5y-kr:
	uv run candle backtest --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y --market kr $(DEBUG)
	uv run candle compare  --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y $(DEBUG)

v2-backtest-kr:
	set -o pipefail; uv run candle backtest-all --market kr $(DEBUG) | tee v2-backtest-kr.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-backtest-kr.log" --body-file="./v2-backtest-kr.log" --only-me --sendmail "$(SENDMAIL)"

v2-sendmail-kr:
	uv run python -u gmail_sender.py \
		--sendmail "$(SENDMAIL)" \
		--subject="[candle][v2] $$(date +%Y-%m-%d) 투자 리포트 (한국 update)" \
		--decisions-json="./dashboard_site/data/decisions.json"

# ── US 전용 단계 (미국장 종료 후 ~09:00 KST) ──────────────────────────────────
v2-fetch-us:
	set -o pipefail; uv run candle fetch --market us $(DEBUG) | tee v2-fetch-us.log

v2-analyze-us:
	set -o pipefail; uv run candle analyze --market us $(DEBUG) | tee v2-analyze-us.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-analyze-us.log" --body-file="./v2-analyze-us.log" --only-me --sendmail "$(SENDMAIL)"

v2-backtest-compare-full-us:
	uv run candle backtest --from 2000-01-01 --label full --market us $(DEBUG)
	uv run candle compare  --from 2000-01-01 --label full $(DEBUG)

v2-backtest-compare-5y-us:
	uv run candle backtest --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y --market us $(DEBUG)
	uv run candle compare  --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y $(DEBUG)

v2-backtest-us:
	set -o pipefail; uv run candle backtest-all --market us $(DEBUG) | tee v2-backtest-us.log
	uv run python -u gmail_sender.py --subject="[candle][v2][progress] $$(date +%Y-%m-%d) v2-backtest-us.log" --body-file="./v2-backtest-us.log" --only-me --sendmail "$(SENDMAIL)"

v2-sendmail-us:
	uv run python -u gmail_sender.py \
		--sendmail "$(SENDMAIL)" \
		--subject="[candle][v2] $$(date +%Y-%m-%d) 투자 리포트 (미국 update)" \
		--decisions-json="./dashboard_site/data/decisions.json"

# ── KR 파이프라인 (한국장 종료 후 ~16:00 KST 실행) ────────────────────────────
# 순서: gmail-etf → fetch(KR) → analyze(KR) → backtest(KR) → simulate(전체) → market-signals → dashboard → 메일
v2-all-kr: v2-gmail-etf v2-fetch-kr v2-analyze-kr v2-backtest-kr v2-simulate v2-market-signals-kr v2-dashboard v2-sendmail-kr

# ── US 파이프라인 (미국장 종료 후 ~09:00 KST 실행) ────────────────────────────
# 순서: fetch(US) → analyze(US) → backtest(US) → simulate(전체) → market-signals-us → dashboard → 메일
v2-all-us: v2-fetch-us v2-analyze-us v2-backtest-us v2-simulate v2-market-signals-us v2-dashboard v2-sendmail-us

# ── smoke (소규모 universe 빠른 검증) ─────────────────────────────────────────
v2-smoke:
	uv run candle universe --small $(DEBUG)
	uv run candle fetch --market all $(DEBUG)
	uv run candle analyze --market all $(DEBUG)
	uv run candle backtest --market all $(DEBUG)
	uv run candle compare $(DEBUG)
	uv run candle simulate --no-ai $(DEBUG)
	uv run candle dashboard $(DEBUG)

# ── Traceback 감지 → owner 경보 메일 ─────────────────────────────────────────
# crontab 에서 파이프라인 실행 후 호출:
#   make v2-all-kr >> crontab.log 2>&1 && make v2-check-traceback
# crontab.log 에 Traceback 문자열이 있으면 프로세스가 비정상 종료된 것으로 판단하고
# owner(config/recipients.yml) 에게 경보 메일을 발송합니다.
v2-check-traceback:
	@if [ ! -f crontab.log ]; then \
		echo "crontab.log not found — skip traceback check"; \
	elif grep -q "Traceback" crontab.log; then \
		echo "[ALERT] Traceback detected in crontab.log — sending alert mail to owner"; \
		uv run python -u gmail_sender.py \
			--subject="[candle][ALERT][Traceback] $$(date +%Y-%m-%d) Traceback in crontab.log" \
			--body-file="./crontab.log" \
			--only-me \
			--sendmail "YES"; \
	else \
		echo "No Traceback found in crontab.log — OK"; \
	fi
