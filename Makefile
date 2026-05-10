SHELL := /bin/bash

# ── DEBUG 플래그 ───────────────────────────────────────────────────────────
# 기본값: 비어 있음 (debug 없음)
# debug 켜기: make <target> DEBUG=--debug
DEBUG ?=

.PHONY: fetch analyze backtest-type1 backtest-type1-2020-2025 backtest-type1-2025-now \
        backtest-type1-2 backtest-type2 backtest-type4 backtest-type4-2 backtest-compare \
        all clean help \
        v2-universe v2-universe-small \
        v2-fetch v2-fetch-full \
        v2-analyze v2-analyze-refresh \
        v2-backtest v2-backtest-full v2-backtest-5y \
        v2-compare v2-compare-full v2-compare-5y \
        v2-backtest-compare-full v2-backtest-compare-5y \
        v2-backtest-compare-2010-2020 v2-backtest-compare-2000-2015 \
        v2-simulate v2-simulate-noai \
        v2-dashboard \
        v2-optimize \
        v2-smoke v2-all

# ── 구형 v1 타겟 ───────────────────────────────────────────────────────────
help:
	@echo "=== Candle v2 — 추세추종 자동 투자 시스템 ==="
	@echo ""
	@echo "전체 파이프라인:"
	@echo "  make v2-all                       - universe→fetch(full)→analyze→backtest→simulate→dashboard"
	@echo "  make v2-all DEBUG=--debug         - 위 + 단계별 상세 출력"
	@echo ""
	@echo "단계별 실행:"
	@echo "  make v2-universe                  - 종목 목록 갱신 (KOSPI200/SP500/ETF)"
	@echo "  make v2-fetch                     - 오늘치 증분 fetch"
	@echo "  make v2-fetch-full                - 2000-01-01부터 전체 fetch"
	@echo "  make v2-analyze                   - 증분 분석 (새 row 자동 감지)"
	@echo "  make v2-analyze-refresh           - 전체 재분석 (백필 후 1회 실행)"
	@echo "  make v2-backtest                  - 기간별 backtest+compare 병렬 실행"
	@echo "  make v2-simulate                  - 오늘 의사결정 (rule+AI+manual)"
	@echo "  make v2-simulate-noai             - AI 없이 rule+manual만"
	@echo "  make v2-dashboard                 - HTML 대시보드 재생성"
	@echo ""
	@echo "Backtest 기간별 타겟:"
	@echo "  make v2-backtest-compare-full     - 2000-01-01~ backtest+compare"
	@echo "  make v2-backtest-compare-5y       - 최근 5년 backtest+compare"
	@echo "  make v2-backtest-compare-2010-2020 - 2010~2020 고정 기간"
	@echo "  make v2-backtest-compare-2000-2015 - 2000~2015 고정 기간"
	@echo ""
	@echo "파라미터 최적화 (v2-all 미포함 — 수동 실행):"
	@echo "  make v2-optimize                  - plus 4~40 step2 × minus 4~10 step2 = 76조합"
	@echo "  make v2-optimize DEBUG=--debug    - 위 + 상세 출력"
	@echo ""
	@echo "기타:"
	@echo "  make v2-smoke                     - 소규모 universe로 전체 파이프라인 검증"
	@echo "  make v2-universe-small            - dev용 소규모 universe 빌드"
	@echo ""
	@echo "옵션: DEBUG=--debug  (예: make v2-fetch DEBUG=--debug)"

fetch:
	set -o pipefail; uv run python -u fetch_data.py | tee log-fetch.log

analyze:
	set -o pipefail; uv run python -u analyze.py | tee log-analyze.log
	uv run python -u gmail_sender.py --subject="[candle] 변곡정 분석" --body-file="./log-analyze.log" --attach-file="./data/inflection_points.csv"

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
	uv run python -u gmail_sender.py --subject="[candle] backtest type2 :  2024.01.01~  규칙: -→+ 직후 즉시 매수하지 않고 + 1일 연속 확인 후 10주 매수 / +→- 직후 즉시 매도하지 않고 - 1일 연속 확인 후 전량 매도" --body-file="./log-backtest-type2.log" --attach-file="./backtest_type2.csv"

backtest-type1-2:
	set -o pipefail; uv run python -u backtest_type1_2.py | tee log-backtest-type1-2.log

backtest-type4:
	set -o pipefail; uv run python -u backtest_type4.py | tee log-backtest-type4.log
	uv run python -u gmail_sender.py --subject="[candle] backtest type4 :  2024.01.01~  규칙: KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 + 신호만 매수, - 신호면 매도" --body-file="./log-backtest-type4.log" --attach-file="./backtest_type4.csv"

backtest-type4-2:
	set -o pipefail; uv run python -u backtest_type4_2.py | tee log-backtest-type4-2.log

backtest-compare:
	set -o pipefail; uv run python -u backtest_compare.py | tee log-backtest-compare.log
	uv run python -u gmail_sender.py --subject="[candle] backtest compare" --body-file="./log-backtest-compare.log" --attach-file="./backtest_compare.csv"

all: fetch analyze backtest-type1 backtest-type2 backtest-type4 backtest-compare

clean:
	rm -rf data/stocks data/kospi_list.csv

# ── v2 (src/candle 패키지) ─────────────────────────────────────────────────
# 모든 v2 명령에 $(DEBUG) 가 붙습니다.
# debug 켜기: make <target> DEBUG=--debug
# 예) make v2-fetch DEBUG=--debug
#     make v2-all   DEBUG=--debug

v2-universe:
	uv run candle universe --market all $(DEBUG)

v2-universe-small:
	uv run candle universe --small $(DEBUG)

v2-fetch:
	uv run candle fetch --market all $(DEBUG)

v2-fetch-full:
	uv run candle fetch --market all --from 2000-01-01 --workers 4 --timeout 30 $(DEBUG)

v2-analyze:
	uv run candle analyze --market all $(DEBUG)

v2-analyze-refresh:
	uv run candle analyze --market all --refresh $(DEBUG)

# ── backtest 단독 (수동 실행용) ────────────────────────────────────────────
# output/backtest/full/   output/backtest/5y/
v2-backtest-full:
	uv run candle backtest --from 2000-01-01 --label full --market all $(DEBUG)

v2-backtest-5y:
	uv run candle backtest --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y --market all $(DEBUG)

# ── compare 단독 (수동 실행용) ─────────────────────────────────────────────
v2-compare:
	uv run candle compare $(DEBUG)

v2-compare-full:
	uv run candle compare --from 2000-01-01 --label full $(DEBUG)

v2-compare-5y:
	uv run candle compare --from $$(date -d '5 years ago' +%Y-%m-%d) --label 5y $(DEBUG)

# ── backtest + compare 묶음 (label 기반, 순차 실행) ───────────────────────
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

# ── 병렬 실행 (v2-all 에서 사용) ───────────────────────────────────────────
# full, 5y, 2010-2020 이 동시에 돌고, 각각 내부에서 backtest → compare 순으로 실행됨
# 2000-2015 를 추가하려면 아래 줄 끝에 v2-backtest-compare-2000-2015 를 추가
v2-backtest:
	$(MAKE) -j v2-backtest-compare-full v2-backtest-compare-5y v2-backtest-compare-2010-2020 v2-backtest-compare-2000-2015 DEBUG="$(DEBUG)"

v2-simulate:
	uv run candle simulate $(DEBUG)

v2-simulate-noai:
	uv run candle simulate --no-ai $(DEBUG)

v2-dashboard:
	uv run candle dashboard $(DEBUG)

# ── optimize (v2-all 에 미포함 — 수동 실행) ───────────────────────────────
# plus_days: 4~40 step 2 (19가지), minus_days: 4~10 step 2 (4가지) → 76 조합
# 결과: output/optimize/streak_grid.csv + 상위 30개 터미널 출력
v2-optimize:
	mkdir -p output/optimize
	uv run candle optimize-streak \
		--market all \
		--plus-min 4 --plus-max 40 --plus-step 2 \
		--minus-min 4 --minus-max 10 --minus-step 2 \
		--top 30 \
		--output output/optimize/streak_grid.csv \
		$(DEBUG)

# ── smoke (소규모 universe 빠른 검증) ─────────────────────────────────────
v2-smoke:
	uv run candle universe --small $(DEBUG)
	uv run candle fetch --market all $(DEBUG)
	uv run candle analyze --market all $(DEBUG)
	uv run candle backtest --market all $(DEBUG)
	uv run candle compare $(DEBUG)
	uv run candle simulate --no-ai $(DEBUG)
	uv run candle dashboard $(DEBUG)

# ── 전체 파이프라인 ────────────────────────────────────────────────────────
# backtest / compare 내부에서 병렬 처리됨
v2-all: v2-universe v2-fetch-full v2-analyze v2-backtest v2-simulate v2-dashboard
