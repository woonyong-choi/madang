"""게시 경로: 프로젝트 ``publish:`` 설정대로 정적 사이트를 게시하고 되감는다.

사이트는 문서 렌더러 하나로 만들고, 브랜치 대상을 원격에 밀지는 정책
(``policy.deny``)이 정한다. 게시와 되감기는 ``.madang/published/<n>.json``에
남고, 끝나면 ``publish.done``으로 알린다.
"""

from __future__ import annotations

from madang import config, git, publish
from madang.api import errors, events, models, workspace
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.recorder import published
from madang.store import projects

router = Router(tags=["publish"])


def _record(
    record: published.PublishRecord | None,
) -> models.PublishRecord | None:
    if record is None:
        return None
    return models.PublishRecord.model_validate(record.model_dump(mode="json"))


@router.get("/projects/{project}/publish", operation_id="getPublishStatus")
def get_status(project: str, core: CoreDep) -> models.PublishStatus:
    """게시 설정(대상, 포함 경로, 자동 게시)과 마지막 게시 기록."""
    found = core.project(project)
    policy = workspace.policy_of(found)
    try:
        latest = published.latest(found.root)
    except published.PublishRecordError as exc:
        raise errors.conflict(str(exc)) from exc
    return models.PublishStatus(
        target=policy.publish.target,
        include=policy.publish.include,
        auto_publish=policy.settings.auto_publish,
        latest=_record(latest),
    )


@router.post("/projects/{project}/publish", operation_id="publishProject")
def publish_project(project: str, core: CoreDep) -> models.PublishOutcome:
    """사이트를 만들어 대상에 싣는다. 대상이 이미 같으면 기록하지 않는다."""
    found = core.project(project)
    return _run(core, found, undo=False)


@router.post("/projects/{project}/publish/undo", operation_id="undoPublish")
def undo_publish(project: str, core: CoreDep) -> models.PublishOutcome:
    """가장 최근 게시를 되감는다. 그 뒤 대상이 바뀌었으면 409."""
    found = core.project(project)
    return _run(core, found, undo=True)


def _run(
    core: Core, project: projects.Project, *, undo: bool
) -> models.PublishOutcome:
    core.config()
    with core.lock:
        try:
            result = (
                publish.undo(project.root)
                if undo
                else publish.publish(project.root, core.home)
            )
        except publish.PublishError as exc:
            raise errors.conflict(str(exc), exc.code) from exc
        except config.ConfigError as exc:
            raise errors.invalid(f"cannot load project config: {exc}") from exc
        except (git.GitError, OSError) as exc:
            raise errors.conflict(str(exc)) from exc
    record = result.record
    if record is not None:
        core.hub.emit(
            events.PUBLISH_DONE,
            {"n": record.n, "undo": undo, "push_error": result.push_error},
            project=project.id,
        )
        if record.branch is not None:
            core.announce_git(
                project.id, project.root, "publish", branch=record.branch
            )
    return models.PublishOutcome(
        target=result.target,
        changed=record is not None,
        site=result.site,
        documents=result.documents,
        warnings=result.warnings,
        push_error=result.push_error,
        record=_record(record),
    )
