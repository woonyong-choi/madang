"""``madang promote``: 블록 파일을 코드 저장소 docs/로 복사하고 커밋한다."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from madang.cli_agent import repo as coderepo
from madang.cli_agent.artifacts import REPO_PREFIX, register
from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.store import pages
from madang.store.page import STATE_FILE

PROMOTE_DIR = "docs"


@dataclass(frozen=True)
class Promoted:
    """승격 결과.

    Attributes:
        path: 복사한 ``repo:`` 경로.
        commit: 새 커밋의 짧은 해시. 저장소가 이미 같은 내용이면 None.
    """

    path: str
    commit: str | None


def _promoted_name(block_id: str, source: Path) -> str:
    name = source.name
    stripped = (
        name[len(block_id) + 1 :] if name.startswith(f"{block_id}-") else name
    )
    return stripped or name


def _source_file(ctx: PageContext, block_id: str) -> Path:
    if pages.parse_block_id(block_id) is None:
        raise AgentError(f"'{block_id}'는 블록 id(bNN)가 아니다")
    files = pages.block_files(ctx.page_dir, block_id)
    if not files:
        raise AgentError(f"블록 {block_id}의 파일이 blocks/에 없다")
    if len(files) > 1:
        raise AgentError(
            f"블록 {block_id}에 파일이 여러 개다: "
            f"{', '.join(f.name for f in files)}"
        )
    return files[0]


def promote(ctx: PageContext, block_id: str) -> Promoted:
    """블록 파일을 코드 저장소로 복사하고 커밋한다.

    Args:
        ctx: 블록을 소유한 페이지.
        block_id: 블록 id, ``bNN``.

    Returns:
        복사한 경로와 커밋.

    Raises:
        AgentError: 블록을 승격할 수 없거나, 파일 이름이 민감해 보이거나,
            페이지 검증에 실패했다.
    """
    repo = coderepo.require_repo(ctx)
    source = _source_file(ctx, block_id)
    rel = f"{PROMOTE_DIR}/{_promoted_name(block_id, source)}"
    if coderepo.sensitive([rel]):
        raise AgentError(
            f"비밀이 들어 있을 수 있는 파일은 승격하지 않는다: {rel}"
        )
    dest = repo / rel
    if dest.exists() and dest.read_bytes() != source.read_bytes():
        dirty = coderepo.git.run(
            repo, "status", "--porcelain", "--", rel
        ).stdout.strip()
        if dirty:
            raise AgentError(
                f"{rel}에 커밋하지 않은 변경이 코드 저장소에 있다. "
                "먼저 커밋한다"
            )
    entry = REPO_PREFIX + rel
    message = f"docs: promote {block_id} from {ctx.page_id}"
    result: dict[str, str | None] = {}

    with guarded(ctx, ctx.page_dir / STATE_FILE, dest) as txn:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pages.update_state(ctx.page_dir, lambda header: register(header, entry))
        txn.then(
            lambda: result.update(
                commit=coderepo.commit_paths(repo, [rel], message)
            )
        )
    return Promoted(path=entry, commit=result.get("commit"))
