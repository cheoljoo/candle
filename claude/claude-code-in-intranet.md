# Claude Code (VS Code 확장) 사내망 인증서 문제 해결

사내 SSL 검사 환경에서 Claude Code가 채팅에 응답하지 못하고 재시도(loop)만 반복하던 문제 해결 정리.

## 원인

사내 프록시가 HTTPS를 가로채 **회사 루트(LGERootCA)** 로 재서명하는데, Windows 신뢰 저장소의 **만료된 루트** 때문에 TLS 검증이 실패(`CERT_HAS_EXPIRED`)하여 모든 API 호출이 막힘.

---

## 1. 회사 루트 포함 PEM 번들 만들기

아래 두 방법 중 하나 선택.

### 방법 A — 브라우저에서 내보내기 후 결합 (수동)

1. 브라우저 인증서 관리 화면 열기 → "신뢰할 수 있는 인증서"에서 **회사 루트(예: LGERootCA)** 찾기.
   (체인이 여러 단계면 **루트 + 중간 인증서** 모두 대상)
2. 각 인증서 **"내보내기"** → 형식은 반드시 **Base-64 encoded X.509 (.CER)** 선택. *(DER 아님)*
3. **메모장**을 열고, 내보낸 파일들의 내용을 차례로 복사해 한 파일에 이어붙이기:
   ```
   -----BEGIN CERTIFICATE-----
   (첫 번째 인증서 내용)
   -----END CERTIFICATE-----
   -----BEGIN CERTIFICATE-----
   (두 번째 인증서 내용)
   -----END CERTIFICATE-----
   ```
   - 각 `BEGIN`/`END` 마커는 한 줄씩. 블록 사이 빈 줄 1개는 무방.
4. **"다른 이름으로 저장"** → 파일 형식 **"모든 파일"**, 이름 `corp-chain.pem`, 인코딩 **ANSI** 또는 **UTF-8**.
   *(형식을 "텍스트"로 두면 `corp-chain.pem.txt`가 되니 주의)*
5. 저장한 파일을 다시 열어 `-----BEGIN CERTIFICATE-----` 텍스트로 시작하는지 확인.

> 내보낸 파일이 메모장에서 깨진 문자로 보이면 DER로 저장된 것 → **Base-64** 형식으로 다시 내보내기.

### 방법 B — PowerShell로 자동 추출 (만료 인증서 자동 제외, 권장)

```powershell
$out = "D:\downloads\corp-chain.pem"
Remove-Item $out -ErrorAction SilentlyContinue
$now = Get-Date
foreach ($store in @("Cert:\LocalMachine\Root","Cert:\CurrentUser\Root","Cert:\LocalMachine\CA","Cert:\CurrentUser\CA")) {
  Get-ChildItem $store | Where-Object { $_.NotAfter -gt $now -and $_.NotBefore -lt $now } | ForEach-Object {
    Add-Content $out "-----BEGIN CERTIFICATE-----"
    Add-Content $out ([Convert]::ToBase64String($_.RawData, 'InsertLineBreaks'))
    Add-Content $out "-----END CERTIFICATE-----"
  }
}
```

> 수동(A)으로 만든 번들에 **만료된 회사 루트 구버전**이 섞이면 `CERT_HAS_EXPIRED`가 날 수 있음. 그럴 땐 유효한 인증서만 넣을 것. (B 방법은 만료분을 자동 제외함)

---

## 2. npm으로 Claude Code 설치

`irm` 설치 스크립트는 .NET이라 막히므로 Node 기반 npm으로 우회:

```powershell
npm config set cafile "D:\downloads\corp-chain.pem"
npm install -g @anthropic-ai/claude-code
```

---

## 3. settings.json 설정

```jsonc
"claudeCode.environmentVariables": [
  { "name": "NODE_EXTRA_CA_CERTS", "value": "D:\\downloads\\corp-chain.pem" },
  { "name": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "value": "1" }
]
```

- `NODE_EXTRA_CA_CERTS` : 회사 루트 신뢰 → TLS 검증 통과
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` : 텔레메트리 등 배경 통신 차단 → 재시도 loop 제거
- (선택) `ENABLE_TOOL_SEARCH` = `false` : 도구 호출 시 2단계 플리커 제거

설정 후 `Ctrl+Shift+P` → **Developer: Reload Window**.

---

## 4. 동작 확인

VS Code 통합 터미널에서:

```powershell
$env:NODE_EXTRA_CA_CERTS="D:\downloads\corp-chain.pem"
claude --debug -p "hi"
```

`CERT_HAS_EXPIRED` 없이 정상 응답이 오면 완료.
로그에 `CA certs: Appended ... corp-chain.pem` 과 `isTelemetryEnabled=false` 가 보이면 정상 적용된 것.

---

## 참고

- 만료 인증서를 제외해도 `CERT_HAS_EXPIRED`가 계속되면 → 클라이언트 해결 불가. 회사 IT에 **프록시 루트 인증서(LGERootCA) 갱신·재배포**와 `api.anthropic.com`, `downloads.claude.ai`, `claude.ai` **허용**을 요청.
- `Fast mode unavailable`, 누락된 `settings.json`, 로딩 문구(`marinating`, `imagining` 등)는 **에러가 아닌 정상** 메시지.
- 네트워크 설정 문서: https://docs.anthropic.com/en/docs/claude-code/network-config

