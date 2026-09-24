"""실행 결과 기록: page.md 블록, ledger.md 머리부, ``runs/`` 기록, 되돌리기.

흐름과 러너가 페이지에 남기는 결과는 모두 이 모듈을 거친다. 실행에 딸린
쓰기는 그 실행의 부작용으로 ``runs/N.undo.json``에 남아 ``undo``로 되감을
수 있다. git 커밋·머지는 ``record_git``으로 더해 되돌림 커밋으로 되감는다.
게시는 프로젝트 단위 부작용이라 ``published`` 모듈이
``.madang/published/<n>.json``에 따로 남긴다.
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
    record_git,
    undo,
)

__all__ = [
    "UndoConflictError",
    "UndoError",
    "UndoResult",
    "add_artifact",
    "begin",
    "mark_route",
    "record_git",
    "reply",
    "request",
    "save_run",
    "set_reads",
    "set_status",
    "undo",
]
