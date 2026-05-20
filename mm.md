feat: compare Top10%/전체분리 + 문서 19차 업데이트 (2026-05-20)

## compare.html — 수익률 Top 10% 상세 내역으로 개편
- 제목: "내림 순위 전체 상세" → "📈 수익률 Top 10% 상세 내역"
- 각 그룹 테이블: `max(group_size // 10, 1)`개만 표시 (전체 대신 상위 10%)
- 헤더: "상위 N개 / 전체 M개 (Top 10%)" 표시
- 제목 옆 "📋 내림 순위 전체 종목 상세 →" 링크 추가 (compare_full.html)

## compare_full.html — 전체 종목 내림차순 페이지 신규
- 기간×전략 2단 탭 구조 (compare.html과 동일)
- 전체 종목 수익률 내림차순, Top 10% 구간 ★ 뱃지·연초록 배경 강조
- 우상단 "← 전략별 요약 (Top 10%)" 복귀 버튼
- render.py에 compare_full.html 렌더링 추가

## 문서 업데이트 (19차)
- claude-opus-4-7_guide.md: 19차 헤더 + compare_full.html 섹션 추가
  대시보드 파일 목록에 compare_full.html 추가
- claude-work.md: 2026-05-20 2차 작업 로그 추가
