"""실행 뒤 정책 단계: 코드 페이지는 테스트·머지, 바뀐 문서는 게시.

흐름이 판정을 마치면(리뷰 통과나 검증된 done) 이 단계가 프로젝트
``config.yaml``의 ``policy``대로 부작용을 낸다. 판단은 policy, 실행은
runs(테스트)·git(커밋·머지)·publish(게시), 기록은 recorder가 한다. 부작용은
모두 마지막 실행의 되돌리기 기록에 남는다. 정책이 거부하면 그 자리에서
멈추고 이유를 돌려준다. 흐름은 그것을 page.md의 묻는 블록으로 남긴다.
"""

from __future__ import annotations

import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from madang import config, git, publish, recorder, runs
from madang.cli_agent.repo import sensitive
from madang.policy import MergeCheck, Policy, conflict_reason
from madang.recorder.undo import COMMIT, MERGE, REPO_PREFIX
from madang.store import runs as run_records
from madang.store import worktrees
from madang.store.page import load_page, project_root, worktree_path

# 멈춘 단계.
STEP_CONFIG = "config"
STEP_MERGE = "merge"
STEP_PUBLISH = "publish"
TEST_RUN = "test"
TEST_SECONDS = 600.0
# 묻는 블록에 남기는 테스트 출력의 끝 줄 수.
OUTPUT_LINES = 20


@dataclass(frozen=True)
class Refusal:
    """정책이 부작용을 멈춘 이유.

    Attributes:
        step: 멈춘 단계(``config``, ``merge``, ``publish``).
        reasons: 사람이 읽을 거부 사유.
        approvable: 사람이 승인하면 테스트 조건 없이 머지할 수 있으면 참.
        output: 테스트 출력의 끝 줄.
    """

    step: str
    reasons: list[str]
    approvable: bool = False
    output: list[str] = field(default_factory=list)


@dataclass
class Settled:
    """정책 단계의 결과.

    Attributes:
        merged: 머지 커밋 해시. 머지하지 않았으면 None.
        published: 게시 번호. 게시하지 않았으면 None.
        push_error: 게시 브랜치를 밀다 실패한 이유. 없으면 None.
        refusal: 정책이 멈췄으면 그 이유. 끝까지 갔으면 None.
    """

    merged: str | None = None
    published: int | None = None
    push_error: str | None = None
    refusal: Refusal | None = None


def settle(
    page_dir: Path,
    n: int,
    message: str,
    *,
    home: Path,
    approved: bool = False,
) -> Settled:
    """메시지 하나의 실행이 끝난 뒤 정책대로 머지하고 게시한다.

    Args:
        page_dir: 페이지 폴더.
        n: 메시지의 마지막 실행 번호. 부작용은 이 실행의 기록에 남는다.
        message: 요청 메시지 블록 id. 이 메시지의 실행이 바꾼 파일로
            문서 변경을 판단한다.
        home: 앱 홈(게시할 때 뷰어 등록부).
        approved: 사람이 테스트 조건 없이 머지하라고 답했으면 참.

    Returns:
        머지·게시 결과 또는 거부 사유.
    """
    settled = Settled()
    root = project_root(page_dir)
    if root is None:
        return settled
    try:
        policy = Policy.load(root)
    except (OSError, config.ConfigError) as exc:
        settled.refusal = Refusal(STEP_CONFIG, [str(exc)])
        return settled
    if _is_code_page(page_dir, root):
        _merge(page_dir, root, n, policy, approved, settled)
        if settled.refusal is not None:
            return settled
    changed = changed_files(page_dir, message)
    _publish(page_dir, root, n, home, policy, changed, settled)
    return settled


def changed_files(page_dir: Path, message: str) -> set[str]:
    """메시지의 실행들이 바꾼 프로젝트 파일(프로젝트 기준 경로)."""
    found: set[str] = set()
    for number in run_records.list_runs(page_dir):
        record = run_records.read_run(page_dir, number)
        if (record.trigger or {}).get("message") != message:
            continue
        found.update(
            path.removeprefix(REPO_PREFIX)
            for path in record.changed_files
            if path.startswith(REPO_PREFIX)
        )
    return found


def run_tests(folder: Path, command: str) -> tuple[int, list[str]]:
    """선언된 테스트 명령을 ``folder``에서 실행하고 끝나기를 기다린다.

    Args:
        folder: 명령을 실행할 폴더(페이지 워크트리).
        command: ``policy.auto_merge.test``.

    Returns:
        ``(종료 코드, 출력의 끝 줄)``. 시간 안에 끝나지 않으면 멈추고
        음수 종료 코드를 돌려준다.

    Raises:
        RunsError: 폴더가 없다.
        OSError: 명령을 띄울 수 없다.
    """
    lines: deque[str] = deque(maxlen=OUTPUT_LINES)

    def keep(name: str, payload: dict) -> None:
        if name == runs.RUN_OUTPUT:
            lines.append(str(payload.get("line", "")))

    target = config.RunTarget(name=TEST_RUN, command=command)
    process = runs.Process(target, folder, keep)
    process.start()
    try:
        code = process.wait(TEST_SECONDS)
    except subprocess.TimeoutExpired:
        stopped = process.stop()
        lines.append(f"{TEST_SECONDS:.0f}초 안에 끝나지 않아 멈췄다")
        code = stopped if stopped is not None and stopped < 0 else -1
    return code, list(lines)


# 머지


def _is_code_page(page_dir: Path, root: Path) -> bool:
    if not git.is_repository(root):
        return False
    return load_page(page_dir)[0].kind == worktrees.CODE_KIND


def _merge(
    page_dir: Path,
    root: Path,
    n: int,
    policy: Policy,
    approved: bool,
    settled: Settled,
) -> None:
    """페이지 브랜치를 머지하고 머지 커밋이나 거부 사유를 ``settled``에 둔다."""
    merged = _try_merge(page_dir, root, n, policy, approved)
    if isinstance(merged, Refusal):
        settled.refusal = merged
    else:
        settled.merged = merged


def _try_merge(
    page_dir: Path, root: Path, n: int, policy: Policy, approved: bool
) -> str | Refusal | None:
    """페이지 브랜치를 테스트하고, 커밋하고, 정책이 허락하면 머지한다.

    Returns:
        머지 커밋 해시, 거부 사유, 합칠 것이 없으면 None.
    """
    branch = worktrees.branch_for(page_dir.name)
    if not git.has_branch(root, branch):
        return None
    denied = policy.check_deny(f"git merge --no-ff {branch}")
    if not denied.allowed:
        return Refusal(STEP_MERGE, denied.reasons)
    worktree = worktree_path(root, page_dir.name)
    test_exit, output = None, []
    if policy.test_command and not approved and worktree.is_dir():
        try:
            test_exit, output = run_tests(worktree, policy.test_command)
        except (runs.RunsError, OSError) as exc:
            return Refusal(STEP_MERGE, [f"테스트를 실행할 수 없다: {exc}"])
    check = MergeCheck(test_exit=test_exit, approved=approved)
    decision = policy.can_auto_merge(check)
    if not decision.allowed:
        return Refusal(STEP_MERGE, decision.reasons, True, output)
    refusal = _commit_worktree(page_dir, worktree, n)
    if refusal is not None:
        return refusal
    head = git.resolve(root, branch)
    if head is None or git.is_ancestor(root, head):
        return None  # 합칠 커밋이 없다
    conflicts = git.merge_conflicts(root, branch)
    check = MergeCheck(test_exit, conflicts, approved)
    decision = policy.can_auto_merge(check)
    if not decision.allowed:
        return Refusal(STEP_MERGE, decision.reasons)
    try:
        result = worktrees.merge_page(page_dir)
    except (worktrees.PageWorktreeError, git.GitError) as exc:
        return Refusal(STEP_MERGE, [str(exc)])
    if result.commit is None:
        return Refusal(STEP_MERGE, [conflict_reason(result.conflicts)])
    recorder.record_git(page_dir, n, MERGE, root, result.before, result.commit)
    return result.commit


def _commit_worktree(page_dir: Path, worktree: Path, n: int) -> Refusal | None:
    """워크트리에 남은 변경을 페이지 브랜치에 커밋하고 기록한다."""
    if not worktree.is_dir():
        return None
    changed = list(git.status(worktree))
    if not changed:
        return None
    secrets = sensitive(changed)
    if secrets:
        reason = "비밀이 들어 있을 수 있는 파일: " + ", ".join(secrets)
        return Refusal(STEP_MERGE, [reason])
    before = git.rev_parse(worktree)
    git.stage(worktree)
    if not git.has_staged_changes(worktree):
        return None
    commit = git.commit(worktree, f"Record page {page_dir.name} run {n}")
    recorder.record_git(page_dir, n, COMMIT, worktree, before, commit)
    return None


# 게시


def _publish(
    page_dir: Path,
    root: Path,
    n: int,
    home: Path,
    policy: Policy,
    changed: set[str],
    settled: Settled,
) -> None:
    """자동 게시가 허락되고 게시할 문서가 바뀌었으면 게시한다."""
    if not policy.can_auto_publish().allowed or not changed:
        return
    try:
        target = publish.parse_target(policy.publish.target, root)
        exclude = [target.folder] if target.folder is not None else []
        documents = publish.collect(root, policy.publish.include, exclude)
        if changed.isdisjoint(documents):
            return
        result = publish.publish(root, home)
    except (
        publish.PublishError,
        config.ConfigError,
        git.GitError,
        OSError,
    ) as exc:
        settled.refusal = Refusal(STEP_PUBLISH, [f"게시 실패: {exc}"])
        return
    settled.push_error = result.push_error
    if result.record is not None:
        recorder.record_publish(page_dir, n, root, result.record.n)
        settled.published = result.record.n
