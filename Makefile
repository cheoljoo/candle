.PHONY: fetch analyze backtest-type1 backtest-type1-2020-2025 backtest-type1-2025-now backtest-type2 backtest-type4 backtest-compare all clean help

help:
	@echo "사용 가능한 명령:"
	@echo "  make fetch    - 데이터 수집 (fetch_data.py)"
	@echo "  make analyze  - 분석 실행 (analyze.py)"
	@echo "  make backtest-type1 - type1 백테스트 실행 (기본: 올해 01-01 ~ 오늘)"
	@echo "  make backtest-type1-2020-2025 - type1 백테스트 (2020-01-01 ~ 2025-12-31)"
	@echo "  make backtest-type1-2025-now  - type1 백테스트 (2025-01-01 ~ 오늘)"
	@echo "  make backtest-type2 - type2 백테스트 실행 (기본: plus/minus 연속일수 1)"
	@echo "  make backtest-type4 - 시가총액 상위 조건 기반 type4 백테스트"
	@echo "  make backtest-compare - 동일 초기자금 기준 type1/type2/type3 비교"
	@echo "  make all      - 데이터 수집 후 분석"
	@echo "  make clean    - 수집된 데이터 삭제"

fetch:
	uv run python -u fetch_data.py | tee log-fetch.log

analyze:
	uv run python -u analyze.py | tee log-analyze.log

backtest-type1:
	uv run python -u backtest_type1.py | tee log-backtest-type1.log

backtest-type1-2020-2025:
	uv run python -u backtest_type1.py --from 2020-01-01 --to 2025-12-31 --output_csv data/backtest_type1_2020_2025.csv | tee log-backtest-type1-2020-2025.log

backtest-type1-2025-now:
	uv run python -u backtest_type1.py --from 2025-01-01 --to $$(date +%F) --output_csv data/backtest_type1_2025_now.csv | tee log-backtest-type1-2025-now.log

backtest-type1-2026-04--now:
	uv run python -u backtest_type1.py --from 2026-04-01 --to $$(date +%F) --output_csv data/backtest_type1_2026_04_now.csv | tee log-backtest-type1-2026-04-now.log

backtest-type2:
	uv run python -u backtest_type2.py | tee log-backtest-type2.log

backtest-type4:
	uv run python -u backtest_type4.py | tee log-backtest-type4.log

backtest-compare:
	uv run python -u backtest_compare.py | tee log-backtest-compare.log

all: fetch analyze backtest-type1 backtest-type2

clean:
	rm -rf data/stocks data/kospi_list.csv
