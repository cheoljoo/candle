.PHONY: fetch analyze all clean help

help:
	@echo "사용 가능한 명령:"
	@echo "  make fetch    - 데이터 수집 (fetch_data.py)"
	@echo "  make analyze  - 분석 실행 (analyze.py)"
	@echo "  make all      - 데이터 수집 후 분석"
	@echo "  make clean    - 수집된 데이터 삭제"

fetch:
	uv run python fetch_data.py | tee log-fetch.log

analyze:
	uv run python analyze.py | tee log-analyze.log

all: fetch analyze

clean:
	rm -rf data/stocks data/kospi_list.csv
