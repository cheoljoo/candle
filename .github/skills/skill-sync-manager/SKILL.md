---
name: skill-sync-manager
description: "skills를 sync해줘" 또는 "기술 동기화해줘" 
---

# 스킬: 기술 동기화 매니저

사용자가 **"skills를 sync해줘"**, **"기술 동기화해줘"**, 또는 **"스킬 업데이트해줘"**라고 요청하면 아래 명령어를 실행한다.

## 수행 작업
1. 프로젝트 루트에서 `make skills-sync` 명령어를 실행한다.
2. 동기화가 완료되면 사용자에게 성공 메시지를 전달한다.

## 참고
- `make skills-sync`는 `scripts/sync_skills.sh`를 실행한다.
- 스크립트가 자동으로 아래를 모두 처리한다:
  - `.gemini/skills/<name>/SKILL.md` symlink 생성/갱신 (Gemini CLI)
  - `.github/vscode-skills/<name>.md` symlink 생성/갱신 (VS Code)
  - `.vscode/settings.json` 의 `github.copilot.chat.codeGeneration.instructions` 자동 갱신
