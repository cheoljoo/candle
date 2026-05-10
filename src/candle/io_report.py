"""각 command가 읽고 쓰는 파일 + 그 내용 설명을 표시하는 helper.

각 run.py 진입 시점에 announce()를 호출.
"""
from __future__ import annotations

from datetime import datetime


def _ts() -> str:
    """현재 시각 문자열 (로그 timestamp). 예: 2026-05-10 19:07:07,928"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S,") + f"{now.microsecond // 1000:03d}"


def tprint(*args, **kwargs) -> None:
    """타임스탬프를 앞에 붙여 print.

    일반 print 대신 사용 — 로그에서 각 단계의 소요 시간 확인 가능.
    debug 출력([..][debug])은 기존 print() 그대로 유지.
    """
    if args and isinstance(args[0], str):
        print(f"{_ts()} {args[0]}", *args[1:], **kwargs)
    else:
        print(_ts(), *args, **kwargs)


def announce(command: str,
             inputs: list[tuple[str, str]] | None = None,
             outputs: list[tuple[str, str]] | None = None) -> None:
    """
    command   : 화면에 표시할 명령 이름 (예: 'fetch')
    inputs    : [(상대경로, 한 줄 설명), ...]
    outputs   : [(상대경로, 한 줄 설명), ...]
    """
    bar = "─" * 70
    ts = _ts()
    print(f"\n{bar}")
    print(f"  {ts} candle {command}")
    print(bar)
    if inputs:
        print("[INPUT]")
        for path, desc in inputs:
            print(f"  - {path}")
            print(f"      └─ {desc}")
    if outputs:
        print("[OUTPUT]")
        for path, desc in outputs:
            print(f"  - {path}")
            print(f"      └─ {desc}")
    print(bar)
