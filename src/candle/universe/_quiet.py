"""pykrx의 깨진 logging.info(args, kwargs) 호출과 stdout 노이즈 차단."""
from __future__ import annotations

import contextlib
import io
import logging as _logging


@contextlib.contextmanager
def quiet_pykrx():
    """pykrx 호출 동안 stdout/stderr 차단 + root logger CRITICAL 로 격하.

    pykrx는 (a) 'Error occurred in ...' 를 print 로 stdout에 찍고,
    (b) wrapper에서 `logging.info(args, kwargs)` 를 호출 (포맷 placeholder 없이 tuple/dict 전달)
        해서 root logger에 TypeError + 거대한 traceback을 발생시킴.
    아래 context 동안 두 노이즈를 모두 막는다.
    """
    root = _logging.getLogger()
    prev_level = root.level
    root.setLevel(_logging.CRITICAL)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            yield
    finally:
        root.setLevel(prev_level)
