---
name: worklog-manager
description: "일을 정리 해주세요" 
---

# 스킬: 작업 정리

사용자가 **"일을 정리 해주세요"** 또는 **"일을 정리 해줘"** 라고 입력하면
아래 순서대로 수행한다.

---

## 사전 단계 A — 월별 아카이브 체크 (매월 초 자동 처리)

현재 날짜의 **월(YYYY-MM)** 과 `worklog.md` 첫 줄의 월이 다르면 (= 새 달):

1. `worklog.md` → `worklog/YYYY-MM.md` 로 이동 (YYYY-MM = 지난달)
2. `data/worklog.json` → `data/worklog/YYYY-MM.json` 으로 이동
3. `worklog.md` 새로 생성 (빈 파일 + 헤더)
4. `data/worklog.json` 새로 생성 (`[]`)
5. `worklog/` 및 `data/worklog/` 디렉토리가 없으면 생성

이 체크는 "일을 정리 해주세요" 를 트리거로 자동 수행한다.

---

## 사전 단계 B — 작업 시간 및 툴 정보 자동 감지

> **시간은 아래 우선순위로 자동 산출한다. `unknown` 기록은 최후 수단이다.**

1. **작업 시간 자동 산출 (우선순위 순)**:

   **[우선순위 1] 사용자가 직접 시각을 언급한 경우**
   - "09:30부터 11:00까지 작업했어" 같이 대화에 시각이 명시되면 해당 값을 사용한다.

   **[우선순위 2] `<current_datetime>` 태그가 메시지에 포함된 경우** (Claude Code, Gemini CLI 등)
   - **세션 시작 시간**: 대화에서 가장 첫 번째 `<current_datetime>` 값 (UTC→KST +9h 변환)
   - **세션 종료 시간**: "일을 정리 해주세요" 메시지의 `<current_datetime>` 값 (UTC→KST +9h 변환)
   - **개별 작업 시간**: 각 작업(task)이 시작/완료된 시점의 `<current_datetime>` 값으로 산출
   - ※ VS Code Copilot Chat은 이 태그를 자동 삽입하지 않으므로 이 우선순위는 해당 없음

   **[우선순위 3 — 기본 동작] mtime 기반 자동 근사** (VS Code Copilot Chat 등)
   - 이번 세션에서 수정된 파일들의 mtime(로컬시간)을 `stat` 명령으로 확인한다.
   - 가장 이른 mtime → `start`, 가장 늦은 mtime → `end` 로 사용한다.
   - task 시간은 전체 구간을 작업 수로 균등 분할해 `start/end/duration` 배분한다.
   - mtime으로 산출한 시간은 `detail`에 `approx by mtime` 문구를 1회 포함해 근사치임을 명시한다.
   - **이 단계는 `<current_datetime>`가 없을 때 자동으로 실행하며, 별도 지시 없이도 수행한다.**

   **[최후 수단] `unknown` 기록**
   - 위 3가지 방법 모두 시각을 확보할 수 없을 때만 `"unknown"` 으로 기록한다.

   - duration 계산: 종료 - 시작 (분 단위 계산 후 `Xh Ym` 형식)

2. **툴 및 세션 ID** 자동 감지:
   - Copilot CLI → `tool: "copilot-cli"`, session_id: 현재 세션 ID
   - Claude Code → `tool: "claude-code"`, session_id: 대화 ID
   - VS Code Copilot → `tool: "vscode-copilot"`, session_id: 대화 ID
   - 확인 불가 → `tool: "unknown"`, session_id: null

---

## 사전 단계 C — Chat 근거 기반 복구(터미널 로그가 약할 때)

> 터미널 실행 이력이 적고 Chat 창 논의가 핵심인 세션은, Chat 내용을 증거로 worklog를 복구한다.

1. **근거 우선순위**:
  - (1) 이번 대화의 요청/응답 요약(가능하면 conversation summary 포함)
  - (2) 에이전트가 실제 실행한 도구 결과(파일 수정/컴파일/테스트)
  - (3) 파일 mtime 및 산출물 timestamp

2. **기록 원칙(확정/추정 분리)**:
  - Chat/도구 결과로 명확히 확인된 내용은 일반 task로 기록
  - 추정으로 복구한 내용은 `detail`에 `approx (from chat)` 문구를 1회 포함
  - 시간은 `<current_datetime>`가 없으면 **반드시 mtime으로 자동 근사**하며, mtime도 확보 불가한 경우에만 `unknown` 허용
  - **worklog.md, data/worklog.json, report.md, lessons.md, mm.md 자체의 업데이트/생성은 task 항목에 포함하지 않는다.** 이는 정리 작업의 부산물이지 실제 작업 내용이 아니다.

3. **반영 파일**:
  - `worklog.md` (맨 위 prepend)
  - `data/worklog.json` (append)
  - 필요 시 `lessons.md`에 "복구 시점에서의 교훈" 추가

4. **최종 보고 형식**:
  - "확정 작업 N건 / 추정 작업 M건"으로 구분
  - 추정 항목에는 신뢰도(`높음/중간/낮음`)를 detail에 표기
  - 추가로 "토큰 사용량(추정)" 1줄을 포함: 예) `예상 토큰: 약 8k~20k (입력 파일 크기/도구 호출 수에 따라 변동)`

---

## 작업 1 — README.md 업데이트
- 해당 일이 전체 구조와 연관된 경우 프로젝트의 현재 상태를 반영하여 `README.md`를 업데이트한다.
- 시간이나 commit 단위의 내용은 `worklog.md`에 업데이트한다.

## 작업 2 — report.md 업데이트
- 세션에서 나온 **핵심 결과, 수치, 분석 과정, 재현 방법**을 `report.md` 에 정리한다.
- 이미 파일이 있으면 최신 결과 중심으로 갱신하고, 없으면 새로 생성한다.

## 작업 3 — worklog.md에 작업 내역 추가 (이번 달 파일)
- `worklog.md` 파일 **맨 위에** 추가한다.
- **`worklog.md`, `data/worklog.json`, `report.md`, `lessons.md`, `mm.md` 자체의 업데이트/생성은 작업 내용에 포함하지 않는다.**
- 형식:
  ```
  ## YYYY-MM-DD HH:MM ~ HH:MM (Xh Ym) [tool: copilot-cli / session: xxxx-xxxx]
  - 작업 내용 1
  - 작업 내용 2
  ```

## 작업 4 — data/worklog.json에 구조화 데이터 추가 (이번 달 파일)
- `data/worklog.json` 배열에 항목을 **append** 한다.
- **`worklog.md`, `data/worklog.json`, `report.md`, `lessons.md`, `mm.md` 자체의 업데이트/생성은 tasks 항목에 포함하지 않는다.**
- 형식:
  ```json
  {
    "date": "YYYY-MM-DD",
    "start": "HH:MM",
    "end": "HH:MM",
    "duration": "Xh Ym",
    "tool": "copilot-cli",
    "session_id": "세션-ID",
    "tasks": [
      { "title": "작업 제목", "detail": "상세 내용" , "start": "HH:MM" , "end": "HH:MM" , "duration": "Xh Ym"}
    ],
    "project": "프로젝트명"
  }
  ```

## 작업 5 — lessons.md에 중요 교훈 기록
- 형식:
  ```
  ## YYYY-MM-DD — [주제]
  - 교훈 내용
  ```

## 작업 6 — mm.md에 commit msg 기록
- git 내용과 비교하여 추가된 내용들을 적어달라.
- 형식:
  ```
  짧은 summary 1줄

  상세한 내용
  ```

---

## Chat 기반 정리용 추천 프롬프트 (복붙용)

```text
아래 chat 기록(요약/원문)을 근거로 worklog를 만들어줘.

규칙:
1) 확정 사실과 추정 내용을 분리
2) 추정은 detail에 `approx (from chat)` 표기
3) `worklog.md`와 `data/worklog.json` 둘 다 업데이트
4) tasks는 3~6개로 구조화
5) 결과 보고 시 확정 N건/추정 M건과 신뢰도(높음/중간/낮음) 표시

입력:
- [여기에 chat 내용 붙여넣기]
```

---

## 전체 합산 방법 (필요 시 안내)

사용자가 "전체 워크로그 합쳐줘" 또는 "워크로그 통합해줘" 라고 하면:

```bash
# 전체 JSON 통합 (날짜순 정렬)
cat data/worklog/*.json data/worklog.json 2>/dev/null \
  | jq -s 'add | sort_by(.date)' > data/worklog_all.json

# 전체 MD 열람
cat worklog/*.md worklog.md 2>/dev/null | less
```

---

## 파일 구조 (참고)
```
worklog.md                  ← 이번 달만
report.md                   ← 최신 분석/결과 요약
worklog/
  2026-03.md                ← 지난달 아카이브
  2026-02.md
data/worklog.json           ← 이번 달만
data/worklog/
  2026-03.json
  2026-02.json
data/worklog_all.json       ← 통합 시에만 생성 (임시)
```

## 공통 규칙
- git add / commit / push 는 하지 않는다. 사용자가 직접 처리한다.
