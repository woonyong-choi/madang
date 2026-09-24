"""정적 사이트 만들기: 문서마다 HTML 껍데기와 렌더러, 고정한 뷰어 사본.

사이트 모양::

    <문서>.html         껍데기. md 원문과 렌더러 context(JSON)를 싣고
                        브라우저에서 renderDocument로 그린다. context에는
                        앱 기본 테마와 같은 토큰(``tokens.json``)이 든다.
    <포함한 파일>        그대로 복사(md 원문, 이미지, 데이터 등).
    index.html          포함한 문서에 index.md가 없으면 문서 목록.
    .nojekyll           GitHub Pages가 ``_madang/``을 그대로 내보내게 한다.
    _madang/runtime/    렌더러(``templates/_runtime``의 같은 파일).
    _madang/viewers/<해시>/<이름>/  게시 시점 해시로 고정한 뷰어 사본.
    _madang/site.json   문서 목록, 렌더러 해시, 뷰어와 그 해시.

서버나 Node에서 미리 그리지 않는다. 로컬(앱 문서 탭)과 웹이 같은 렌더러
코드를 돌리게 하기 위해서다.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import quote

from madang.cli_agent.views import TEMPLATES_ENV
from madang.publish.settings import PublishError
from madang.publish.views import PinnedCopy, document_views
from madang.recorder.published import ViewerPin
from madang.store import frontmatter
from madang.viewers import Registry

SITE_DIR = "_madang"
SITE_MANIFEST = f"{SITE_DIR}/site.json"
RUNTIME_DIR = "_runtime"
RENDERER = "document.js"
# 기본 앱 토큰. 앱 기본 테마와 같은 값이라 게시도 이것을 context에 싣는다.
TOKENS_FILE = "tokens.json"
# 사이트에 싣는 렌더러 파일(``templates/_runtime`` 기준)
RUNTIME_FILES = (
    RENDERER,
    "document.css",
    "vendor/marked.umd.js",
    "vendor/marked.LICENSE",
    "THIRD_PARTY_NOTICES.md",
)
INDEX_PAGE = "index.html"
NO_JEKYLL = ".nojekyll"
MARKDOWN_SUFFIX = ".md"
PAGE_SUFFIX = ".html"
_SKIPPED_VIEWER_DIRS = (".git",)


@dataclass(frozen=True)
class Document:
    """게시한 문서 하나.

    Attributes:
        source: md 원문(프로젝트 기준 경로).
        page: 껍데기 HTML(사이트 기준 경로).
        title: 머리부 ``title``, 없으면 원문 경로.
    """

    source: str
    page: str
    title: str


@dataclass
class Site:
    """만든 사이트.

    Attributes:
        folder: 사이트 폴더.
        documents: 게시한 문서.
        viewers: 담은 뷰어와 그 해시.
        warnings: 뷰어를 쓰지 못해 표로 대체될 펜스 등.
    """

    folder: Path
    documents: list[Document] = field(default_factory=list)
    viewers: list[ViewerPin] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def find_runtime() -> Path:
    """렌더러 폴더(``templates/_runtime``)를 찾는다.

    ``MADANG_TEMPLATES``(앱이 번들한 템플릿 폴더)에서 먼저 찾고, 없으면
    이 패키지가 든 저장소의 ``templates/_runtime``을 쓴다.

    Raises:
        PublishError: 렌더러가 없다(``runtime-missing``).
    """
    extra = os.environ.get(TEMPLATES_ENV, "")
    bases = [Path(p).expanduser() for p in extra.split(os.pathsep) if p]
    bases.append(Path(__file__).resolve().parents[3] / "templates")
    for base in bases:
        if (base / RUNTIME_DIR / RENDERER).is_file():
            return base / RUNTIME_DIR
    raise PublishError(
        "runtime-missing",
        f"templates/{RUNTIME_DIR}/{RENDERER} not found; set {TEMPLATES_ENV}",
    )


def read_tokens(runtime: Path) -> dict[str, Any]:
    """렌더러 폴더의 기본 앱 토큰을 ``{"tokens": {...}}``로 읽는다.

    앱 문서 탭이 기본 테마로 넘기는 토큰과 같은 값이라, 게시 페이지도
    이것을 넣어야 로컬과 웹이 같은 모양이 된다.

    Raises:
        PublishError: 토큰 파일이 없거나 JSON 객체가 아니다
            (``runtime-missing``).
    """
    path = runtime / TOKENS_FILE
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublishError(
            "runtime-missing", f"cannot read {path}: {exc}"
        ) from exc
    if not isinstance(tokens, dict):
        raise PublishError("runtime-missing", f"{path} must be a JSON object")
    return {"tokens": tokens}


def collect(root: Path, include: list[str], exclude: list[Path]) -> list[str]:
    """포함 경로에서 게시할 파일을 모은다.

    폴더는 안의 파일을 모두 담되 이름이 ``.``으로 시작하는 파일·폴더
    (``.madang/``, ``.git/`` 등)와 ``exclude`` 폴더는 뺀다. 파일로 적은
    경로는 그대로 담는다.

    Args:
        root: 프로젝트 폴더.
        include: 프로젝트 기준 경로 목록.
        exclude: 뺄 폴더(게시 대상 폴더 등).

    Returns:
        프로젝트 기준 posix 경로, 정렬됨.

    Raises:
        PublishError: 포함 경로가 비었거나(``include-empty``), 없거나
            (``include-missing``), 프로젝트 밖이다(``include-outside``).
    """
    if not include:
        raise PublishError(
            "include-empty", "publish.include lists no paths to publish"
        )
    base = root.resolve()
    skipped = [path.resolve() for path in exclude]
    found: set[str] = set()
    for entry in include:
        path = (base / entry).resolve()
        if not path.is_relative_to(base):
            raise PublishError(
                "include-outside", f"{entry!r} points outside the project"
            )
        if path.is_file():
            found.add(path.relative_to(base).as_posix())
        elif path.is_dir():
            found.update(_walk(base, path, skipped))
        else:
            raise PublishError("include-missing", f"{entry!r} does not exist")
    return sorted(found)


def build(
    root: Path,
    include: list[str],
    *,
    out: Path,
    registry: Registry,
    exclude: list[Path] | None = None,
) -> Site:
    """프로젝트의 포함 경로로 정적 사이트를 ``out``에 만든다.

    Args:
        root: 프로젝트 폴더.
        include: 포함 경로.
        out: 사이트를 만들 빈 폴더(없으면 만든다).
        registry: 뷰어 등록부.
        exclude: 모을 때 뺄 폴더.

    Returns:
        만든 사이트.

    Raises:
        PublishError: 포함 경로나 렌더러에 문제가 있거나, 한 경로에 두
            파일이 나온다(``path-conflict``).
    """
    runtime = find_runtime()
    tokens = read_tokens(runtime)
    files = collect(root, include, exclude or [])
    site = Site(out)
    copies: dict[tuple[str, str], PinnedCopy] = {}
    outputs: set[str] = set()
    for rel in files:
        _claim(outputs, rel, rel)
        _copy(root / rel, out / rel)
    for rel in (f for f in files if f.endswith(MARKDOWN_SUFFIX)):
        document = _document(root, rel)
        _claim(outputs, document.page, rel)
        markdown = (root / rel).read_text(encoding="utf-8")
        views = document_views(
            markdown,
            registry,
            document_dir=(root / rel).parent,
            project=root,
        )
        _write_page(out, document, markdown, {**views.context, **tokens})
        site.documents.append(document)
        site.warnings += [f"{rel}: {w}" for w in views.warnings]
        copies.update({(c.name, c.pin): c for c in views.copies})
    if INDEX_PAGE not in outputs:
        _write_index(out, root.name, site.documents, tokens)
    for copy in copies.values():
        _copy_viewer(copy, out)
    site.viewers = [ViewerPin(name=n, pin=p) for n, p in sorted(copies)]
    _write_runtime(runtime, out)
    (out / NO_JEKYLL).write_bytes(b"")
    _write_manifest(out, site, runtime)
    return site


def _claim(outputs: set[str], page: str, source: str) -> None:
    """사이트 경로 하나를 차지한다. 이미 쓰였거나 예약된 곳이면 오류다."""
    if page in outputs or page.split("/", 1)[0] in (SITE_DIR, NO_JEKYLL):
        raise PublishError(
            "path-conflict", f"{source} would overwrite site file {page}"
        )
    outputs.add(page)


def _walk(base: Path, folder: Path, skipped: list[Path]) -> list[str]:
    found = []
    for current, dirs, names in os.walk(folder):
        here = Path(current)
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".") and (here / d).resolve() not in skipped
        )
        for name in names:
            path = here / name
            if name.startswith(".") or not path.is_file():
                continue
            if path.resolve().is_relative_to(base):
                found.append(path.relative_to(base).as_posix())
    return found


def _document(root: Path, rel: str) -> Document:
    page = rel[: -len(MARKDOWN_SUFFIX)] + PAGE_SUFFIX
    return Document(rel, page, _title(root / rel) or rel)


def _title(path: Path) -> str | None:
    """머리부의 ``title``. 없거나 읽을 수 없으면 None."""
    try:
        parts = frontmatter.split(path.read_text(encoding="utf-8"))
        header = frontmatter.load_header(parts)
    except (OSError, UnicodeDecodeError, frontmatter.FrontmatterError):
        return None
    title = header.get("title")
    return str(title) if title else None


def _write_page(
    out: Path, document: Document, markdown: str, context: dict[str, Any]
) -> None:
    depth = document.page.count("/")
    shell = Template(
        resources.files("madang.publish")
        .joinpath("shell.html")
        .read_text(encoding="utf-8")
    )
    text = shell.substitute(
        title=html.escape(document.title),
        base="../" * depth,
        markdown=_script_json(markdown),
        context=_script_json(context),
    )
    path = out / document.page
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_index(
    out: Path, title: str, documents: list[Document], tokens: dict[str, Any]
) -> None:
    """문서 목록을 마크다운으로 만들어 같은 렌더러로 그리는 첫 페이지."""
    lines = [f"# {_link_text(title)}", ""]
    lines += [f"- [{_link_text(d.title)}]({quote(d.page)})" for d in documents]
    index = Document(INDEX_PAGE, INDEX_PAGE, title)
    context = {"views": {}, **tokens}
    _write_page(out, index, "\n".join(lines) + "\n", context)


def _link_text(text: str) -> str:
    return "".join(f"\\{c}" if c in "\\[]*_`<>#" else c for c in text)


def _script_json(value: Any) -> str:
    """``<script type="application/json">`` 안에 둘 JSON 텍스트."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _copy_viewer(copy: PinnedCopy, out: Path) -> None:
    shutil.copytree(
        copy.folder,
        out / SITE_DIR / "viewers" / copy.pin / copy.name,
        ignore=shutil.ignore_patterns(*_SKIPPED_VIEWER_DIRS),
    )


def _write_runtime(runtime: Path, out: Path) -> None:
    for rel in RUNTIME_FILES:
        _copy(runtime / rel, out / SITE_DIR / "runtime" / rel)


def _write_manifest(out: Path, site: Site, runtime: Path) -> None:
    renderer = hashlib.sha256((runtime / RENDERER).read_bytes()).hexdigest()
    data = {
        "version": 1,
        "renderer": renderer,
        "documents": [
            {"source": d.source, "page": d.page, "title": d.title}
            for d in site.documents
        ],
        "viewers": [v.model_dump() for v in site.viewers],
    }
    path = out / SITE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
