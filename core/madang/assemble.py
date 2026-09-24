"""실행 하나의 프롬프트를 조립하고 부분별 크기를 추정한다.

프롬프트는 루트 메모리, 프로젝트 노트, 페이지 상태, 공통 작업 지시, 대상
블록, 요청 순서로 구성한다. 러너 자체의 시스템 프롬프트와 도구는 프롬프트에
들어가지 않으며, 그 크기는 러너별 추정값(runners.yaml의 ``system_est``)이다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from madang import contract
from madang.cli_agent.views import BUILTIN_TEMPLATES
from madang.config import Config, default_text
from madang.store import frontmatter, pages
from madang.store.page import STATE_FILE, project_memory, work_dir
from madang.validate import tokens

ROOT_FILE = "root.md"
TEMPLATES_DIR = "templates"
TRUNCATION_MARK = "\n..."
# 승격된 실행(tier > 1)이 여전히 읽는 상태 절.
PROMOTED_SECTIONS = ("막힌 점", "다음 할 일")

_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Part:
    """프롬프트의 한 절.

    Attributes:
        name: ``input.parts``에 기록하는 부분 이름.
        text: 프롬프트에 나타나는 절 텍스트.
        tokens: ``text``의 추정 토큰 수.
    """

    name: str
    text: str
    tokens: int


@dataclass
class Assembled:
    """프롬프트와 크기 추정.

    Attributes:
        parts: 순서대로 나열한 프롬프트 절.
        system_est: 러너 자체 시스템 프롬프트의 추정 토큰 수.
        contract: 사용한 작업 지시의 버전.
        tokenizer: 추정에 쓴 토큰 계수기.
        truncated: 블록 제한에 맞춰 잘린 페이지 기준 상대 경로 파일.
    """

    parts: list[Part]
    system_est: int
    contract: str = contract.VERSION
    tokenizer: str = tokens.TOKENIZER
    truncated: list[str] = field(default_factory=list)

    @property
    def prompt(self) -> str:
        """러너에 넘기는 텍스트."""
        return "\n\n".join(part.text for part in self.parts) + "\n"

    @property
    def total_est(self) -> int:
        """러너 시스템 프롬프트를 포함한 추정 입력 토큰 수."""
        return self.system_est + sum(part.tokens for part in self.parts)

    def estimate(self) -> dict[str, Any]:
        """실행 기록의 ``input`` 객체를 반환한다."""
        record: dict[str, Any] = {
            "parts": {
                "system_est": self.system_est,
                **{part.name: part.tokens for part in self.parts},
            },
            "total_est": self.total_est,
            "tokenizer": self.tokenizer,
        }
        if self.truncated:
            record["truncated"] = list(self.truncated)
        return record


def assemble(
    page_dir: Path,
    target: str | None,
    request: str,
    tier: int,
    *,
    cfg: Config,
    runner: str,
) -> Assembled:
    """페이지 실행 하나의 프롬프트를 조립한다.

    Args:
        page_dir: 페이지 폴더.
        target: 요청 대상 블록 id. 페이지 전체면 None.
        request: 메시지 본문.
        tier: 승격 단계. 1보다 크면 상태의 막힌 점과 다음 할 일 절만
            넣는다.
        cfg: 앱 홈 설정.
        runner: 러너 이름. ``system_est``를 고른다.

    Returns:
        프롬프트와 그 추정.

    Raises:
        OSError: 메모리나 블록 파일을 읽을 수 없는 경우.
        ValueError: 대상 블록에 파일이 없는 경우.
    """
    limit = cfg.madang.limits.block_input_tokens
    truncated: list[str] = []
    sections = [
        ("root", "root", _root_text(cfg.home)),
        ("project", "project", _project_text(page_dir)),
        ("state", "state", _state_text(page_dir, tier)),
        (
            "contract",
            f'instructions version="{contract.VERSION}"',
            _contract_text(page_dir, cfg),
        ),
    ]
    if target is not None:
        body = _target_text(page_dir, target, limit, truncated)
        sections.append(("target", f'target block="{target}"', body))
    sections.append(("request", "request", request.strip()))
    return Assembled(
        parts=[_part(name, tag, body) for name, tag, body in sections],
        system_est=system_estimate(cfg, runner),
        tokenizer=tokens.tokenizer_name(),
        truncated=truncated,
    )


def system_estimate(cfg: Config, runner: str) -> int:
    """runners.yaml에서 ``runner``의 ``system_est``를 반환한다.

    앱 홈의 runners.yaml에 값이 없으면 번들된 기본 runners.yaml의 값을
    쓴다. 예전에 만든 앱 홈도 추정이 0이 되지 않게 하기 위해서다.

    Args:
        cfg: 앱 홈 설정.
        runner: 러너 이름.

    Returns:
        설정값, 없으면 기본 runners.yaml의 값, 그것도 없으면 0.
    """
    spec = cfg.runners.get(runner)
    value = getattr(spec, "system_est", None) if spec else None
    if _is_count(value):
        return value
    default = _default_runners().get(runner) or {}
    value = default.get("system_est") if isinstance(default, dict) else None
    return value if _is_count(value) else 0


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@lru_cache(maxsize=1)
def _default_runners() -> dict[str, Any]:
    return yaml.safe_load(default_text("runners.yaml")) or {}


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """``text``를 앞부분을 남겨 최대 ``limit`` 토큰으로 자른다.

    Args:
        text: 자를 텍스트.
        limit: 토큰 제한.

    Returns:
        ``(text, cut)``. 잘린 텍스트는 ``TRUNCATION_MARK``로 끝난다.
    """
    if tokens.count_tokens(text) <= limit:
        return text, False
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if tokens.count_tokens(text[:mid] + TRUNCATION_MARK) <= limit:
            low = mid
        else:
            high = mid - 1
    return text[:low] + TRUNCATION_MARK, True


def _part(name: str, tag: str, body: str) -> Part:
    closing = tag.split(" ", 1)[0]
    text = f"<{tag}>\n{body.strip()}\n</{closing}>"
    return Part(name=name, text=text, tokens=tokens.count_tokens(text))


def _body(path: Path) -> str:
    if not path.is_file():
        return ""
    return frontmatter.split(path.read_text(encoding="utf-8")).body


def _root_text(home: Path) -> str:
    return _body(home / ROOT_FILE)


def _project_text(page_dir: Path) -> str:
    memory = project_memory(page_dir)
    return _body(memory) if memory else ""


def _state_text(page_dir: Path, tier: int) -> str:
    path = page_dir / STATE_FILE
    text = path.read_text(encoding="utf-8")
    if tier <= 1:
        return f"path: {path}\n\n{text}"
    kept = [
        section
        for title, section in _sections(frontmatter.split(text).body)
        if title in PROMOTED_SECTIONS
    ]
    return f"path: {path}\n\n" + "\n".join(kept)


def _sections(body: str) -> Iterator[tuple[str, str]]:
    """본문의 ``## `` 절마다 ``(title, text)``를 낸다."""
    heads = list(_HEADING.finditer(body))
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        yield head.group(1), body[head.start() : end]


def _contract_text(page_dir: Path, cfg: Config) -> str:
    return contract.render(
        repo=str(work_dir(page_dir)),
        page=str(page_dir),
        templates=_template_names(cfg.home),
        failures=cfg.routes.limits.blocked_after_failures,
    )


def _template_names(home: Path) -> list[str]:
    installed = {
        p.parent.name for p in (home / TEMPLATES_DIR).glob("*/template.yaml")
    }
    return sorted(installed | set(BUILTIN_TEMPLATES))


def _target_text(
    page_dir: Path, block: str, limit: int, truncated: list[str]
) -> str:
    files = pages.block_files(page_dir, block)
    if not files:
        raise ValueError(f"block '{block}' has no file in blocks/")
    data = [
        path
        for bound in _bindings(files)
        for path in pages.block_files(page_dir, bound)
    ]
    chunks = []
    for path in dict.fromkeys([*files, *data]):
        rel = path.relative_to(page_dir).as_posix()
        text, cut = truncate(path.read_text(encoding="utf-8"), limit)
        if cut:
            truncated.append(rel)
        chunks.append(f'<file path="{rel}">\n{text.strip()}\n</file>')
    return "\n".join(chunks)


def _bindings(files: list[Path]) -> list[str]:
    """``files`` 중 view 파일이 묶은 데이터 블록 id를 반환한다."""
    bound: list[str] = []
    for path in files:
        if not path.name.endswith(".view.md"):
            continue
        header, _ = frontmatter.read(path)
        bindings = header.get("bindings") or {}
        if isinstance(bindings, dict):
            bound += [str(b) for b in bindings.values()]
    return bound
