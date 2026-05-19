feat: add type0_2 buy-and-hold + type2_2_opt per-ticker optimized

- backtest/type0_2.py 신규: 첫 거래일 전액매수 후 보유, 매도 없음 (벤치마크)
- backtest/type2_2_opt.py 신규: type2_2 로직 + 종목별 최적화 plus/minus_days 사용
- backtest/run.py: _opt_params.json으로 파라미터 변경 감지 (변경 시 full 재계산)
  · _load_opt_params_current(): per_ticker/_summary.json → fallback=strategies.yml
  · _dispatch()/resume(): type0_2 + type2_2_opt 케이스 추가
- config/strategies.yml: type0_2·type2_2_opt 항목 + enabled_types에 추가
  · type2_2_opt fallback_plus_days=33, fallback_minus_days=5
- src/candle/config.py: ALL_TYPES 튜플에 type0_2·type2_2_opt 추가
- src/candle/backtest/__init__.py: 신규 모듈 import + ALL_TYPES 갱신
- claude-opus-4-7_guide.md: 17차 업데이트 (backtest 구조, optimize 섹션)

