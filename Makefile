.PHONY: fetch analyze backtest-type1 backtest-type1-2020-2025 backtest-type1-2025-now backtest-type1-2 backtest-type2 backtest-type4 backtest-type4-2 backtest-compare all clean help

help:
	@echo "사용 가능한 명령:"
	@echo "  make fetch    - 데이터 수집 (fetch_data.py)"
	@echo "  make analyze  - 분석 실행 (analyze.py)"
	@echo "  make backtest-type1 - type1 백테스트 실행 (기본: 올해 01-01 ~ 오늘)"
	@echo "  make backtest-type1-2020-2025 - type1 백테스트 (2020-01-01 ~ 2025-12-31)"
	@echo "  make backtest-type1-2025-now  - type1 백테스트 (2025-01-01 ~ 오늘)"
	@echo "  make backtest-type1-2 - type1-2 백테스트 실행 (현금 추적: 가용 현금으로 최대 주수 매수)"
	@echo "  make backtest-type2 - type2 백테스트 실행 (기본: plus/minus 연속일수 1)"
	@echo "  make backtest-type4 - 시가총액 상위 조건 기반 type4 백테스트"
	@echo "  make backtest-type4-2 - type4-2 백테스트 실행 (시총 조건 + 현금 추적)"
	@echo "  make backtest-compare - 동일 초기자금 기준 type1/type2/type3 비교"
	@echo "  make all      - 데이터 수집 후 분석"
	@echo "  make clean    - 수집된 데이터 삭제"

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
