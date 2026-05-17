feat: enabled_types·worker기본값·market calendar·decisions날짜·전략설명 수정 (2026-05-17)

## config.py — enabled_types / disabled_types 프로퍼티
- `ALL_TYPES` 상수 추가 (type1_1~type3 고정 순서)
- `enabled_types`: strategies.yml의 enabled_types → ALL_TYPES 순서로 필터링. 없으면 전체 7개 하위호환
- `disabled_types`: enabled에 없는 비활성 type 목록

## cli.py — Worker 기본값 CPU×1/2 + enabled_types 연동
- `_DEFAULT_WORKERS = max(1, (os.cpu_count() or 4) // 2)` — fetch/optimize-streak/backtest/compare 공통 적용
- `backtest --types`, `compare --types`: 미지정 시 `cfg.enabled_types` 사용
- `simulate`: `rule_types=cfg.enabled_types` 전달

## simulate/run.py + _type_legend.html
- `rule_types` 파라미터 수용 → enabled types만 신호 평가
- _type_legend.html: enabled/disabled 뱃지 스타일 분리

## optimize/streak_grid.py — --debug 없이도 진행 상황 출력
- 핵심 진행 메시지들(`_debug_log(debug, ...)` → `tprint(...)`)로 변경
- 변경 위치: 로딩 시작/완료(100개 단위), 그룹별 grid search 시작/완료, combo 진행(20개 단위 elapsed+ETA), per-ticker 종목별 완료

## dashboard/render.py — 전략 설명 + ON/OFF 뱃지 + best_type 필터
- type 설명 수정: "전액매수" → "전액매수·전량매도", "고정수량" → "고정수량 매수·매도"
- `enabled_types`, `disabled_types` → common_ctx 추가
- best_type: enabled_types 기준으로 결정
- `_dow_fmt` Jinja2 필터 추가 (YYYY-MM-DD → YYYY-MM-DD (요일))
- group_returns.html: disabled type 행 `opacity-50 bg-slate-300` ON/OFF 뱃지

## fetch/run.py + storage/paths.py — market calendar 수집
- `paths.market_calendar_csv(data_dir)` 추가 → `data/market_calendar.csv`
- `_build_market_calendar(data_dir, market)`:
  - 증분 업데이트: 기존 calendar max_date 이후만 집계
  - 속도 최적화: 파일별 마지막 줄만 읽어 비교 (22초 → 1.5초)
  - 컬럼: `date, is_kr_trading, is_us_trading`
- fetch 완료 후 KR/US 자동 호출

## simulate/engine.py — decisions date = 신호 확인일(마지막 거래일)
- rule decisions: `"date": on_date.isoformat()` → `"date": str(cur_row.get("date", on_date.isoformat()))`
- `event_date` 컬럼 추가: type1=변곡점 발생일, type2=streak 시작일
- decisions.csv 스키마: `decision_id, date, ticker, source, action, qty, price, reason, event_date, raw_json_path`

## decisions.html — 날짜 칼럼 주/부 표시 교체
- 주 표시: `date (요일)` (마지막 거래일, 신호 확인일)
- 부 표시: `event_date` (연속 시작일, 다를 때만)
- `dow_fmt` 필터 적용
