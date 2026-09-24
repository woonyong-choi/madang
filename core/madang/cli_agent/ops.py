"""What each agent command does to the page. Every write is validated and undone on failure."""

from __future__ import annotations

import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from madang.cli_agent import repo as coderepo
from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.store import frontmatter, pages
from madang.store.page import PAGE_FILE, STATE_FILE

TASK_STATUSES = ("todo", "doing", "blocked", "review", "done")
DECISION_STATES = ("proposed", "confirmed", "superseded", "deferred")
REPO_PREFIX = "repo:"
PROMOTE_DIR = "docs"
DATA_SUFFIXES = (".json", ".csv", ".source.yaml")
TEMPLATES_ENV = "MADANG_TEMPLATES"

# Templates bundled with the app: name -> (version, [(slot, required)]).
BUILTIN_TEMPLATES: dict[str, tuple[int, list[tuple[str, bool]]]] = {
    "table": (1, [("data", True)]),
    "decisions": (1, [("state", True)]),
    "tasks": (1, [("state", True)]),
    "resume": (1, [("base", True), ("overlay", False)]),
}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _list(header: dict[str, Any], key: str) -> list[Any]:
    value = header.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise AgentError(f"state.md '{key}' is not a list")
    return value


def _check_id(value: str, what: str) -> None:
    if not _ID.match(value):
        raise AgentError(f"invalid {what} id '{value}'")


# task


def set_task(
    ctx: PageContext, task_id: str, status: str, title: str | None = None, due: str | None = None
) -> str:
    _check_id(task_id, "task")
    if status not in TASK_STATUSES:
        raise AgentError(f"status '{status}' is not one of {' | '.join(TASK_STATUSES)}")
    due_date: date | None = None
    if due is not None:
        try:
            due_date = date.fromisoformat(due)
        except ValueError as exc:
            raise AgentError(f"due '{due}' is not a YYYY-MM-DD date") from exc

    result = ""

    def mutate(header: dict[str, Any]) -> None:
        nonlocal result
        tasks = _list(header, "tasks")
        task = next((t for t in tasks if isinstance(t, dict) and str(t.get("id")) == task_id), None)
        if task is None:
            if not title:
                raise AgentError(f"task '{task_id}' does not exist; pass --title to create it")
            task = {"id": task_id, "title": title, "status": status}
            tasks.append(task)
            result = f"added task {task_id}"
        else:
            task["status"] = status
            if title:
                task["title"] = title
            result = f"updated task {task_id}"
        if due_date is not None:
            task["due"] = due_date
        header["tasks"] = tasks

    with guarded(ctx, ctx.page_dir / STATE_FILE):
        pages.update_state(ctx.page_dir, mutate)
    return f"{result}: {status}"


# decide


def decide(
    ctx: PageContext,
    decision_id: str,
    *,
    topic: str,
    choice: str,
    options: str,
    supersedes: str | None = None,
    state: str = "confirmed",
    by: str | None = None,
) -> str:
    _check_id(decision_id, "decision")
    opts = [o.strip() for o in options.split(",") if o.strip()]
    if not opts:
        raise AgentError("--options needs at least one value (a,b,c)")
    if len(set(opts)) != len(opts):
        raise AgentError("--options has duplicate values")
    if choice not in opts:
        raise AgentError(f"choice '{choice}' is not in options {', '.join(opts)}")
    if state not in DECISION_STATES:
        raise AgentError(f"state '{state}' is not one of {' | '.join(DECISION_STATES)}")
    if supersedes == decision_id:
        raise AgentError("a decision cannot supersede itself")

    def mutate(header: dict[str, Any]) -> None:
        decisions = _list(header, "decisions")
        ids = {str(d.get("id")) for d in decisions if isinstance(d, dict)}
        if decision_id in ids:
            raise AgentError(f"decision '{decision_id}' already exists; record a new id with --supersedes")
        if supersedes is not None:
            old = next(
                (d for d in decisions if isinstance(d, dict) and str(d.get("id")) == supersedes), None
            )
            if old is None:
                raise AgentError(f"decision '{supersedes}' to supersede does not exist")
            old["state"] = "superseded"
        decisions.append(
            {
                "id": decision_id,
                "topic": topic,
                "choice": choice,
                "options": opts,
                "by": ctx.by(by),
                "run": ctx.run,
                "state": state,
                "supersedes": supersedes,
            }
        )
        header["decisions"] = decisions

    with guarded(ctx, ctx.page_dir / STATE_FILE):
        pages.update_state(ctx.page_dir, mutate)
    suffix = f" (supersedes {supersedes})" if supersedes else ""
    return f"recorded decision {decision_id}: {choice}{suffix}"


# artifact


def _within(path: Path, base: Path) -> str | None:
    try:
        return path.relative_to(base.resolve()).as_posix()
    except ValueError:
        return None


def artifact_entry(ctx: PageContext, raw: str, cwd: Path | None = None) -> str:
    """Normalize a path to a state.md artifact: ``blocks/...`` or ``repo:...``."""
    if raw.startswith(REPO_PREFIX):
        return REPO_PREFIX + Path(raw[len(REPO_PREFIX) :]).as_posix()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        if (ctx.page_dir / path).exists():
            return path.as_posix()
        candidate = (cwd or Path.cwd()) / path
        if not candidate.exists():
            return path.as_posix()
        path = candidate
    path = path.resolve()
    if (rel := _within(path, ctx.page_dir)) is not None:
        return rel
    repo = ctx.repo()
    if repo is not None and (rel := _within(path, repo)) is not None:
        return REPO_PREFIX + rel
    raise AgentError(f"{raw} is outside the page folder and the space's code repository")


def _register(header: dict[str, Any], entry: str) -> bool:
    artifacts = _list(header, "artifacts")
    if entry in artifacts:
        return False
    artifacts.append(entry)
    header["artifacts"] = artifacts
    return True


def add_artifact(ctx: PageContext, raw: str, cwd: Path | None = None) -> str:
    entry = artifact_entry(ctx, raw, cwd)
    added = False

    def mutate(header: dict[str, Any]) -> None:
        nonlocal added
        added = _register(header, entry)

    with guarded(ctx, ctx.page_dir / STATE_FILE):
        pages.update_state(ctx.page_dir, mutate)
    return f"registered artifact {entry}" if added else f"artifact already registered: {entry}"


# commit / push


def commit(ctx: PageContext, message: str) -> str:
    repo = coderepo.require_repo(ctx)
    return f"committed {coderepo.commit_all(repo, message)} in {repo}"


def push(ctx: PageContext) -> str:
    repo = coderepo.require_repo(ctx)
    remote, branch = coderepo.push_current(repo)
    return f"pushed {branch} to {remote}"


# promote


def _promoted_name(block_id: str, source: Path) -> str:
    name = source.name
    stripped = name[len(block_id) + 1 :] if name.startswith(f"{block_id}-") else name
    return stripped or name


def promote(ctx: PageContext, block_id: str) -> str:
    repo = coderepo.require_repo(ctx)
    if pages.parse_block_id(block_id) is None:
        raise AgentError(f"'{block_id}' is not a block id (bNN)")
    files = pages.block_files(ctx.page_dir, block_id)
    if not files:
        raise AgentError(f"block {block_id} has no file in blocks/")
    if len(files) > 1:
        raise AgentError(f"block {block_id} has several files: {', '.join(f.name for f in files)}")
    source = files[0]
    rel = f"{PROMOTE_DIR}/{_promoted_name(block_id, source)}"
    dest = repo / rel
    if dest.exists() and dest.read_bytes() != source.read_bytes():
        dirty = coderepo.git.run(repo, "status", "--porcelain", "--", rel).stdout.strip()
        if dirty:
            raise AgentError(f"{rel} has uncommitted changes in the code repository; commit them first")
    entry = REPO_PREFIX + rel
    message = f"docs: promote {block_id} from {ctx.page_id}"
    result: dict[str, str | None] = {}

    with guarded(ctx, ctx.page_dir / STATE_FILE, dest) as txn:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pages.update_state(ctx.page_dir, lambda header: _register(header, entry))
        txn.then(lambda: result.update(commit=coderepo.commit_paths(repo, [rel], message)))

    sha = result.get("commit")
    if sha is None:
        return f"{rel} is already up to date in the code repository"
    return f"promoted {block_id} to {rel} ({sha})"


# view


def _template_dirs(ctx: PageContext) -> list[Path]:
    dirs = [ctx.home / "templates"]
    if extra := os.environ.get(TEMPLATES_ENV):
        dirs += [Path(p).expanduser() for p in extra.split(os.pathsep) if p]
    return dirs


def find_template(ctx: PageContext, spec: str) -> tuple[str, int, list[tuple[str, bool]]]:
    """Resolve ``name`` or ``name@version`` to (name, version, slots)."""
    name, _, want = spec.partition("@")
    if not name or not _ID.match(name):
        raise AgentError(f"invalid template '{spec}'")
    found: tuple[int, list[tuple[str, bool]]] | None = None
    for base in _template_dirs(ctx):
        path = base / name / "template.yaml"
        if path.is_file():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                slots = [(str(k), bool((v or {}).get("required"))) for k, v in (data.get("slots") or {}).items()]
                found = (int(data.get("version", 1)), slots)
            except (yaml.YAMLError, AttributeError, TypeError, ValueError) as exc:
                raise AgentError(f"{path}: invalid template.yaml: {exc}") from exc
            break
    if found is None:
        found = BUILTIN_TEMPLATES.get(name)
    if found is None:
        known = ", ".join(sorted(BUILTIN_TEMPLATES))
        raise AgentError(f"template '{name}' not found (built-in: {known})")
    version, slots = found
    if want and want != str(version):
        raise AgentError(f"template '{name}' is version {version}, not {want}")
    return name, version, slots


def _bindings(ctx: PageContext, slots: list[tuple[str, bool]], data: list[str]) -> dict[str, str]:
    names = [s for s, _ in slots]
    bound: dict[str, str] = {}
    positional: list[str] = []
    for item in data:
        slot, sep, block = item.partition("=")
        if sep:
            if slot not in names:
                raise AgentError(f"template has no slot '{slot}' (slots: {', '.join(names)})")
            if slot in bound:
                raise AgentError(f"slot '{slot}' is bound twice")
            bound[slot] = block
        else:
            positional.append(item)
    free = [s for s in names if s not in bound]
    if len(positional) > len(free):
        raise AgentError(f"too many --data values for slots {', '.join(names)}")
    bound.update(zip(free, positional))

    for slot, block in bound.items():
        if pages.parse_block_id(block) is None:
            raise AgentError(f"'{block}' is not a block id (bNN)")
        files = pages.block_files(ctx.page_dir, block)
        if not any(f.name.endswith(DATA_SUFFIXES) for f in files):
            raise AgentError(f"data block {block} for slot '{slot}' not found in blocks/")
    missing = [s for s, required in slots if required and s not in bound]
    if missing:
        raise AgentError(f"required slot(s) not bound: {', '.join(missing)}")
    return {s: bound[s] for s in names if s in bound}


def create_view(ctx: PageContext, template: str, data: list[str], title: str | None = None) -> str:
    name, version, slots = find_template(ctx, template)
    bindings = _bindings(ctx, slots, data)
    blocks_dir = ctx.page_dir / pages.BLOCKS_DIR
    last = blocks_dir / pages.LAST_BLOCK_FILE

    with guarded(ctx, ctx.page_dir / PAGE_FILE, last) as txn:
        block_id = pages.allocate_block(ctx.page_dir)
        path = blocks_dir / f"{block_id}-{name}.view.md"
        txn.track(path)
        header: dict[str, Any] = {"type": "view", "template": f"{name}@{version}"}
        if title:
            header["title"] = title
        header["bindings"] = bindings
        if ctx.run is not None:
            header["created_by"] = f"run {ctx.run}"
        path.write_text(frontmatter.dumps(header, ""), encoding="utf-8")
        pages.append_block(ctx.page_dir, block_id)
    return f"created view {block_id} ({path.relative_to(ctx.page_dir).as_posix()})"
