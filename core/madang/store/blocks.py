"""블록 읽기·쓰기: 메시지(log.md 항목)와 ``blocks/`` 파일 블록.

블록 종류는 파일 이름으로 정한다. ``.view.md``는 view, 그 밖의 ``.md``는
doc, ``.json``·``.csv``는 data(머리부는 ``.meta.yaml`` 부속 파일),
``.source.yaml``은 API 데이터, ``.code.yaml``·``.term.yaml``·``.site.yaml``은
각 종류다. 알 수 없는 파일은 doc으로 본다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from madang.store import frontmatter, pages
from madang.store.files import atomic_write
from madang.store.log import Message, read_messages
from madang.validate.issues import Issue

META_SUFFIX = ".meta.yaml"
USER = "user"

# 파일 이름 끝 -> (블록 종류, 데이터 형식)
_KINDS: tuple[tuple[str, str, str | None], ...] = (
    (".view.md", "view", None),
    (".source.yaml", "data", "source"),
    (".code.yaml", "code", None),
    (".term.yaml", "term", None),
    (".site.yaml", "site", None),
    (".json", "data", "json"),
    (".csv", "data", "csv"),
    (".md", "doc", None),
)
_DATA_FILES = (".json", ".csv")
# 머리부 패치로 바꿀 수 있는 키.
PATCHABLE = ("title", "bindings", "presets", "active_preset", "theme")


class BlockNotFoundError(LookupError):
    """페이지에 그 id의 블록이 없다."""


class BlockContentError(ValueError):
    """저장하려는 블록 내용이 파일 형식에 맞지 않는다.

    Attributes:
        issues: 문제 목록.
    """

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__(issues[0].message if issues else "invalid block")
        self.issues = issues


@dataclass(frozen=True)
class FileBlock:
    """``blocks/``의 파일 블록.

    Attributes:
        id: 블록 id.
        path: 블록 파일.
        type: 블록 종류.
        format: 데이터 형식. data 블록만.
    """

    id: str
    path: Path
    type: str
    format: str | None = None

    @property
    def meta_path(self) -> Path:
        """json·csv 데이터의 머리부 부속 파일."""
        return self.path.with_name(_stem(self.path.name) + META_SUFFIX)

    @property
    def is_markdown(self) -> bool:
        """머리부가 파일 안의 YAML 울타리에 있는지 여부."""
        return self.path.suffix == ".md"

    @property
    def has_sidecar(self) -> bool:
        """머리부가 ``.meta.yaml`` 부속 파일에 있는지 여부."""
        return self.path.suffix in _DATA_FILES

    def files(self) -> list[Path]:
        """블록을 이루는 파일(부속 파일 포함)."""
        extra = [self.meta_path] if self.meta_path.is_file() else []
        return [self.path, *extra]


def _stem(name: str) -> str:
    for suffix, _, _ in _KINDS:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name.rsplit(".", 1)[0]


def classify(path: Path) -> tuple[str, str | None]:
    """파일 이름으로 ``(블록 종류, 데이터 형식)``을 반환한다."""
    for suffix, kind, fmt in _KINDS:
        if path.name.endswith(suffix):
            return kind, fmt
    return "doc", None


def find_file_block(page_dir: Path, block_id: str) -> FileBlock | None:
    """``blocks/``에서 블록 파일을 찾는다. 파일 블록이 아니면 None."""
    files = pages.block_files(page_dir, block_id)
    if not files:
        return None
    kind, fmt = classify(files[0])
    return FileBlock(id=block_id, path=files[0], type=kind, format=fmt)


def find_message(page_dir: Path, block_id: str) -> Message | None:
    """log.md에서 메시지 블록을 찾는다. 없으면 None."""
    return next((m for m in read_messages(page_dir) if m.id == block_id), None)


# 머리부


def message_header(message: Message) -> dict[str, Any]:
    """메시지 블록의 머리부를 반환한다.

    Args:
        message: log.md의 메시지.

    Returns:
        ``id``, ``type``, ``role``, ``ts``, ``text``와, 있으면 ``run``,
        사용자 메시지면 ``target``.
    """
    header: dict[str, Any] = {
        "id": message.id,
        "type": "message",
        "role": message.role,
        "ts": message.ts,
        "text": message.text,
    }
    run = message.attrs.get("run", "")
    if run.isdigit():
        header["run"] = int(run)
    if message.role == USER:
        header["target"] = _target(message.attrs)
    return header


def _target(attrs: dict[str, str]) -> dict[str, Any]:
    target: dict[str, Any] = {}
    block = attrs.get("target")
    if block and block != "page":
        target["block"] = block
    if attrs.get("elements"):
        target["elements"] = attrs["elements"].split(",")
    if attrs.get("mode"):
        target["mode"] = attrs["mode"]
    return target


def read_header(block: FileBlock) -> dict[str, Any]:
    """파일 블록에 저장된 머리부 매핑을 반환한다(``id``·``file`` 제외).

    Raises:
        FrontmatterError: md 머리부를 파싱할 수 없다.
        yaml.YAMLError: YAML 파일을 파싱할 수 없다.
    """
    if block.is_markdown:
        header, _ = frontmatter.read(block.path)
        return header
    source = block.meta_path if block.has_sidecar else block.path
    if not source.is_file():
        return {}
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def file_header(page_dir: Path, block: FileBlock) -> dict[str, Any]:
    """앱에 보여 줄 파일 블록의 머리부를 반환한다.

    머리부를 읽을 수 없어도 id, 종류, 파일은 돌려준다.

    Args:
        page_dir: 페이지 폴더.
        block: 파일 블록.

    Returns:
        ``id``, ``type``, ``file``, ``title``과 파일 머리부의 나머지 키.
    """
    try:
        stored = read_header(block)
    except (frontmatter.FrontmatterError, yaml.YAMLError, OSError):
        stored = {}
    header: dict[str, Any] = {
        "id": block.id,
        "type": block.type,
        "file": block.path.relative_to(page_dir).as_posix(),
        "title": str(stored.get("title") or _title(block)),
    }
    if block.format is not None:
        header["format"] = block.format
    for key, value in stored.items():
        if key in ("id", "type", "file", "title"):
            continue
        header[key] = str(value) if key == "created_by" else value
    return header


def _title(block: FileBlock) -> str:
    stem = _stem(block.path.name)
    return stem.removeprefix(f"{block.id}-") or block.id


def block_header(page_dir: Path, block_id: str) -> dict[str, Any]:
    """메시지든 파일이든 블록 하나의 머리부를 반환한다.

    Raises:
        BlockNotFoundError: 그 id의 블록이 없다.
    """
    block = find_file_block(page_dir, block_id)
    if block is not None:
        return file_header(page_dir, block)
    message = find_message(page_dir, block_id)
    if message is not None:
        return message_header(message)
    raise BlockNotFoundError(f"block '{block_id}' not found")


def page_blocks(page_dir: Path, order: list[str]) -> list[dict[str, Any]]:
    """page.md ``blocks`` 순서대로 블록 머리부를 반환한다.

    파일도 메시지도 없는 id는 건너뛴다.

    Args:
        page_dir: 페이지 폴더.
        order: page.md의 ``blocks``.

    Returns:
        블록 머리부 목록.
    """
    messages = {m.id: m for m in read_messages(page_dir)}
    headers = []
    for block_id in order:
        block = find_file_block(page_dir, block_id)
        if block is not None:
            headers.append(file_header(page_dir, block))
        elif block_id in messages:
            headers.append(message_header(messages[block_id]))
    return headers


# 쓰기


def check_content(block: FileBlock, content: str) -> None:
    """블록 파일에 쓸 내용이 형식에 맞는지 본다.

    Args:
        block: 대상 블록.
        content: 새 파일 내용.

    Raises:
        BlockContentError: md 머리부, JSON, YAML이 올바르지 않다.
    """
    where = block.path
    if block.is_markdown:
        try:
            frontmatter.load_header(frontmatter.split(content))
        except frontmatter.FrontmatterError as exc:
            raise BlockContentError(
                [Issue("frontmatter", str(exc), exc.line, where)]
            ) from exc
    elif block.path.suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            issue = Issue(
                "invalid-value", f"invalid JSON: {exc.msg}", exc.lineno
            )
            raise BlockContentError([_at(issue, where)]) from exc
    elif block.path.suffix == ".yaml":
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            issue = Issue("invalid-value", f"invalid YAML: {exc}")
            raise BlockContentError([_at(issue, where)]) from exc
        if not isinstance(data, dict):
            issue = Issue("invalid-value", "YAML block must be a mapping")
            raise BlockContentError([_at(issue, where)])


def _at(issue: Issue, path: Path) -> Issue:
    return Issue(issue.code, issue.message, issue.line, path)


def write_content(block: FileBlock, content: str) -> None:
    """검사한 뒤 블록 파일 전체를 바꾼다.

    Raises:
        BlockContentError: 내용이 파일 형식에 맞지 않는다.
    """
    check_content(block, content)
    atomic_write(block.path, content)


def update_header(
    block: FileBlock, mutate: Callable[[dict[str, Any]], None]
) -> None:
    """``mutate``로 블록의 저장된 머리부를 바꾼다.

    md는 본문을 그대로 두고 머리부만, json·csv는 부속 파일을, YAML
    블록은 파일 전체 매핑을 다시 쓴다.

    Args:
        block: 대상 블록.
        mutate: 머리부 매핑을 제자리에서 바꾼다.
    """
    if block.is_markdown:
        pages.update_header(block.path, mutate)
        return
    header = read_header(block)
    mutate(header)
    target = block.meta_path if block.has_sidecar else block.path
    atomic_write(
        target, yaml.safe_dump(header, sort_keys=False, allow_unicode=True)
    )


def create_file_block(
    page_dir: Path,
    kind: str,
    name: str,
    content: str,
    fmt: str = "json",
) -> str:
    """Doc 또는 data 블록을 만들어 page.md 끝에 붙인다.

    doc은 ``bNN-<name>.md``(머리부 ``type``, ``title``, ``created_by``)이고
    ``content``가 본문이다. data는 ``bNN-<name>.<fmt>``에 ``content``를
    그대로 쓰고 머리부를 ``.meta.yaml``에 둔다.

    Args:
        page_dir: 페이지 폴더.
        kind: ``doc`` 또는 ``data``.
        name: 파일 이름용 슬러그.
        content: doc 본문 또는 데이터 텍스트.
        fmt: data 형식. ``json`` 또는 ``csv``.

    Returns:
        새 블록 id.

    Raises:
        BlockContentError: 데이터가 형식에 맞지 않는다.
    """
    header = {"type": kind, "title": name, "created_by": USER}
    if kind == "doc":
        suffix, text = ".md", frontmatter.dumps(header, content)
    else:
        suffix, text = f".{fmt}", content
    probe = FileBlock("b00", page_dir / pages.BLOCKS_DIR / f"x{suffix}", kind)
    check_content(probe, text)
    block_id = pages.allocate_block(page_dir)
    path = page_dir / pages.BLOCKS_DIR / f"{block_id}-{name}{suffix}"
    atomic_write(path, text)
    if kind == "data":
        block = FileBlock(block_id, path, kind, fmt)
        atomic_write(
            block.meta_path,
            yaml.safe_dump(header, sort_keys=False, allow_unicode=True),
        )
    pages.append_block(page_dir, block_id)
    return block_id


def remove_from_order(page_dir: Path, block_id: str) -> None:
    """page.md ``blocks``에서 ``block_id``를 뺀다."""

    def mutate(header: dict[str, Any]) -> None:
        header["blocks"] = [
            str(b) for b in header.get("blocks") or [] if str(b) != block_id
        ]

    pages.update_page(page_dir, mutate)
