"""실행 결과 기록: page.md 블록, ledger.md 머리부, ``runs/`` 기록, 되돌리기.

흐름과 러너가 페이지에 남기는 결과는 모두 이 모듈을 거친다. 실행에 딸린
쓰기는 그 실행의 부작용으로 ``runs/N.undo.json``에 남아 ``undo``로 되감을
수 있다.
"""

from madang.recorder.ledger import (
    add_artifact,
    mark_route,
    set_reads,
    set_status,
)
from madang.recorder.page import reply, request
from madang.recorder.run import begin, save_run
from madang.recorder.undo import (
    UndoConflictError,
    UndoError,
    UndoResult,
    undo,
)

__all__ = [
    "UndoConflictError",
    "UndoError",
    "UndoResult",
    "add_artifact",
    "begin",
    "mark_route",
    "reply",
    "request",
    "save_run",
    "set_reads",
    "set_status",
    "undo",
]
