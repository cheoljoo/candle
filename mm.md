feat: 수익률 테이블 종목명 개선 — 25자·보라색·데이터부족 뱃지

## dashboard — group_returns.html 종목명 표시 개선
- `templates/group_returns.html`: 종목명 길이 10자 → 25자(2.5배), 색상 회색 → 보라색(`text-violet-600`)
- `render.py`: instruments 루프 1회 통합(`ticker_rc` 맵). `period_table` 행에 `data_lacking`/`row_count` 추가
- 수익률 테이블 내 `data_lacking=True` 종목에 주황색 뱃지 `데이터부족 N일` 인라인 표시

