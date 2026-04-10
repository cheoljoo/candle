# GitHub Copilot Instructions

## 프로젝트 개요
- **프로젝트명**: CANDLE
- **목적**: 캔들차트 하나로 끝내는 추세추종 투자 (책 내용 구현) — KOSPI 200 종목의 10월 이동평균 추세 분석
- **언어**: Python 3
- **패키지 관리 / 실행**: `uv` 사용 (`uv run python <file>`)
- **저장소**: https://github.com/cheoljoo/candle.git

## 주요 파일
| 파일 | 역할 |
|------|------|
| `fetch_data.py` | KOSPI 종목 목록 및 일봉 종가 수집. 오늘 데이터가 이미 있으면 스킵(증분 수집) |
| `analyze.py` | 저장된 데이터로 10월 이평 분석. 7거래일 이격률 추이 및 변곡점 종목 출력 |
| `main.py` | fetch + analyze 를 하나로 합친 초기 버전 (참고용) |
| `Makefile` | `make fetch` / `make analyze` / `make all` / `make clean` |

## 데이터 구조
```
data/
├── kospi_list.csv          # KOSPI 전체 종목 목록 (fetch_data.py 가 매번 갱신)
└── stocks/{code}.csv       # 종목별 일봉 데이터 (컬럼: Date, Close)
                            # ※ 10월이평은 저장하지 않음 — analyze.py 실행 시 계산
```

## 분석 로직 요약
1. `data/stocks/{code}.csv` 에서 일봉 종가 로드
2. 월말 종가(`resample('ME').last()`)로 월봉 생성
3. 월봉 기준 rolling(10) 이동평균 → 일봉 인덱스에 forward-fill
4. 이격률(%) = `(현재가 - 10월이평) / 10월이평 × 100`
5. 최근 7거래일 이격률의 부호 변화 → **변곡점** 판별

## Makefile 사용법
```bash
make fetch    # 데이터 수집 (당일 이미 수집했으면 스킵)
make analyze  # 분석 실행
make all      # fetch → analyze 순서 실행
make clean    # data/ 디렉터리 초기화
```

## 규칙
- **git add / commit / push 는 하지 않는다.** 사용자가 직접 처리한다.
- commit 메시지 초안이 필요하면 `mm.md` 파일에 작성한다.
- Python 실행은 반드시 `uv run python <file>` 을 사용한다.
- `data/` 디렉터리는 `.gitignore` 에 등록되어 있으므로 커밋하지 않는다.

> 프로젝트 스킬은 `.github/instructions/` 폴더의 파일을 참고하세요.
