"""게시와 되감기: 설정을 읽어 사이트를 만들고 대상에 실은 뒤 기록한다."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from madang import config, git
from madang.policy import Policy
from madang.publish import targets
from madang.publish.settings import KIND_FOLDER, PublishError, parse_target
from madang.publish.site import Site, build
from madang.recorder import published
from madang.recorder.published import PublishRecord
from madang.store import pages
from madang.viewers import Registry, content_hash


@dataclass
class PublishResult:
    """게시나 되감기의 결과.

    Attributes:
        target: 설정의 대상 원문.
        record: 남긴(되감기면 되감은) 게시 기록. 대상이 이미 같아서
            아무것도 하지 않았으면 None.
        site: 사이트 내용 해시. 되감기면 None.
        documents: 게시한 문서 수.
        warnings: 표로 대체될 뷰어 펜스 등.
        push_error: 게시 브랜치를 밀다 실패한 이유. 없으면 None.
    """

    target: str
    record: PublishRecord | None = None
    site: str | None = None
    documents: int = 0
    warnings: list[str] = field(default_factory=list)
    push_error: str | None = None


def publish(root: Path, home: str | Path | None = None) -> PublishResult:
    """프로젝트 설정 ``publish:``대로 사이트를 만들어 게시한다.

    Args:
        root: 프로젝트 폴더.
        home: 앱 홈(뷰어 등록부). ``config.resolve_home``과 같이 해석한다.

    Returns:
        게시 결과.

    Raises:
        PublishError: 설정·포함 경로·대상에 문제가 있다.
        config.ConfigError: 프로젝트 설정이 틀렸다.
        git.GitError: 브랜치 대상에서 git이 실패했다.
    """
    settings = config.load_project_config(root)
    target = parse_target(settings.publish.target, root)
    exclude = [target.folder] if target.folder is not None else []
    with tempfile.TemporaryDirectory(prefix="madang-site-") as tmp:
        out = Path(tmp) / "site"
        site = build(
            root,
            settings.publish.include,
            out=out,
            registry=Registry(home),
            exclude=exclude,
        )
        base = _record(root, target.raw, site)
        if target.kind == KIND_FOLDER:
            assert target.folder is not None
            record = targets.deploy_folder(root, out, target.folder, base)
        else:
            assert target.branch is not None
            record = targets.deploy_branch(root, out, target.branch, base)
    result = PublishResult(
        target.raw,
        site=base.site,
        documents=len(site.documents),
        warnings=site.warnings,
    )
    if record is None:
        return result
    if record.branch is not None:
        remote, result.push_error = _push(
            root, record.branch, Policy(settings.policy, settings.publish)
        )
        record = record.model_copy(update={"pushed_to": remote})
    published.save(root, record)
    result.record = record
    return result


def undo(root: Path) -> PublishResult:
    """가장 최근 게시를 되감는다.

    브랜치 대상이고 그 게시를 원격에 밀었으면 되감은 커밋도 민다.

    Args:
        root: 프로젝트 폴더.

    Returns:
        되감은 기록을 담은 결과.

    Raises:
        PublishError: 되감을 게시가 없거나(``nothing-to-undo``), 게시 뒤에
            대상이 바뀌었다(``target-changed``).
        git.GitError: 브랜치 대상에서 git이 실패했다.
    """
    record = published.latest(root)
    if record is None:
        raise PublishError("nothing-to-undo", "no publish left to undo")
    target = parse_target(record.target, root)
    result = PublishResult(record.target)
    undo_commit = None
    if target.kind == KIND_FOLDER:
        assert target.folder is not None
        targets.rewind_folder(root, target.folder, record)
    else:
        undo_commit = targets.rewind_branch(root, record)
        if record.pushed_to is not None and record.branch is not None:
            policy = Policy.load(root)
            _, result.push_error = _push(root, record.branch, policy)
    result.record = published.mark_undone(root, record, undo_commit)
    return result


def _record(root: Path, target: str, site: Site) -> PublishRecord:
    return PublishRecord(
        n=published.next_number(root),
        at=pages.now(),
        target=target,
        site=content_hash(site.folder),
        documents=[d.source for d in site.documents],
        viewers=site.viewers,
    )


def _push(
    root: Path, branch: str, policy: Policy
) -> tuple[str | None, str | None]:
    """``(민 원격, 실패 이유)``. 실패해도 브랜치 커밋은 그대로 남는다."""
    try:
        return targets.push_branch(root, branch, policy), None
    except git.GitError as exc:
        return None, str(exc)
