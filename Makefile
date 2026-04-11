.PHONY: fetch analyze backtest-type1 backtest-type1-2020-2025 backtest-type1-2025-now all clean help

help:
	@echo "사용 가능한 명령:"
	@echo "  make fetch    - 데이터 수집 (fetch_data.py)"
	@echo "  make analyze  - 분석 실행 (analyze.py)"
	@echo "  make backtest-type1 - type1 백테스트 실행 (기본: 올해 01-01 ~ 오늘)"
	@echo "  make backtest-type1-2020-2025 - type1 백테스트 (2020-01-01 ~ 2025-12-31)"
	@echo "  make backtest-type1-2025-now  - type1 백테스트 (2025-01-01 ~ 오늘)"
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

all: fetch analyze

clean:
	rm -rf data/stocks data/kospi_list.csv
