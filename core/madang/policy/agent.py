"""에이전트 공통 지시: 부작용은 직접 하지 않고 madang 명령으로만 한다.

모든 실행의 요청 끝에 붙는다. 머지와 게시는 실행이 끝난 뒤 정책이 하므로
에이전트는 git·배포 명령을 직접 쓰지 않는다. 실행할 수 있는 것을 만들면
선언하는 것까지가 과업이며, Ledger 검사기가 선언과 대조한다.
"""

from __future__ import annotations

AGENT_RULES = """\
<side-effects>
부작용 규칙 (모든 실행 공통)
1. git 명령(commit, merge, push, reset, checkout 등)과 배포·게시 명령을 \
직접 실행하지 않는다. 커밋·머지·게시는 실행이 끝난 뒤 madang이 정책에 따라 \
한다.
2. 실행할 수 있는 것(서버, 사이트, 스크립트)을 만들면 \
`madang runs add --name <이름> --command <명령> [--cwd <폴더>] \
[--opens <주소>]`로 선언하고, ledger.md artifacts에 \
`{path: <경로>, run: true, name: <이름>, command: <명령>}`으로 등록한다. \
선언과 다르면 검사기가 거부한다.
3. 그 밖의 부작용은 madang 명령으로만 한다: madang task, madang decide, \
madang artifact add, madang view create.
</side-effects>"""


def with_rules(request: str) -> str:
    """요청 끝에 공통 부작용 규칙을 붙인다."""
    return f"{request.rstrip()}\n\n{AGENT_RULES}"
