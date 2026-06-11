feat: 구성종목 변동 감지 노이즈 방지 강화 + KR ticker 선행 0 보존 일관화

## 변경 요약

### src/candle/universe/build.py — 핵심 개선
- `_STABLE_DAYS=5`, `_EXIT_DAYS=20` 상수 도입으로 판정 기준 명시화
- **진입 판정**: 과거 스냅샷 전체에 단 한 번도 없었던 종목만 신규 진입으로 기록
- **퇴출 판정**: 최근 `_EXIT_DAYS`(≈1개월) 동안 연속 부재 + 그 이전 `_STABLE_DAYS` 거래일에 안정적으로 존재했던 종목으로 한정 → 일시적 데이터 누락 오판 방지
- 최초 부재일 기준으로 단 1회 기록(upsert 중복 방지)
- 변동 비율 10% 이상 시 데이터 노이즈(fallback 오염)로 간주하여 기록 스킵

### src/candle/storage/csv_io.py
- post-read astype 방식 → `pd.read_csv(dtype={"ticker": str})` 방식으로 단순화
- ticker 컬럼 없는 CSV에서도 안전하게 동작

### src/candle/dashboard/render.py
- `_load_membership_changes`: KR ticker csv 읽기 시 선행 0 복원 (`str.zfill(6)`)
- instruments.csv → pykrx 순서로 종목명 fallback 보강
- `_load_delisted`: name 컬럼 `astype(str)` 강제로 TypeError 방지

### 기타
- `config/runtime.yml`: backtest workers 8 → 3 (로컬 환경 기준 조정)
- `claude/research_to_increase_stock_count.md`: type3_boost → type4 명칭 정정, price_guard 1.20 → 1.10

