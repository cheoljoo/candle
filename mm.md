feat: backtest 기간 config화(periods.yml) + Chart.js 차트 + 전략설명 + Buy-Sell 수익률

## config/periods.yml 신규 — backtest 기간 정의
- 기간별 label / from / to / rolling / markets 필드
- rolling: "5y" 지원 (실행 시점 N년 전 날짜 자동 계산)
- workers: 0 = 기간 수 만큼 병렬(기본), 1 = 순차

## src/candle/config.py — periods 지원 추가
- `Config.periods` 필드, `_load_periods()`, `backtest_periods` 프로퍼티
- `backtest_periods_for_market(market)` 메서드: markets 필드 기준 필터링

## src/candle/cli.py — candle backtest-all 커맨드 신규
- `_resolve_rolling("5y")`: N년 전 date 반환
- `_period_task(task)`: ProcessPoolExecutor worker 함수
- `candle backtest-all --market all|kr|us --workers N`
  - workers: CLI > periods.yml > len(periods) (병렬 최대)
  - workers > 1 시 ProcessPoolExecutor 병렬 실행 (make -j 동등)

## Makefile — v2-backtest{,-kr,-us} 커맨드 수정
- `$(MAKE) -j ...` → `uv run candle backtest-all --market {all|kr|us}`
- 기존 v2-backtest-compare-{label} 수동 단일 실행 타겟 유지

