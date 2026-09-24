"""실행 결과 기록: page.md 블록, ledger.md 머리부, ``runs/`` 기록, 되돌리기.

흐름과 러너가 페이지에 남기는 결과는 모두 이 모듈을 거친다. 실행에 딸린
쓰기는 그 실행의 부작용으로 ``runs/N.undo.json``에 남아 ``undo``로 되감을
수 있다. git 커밋·머지는 ``record_git``으로 더해 되돌림 커밋으로 되감는다.
게시 자체는 프로젝트 단위 기록이라 ``published`` 모듈이
``.madang/published/<n>.json``에 남기고, 그 게시를 부른 실행에는
``record_publish``로 번호를 더해 같은 되돌리기로 되감는다.
"""

from madang.recorder.ledger import (
    add_artifact,
    mark_route,
    set_reads,
    set_status,
    update_ledger,
)
from madang.recorder.page import answer, ask, reply, request
from madang.recorder.run import begin, save_run
from madang.recorder.undo import (
    UndoConflictError,
    UndoError,
    UndoResult,
    record_git,
    record_publish,
    undo,
)

__all__ = [
    "UndoConflictError",
    "UndoError",
    "UndoResult",
    "add_artifact",
    "answer",
    "ask",
    "begin",
    "mark_route",
    "record_git",
    "record_publish",
    "reply",
    "request",
    "save_run",
    "set_reads",
    "set_status",
    "undo",
    "update_ledger",
]
