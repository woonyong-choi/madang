"""데모 세 프로젝트(wiki, resume, code)를 만들고 페이지 두 개씩 남긴다.

원본은 ``samples/``(위키 노트, 이력서 문서), ``templates/viewers/``(이력서
뷰어), 이 폴더의 ``projects/``(기억·설정, 코드)다. 임시 앱 홈으로 저장소
core(``madang serve``)를 띄워 API로만 다음을 한다. 사용자 ``~/.madang``은
건드리지 않는다.

1. 세 프로젝트를 등록하고 code를 git 저장소로 만들어 첫 커밋을 한다.
2. 프로젝트마다 작은 요청 하나를 실제로 보내 "실행 완료 페이지"를 남긴다.
3. code에 버그를 드러내는 테스트를 커밋한다(완료 페이지의 자동 머지는 모든
   테스트 통과가 조건이라 이 테스트는 그 뒤에 넣는다).
4. 프로젝트마다 "요청 대기 페이지"를 만들어 목표와 다음 할 일을 채운다.
5. 등록을 해제한 뒤 새 임시 앱 홈에 다시 등록해 페이지가 두 개씩 보이는지
   확인한다.

앱 홈 설정은 ``madang init``이 만든 기본 config.yaml 그대로다. git은 core
API로만 실행한다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checklist"))

from checklist import ApiError, Core  # noqa: E402

from madang.store import frontmatter  # noqa: E402

FLOW_POLL_SECONDS = 5.0
FLOW_TIMEOUT_SECONDS = 1800.0
PROJECTS = ("wiki", "resume", "code")
# 원본에서 프로젝트 .madang/이 될 폴더 이름.
RECORDS_SOURCE = "madang"


@dataclass(frozen=True)
class DonePage:
    """실제로 한 번 실행해 둘 페이지."""

    title: str
    kind: str
    request: str


@dataclass(frozen=True)
class WaitingPage:
    """아직 실행하지 않은 페이지. 요청 문장은 README에 있다."""

    title: str
    kind: str
    goal: str
    steps: tuple[str, ...]


DONE = {
    "wiki": DonePage(
        "도구 노트 보강",
        "doc",
        "notes/tools.md 노트 끝에 '## 물뿌리개' 절을 새로 추가하고, 그 절에 "
        "'물뿌리개는 쓰고 나서 거꾸로 세워 말린다.' 한 문장만 넣어 줘. "
        "다른 파일은 고치지 않는다.",
    ),
    "resume": DonePage(
        "자기소개 다듬기",
        "doc",
        "docs/resume.json의 summary 끝에 '대용량 트래픽에서도 정확한 정산을 "
        "지키는 일을 좋아합니다.' 한 문장을 덧붙여 줘. 다른 키와 다른 파일은 "
        "고치지 않는다.",
    ),
    "code": DonePage(
        "합계 함수 설명",
        "code",
        "receipt.py의 subtotal 함수 docstring에 사용 예 한 줄"
        "(subtotal([(3000, 2), (1500, 1)])는 7500)을 덧붙여 줘. 코드 동작과 "
        "다른 함수, 테스트 파일은 고치지 않는다.",
    ),
}

WAITING = {
    "wiki": WaitingPage(
        "가을 준비 노트",
        "doc",
        "텃밭 노트(notes/garden.md)에 가을 준비 절을 더하고 게시된 위키 "
        "사이트에 반영한다.",
        (
            "notes/garden.md 끝에 '## 가을 준비' 절을 더한다.",
            "게시된 site/notes/garden.html에 새 절이 있는지 확인한다.",
        ),
    ),
    "resume": WaitingPage(
        "이력서 직함 바꾸기",
        "doc",
        "이력서 데이터(docs/resume.json)의 직함과 첫 경력 성과를 고치고, 문서 "
        "탭과 게시 화면이 같은지 본다.",
        (
            "docs/resume.json의 title과 바다페이 highlights를 고친다.",
            "게시된 site/docs/resume.html에 새 내용이 있는지 확인한다.",
        ),
    ),
    "code": WaitingPage(
        "할인 계산 버그",
        "code",
        "apply_discount가 10% 할인에 0원을 내는 버그를 고쳐 모든 테스트를 "
        "통과시키고 자동 머지한다.",
        (
            "apply_discount의 할인 계산을 고친다.",
            "python3 -m unittest -q가 모두 통과하는지 확인한다.",
        ),
    ),
}


# 준비


def demo_git_env(work: Path) -> dict[str, str]:
    """데모 커밋에 쓸 임시 git 설정(작성자, 서명 없음)의 환경 변수."""
    config = work / "gitconfig"
    config.write_text(
        "[user]\n\tname = Madang Demo\n\temail = demo@localhost\n"
        "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
    )
    return {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}


def lay_out(repo: Path, here: Path, dest: Path) -> None:
    """원본 파일을 ``dest`` 아래 세 프로젝트 폴더로 복사한다.

    원본의 ``madang/``은 프로젝트의 ``.madang/``(기억·설정)이 된다. 원본을
    점 없는 이름으로 두는 것은 저장소가 ``.madang/``을 git에서 빼기 때문이다.
    """
    samples = repo / "samples"
    for name in PROJECTS:
        source = here / "projects" / name
        shutil.copytree(
            source, dest / name, ignore=shutil.ignore_patterns(RECORDS_SOURCE)
        )
        shutil.copytree(source / RECORDS_SOURCE, dest / name / ".madang")
    shutil.copytree(samples / "wiki" / "notes", dest / "wiki" / "notes")
    shutil.copytree(samples / "resume" / "docs", dest / "resume" / "docs")
    shutil.copytree(
        repo / "templates" / "viewers" / "resume-basic",
        dest / "resume" / ".madang" / "viewers" / "resume-basic",
    )
    shutil.copy(here / "README.md", dest / "README.md")


def start_core(repo: Path, home: Path, env: dict[str, str]) -> Core:
    """새 임시 앱 홈을 만들고 core를 띄운다."""
    home.parent.mkdir(parents=True, exist_ok=True)
    core = Core(
        repo,
        home,
        {**env, "MADANG_HOME": str(home)},
        home.parent / f"{home.name}.log",
    )
    core.madang("init")
    core.start()
    return core


def register(core: Core, dest: Path) -> None:
    """세 프로젝트를 폴더 이름을 id로 등록한다."""
    for name in PROJECTS:
        core.call("POST", "/projects", {"path": str(dest / name), "id": name})


def unregister(core: Core) -> None:
    """세 프로젝트의 등록을 지운다. 폴더와 ``.madang/``은 남는다."""
    for name in PROJECTS:
        core.call("DELETE", f"/projects/{name}")


def commit(core: Core, message: str, paths: list[str] | None = None) -> str:
    """코드 프로젝트의 변경을 core git API로 스테이징하고 커밋한다."""
    core.call(
        "POST", "/projects/code/git/stage", {"paths": paths} if paths else {}
    )
    _, done = core.call(
        "POST", "/projects/code/git/commit", {"message": message}
    )
    return done["commit"]


# 페이지


def new_page(core: Core, project: str, title: str, kind: str) -> str:
    """페이지를 만들고 id를 돌려준다."""
    _, page = core.call(
        "POST", f"/projects/{project}/pages", {"title": title, "kind": kind}
    )
    return page["id"]


def run_done_page(core: Core, project: str) -> dict[str, Any]:
    """요청 하나를 보내 흐름이 끝날 때까지 기다린 뒤 페이지 상세를 준다.

    Raises:
        RuntimeError: 흐름이 사람의 답을 기다리거나 완료되지 않았다.
        TimeoutError: 흐름이 제한 시간 안에 끝나지 않았다.
    """
    spec = DONE[project]
    page = new_page(core, project, spec.title, spec.kind)
    core.call("POST", f"/pages/{page}/messages", {"text": spec.request})
    deadline = time.monotonic() + FLOW_TIMEOUT_SECONDS
    while (detail := core.get(f"/pages/{page}"))["busy"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"flow on {page} still running")
        time.sleep(FLOW_POLL_SECONDS)
    if detail.get("waiting") or detail["status"] != "done":
        waiting = json.dumps(detail.get("waiting"), ensure_ascii=False)
        raise RuntimeError(
            f"{project}/{page} ended as {detail['status']}, waiting={waiting}"
        )
    return detail


def make_waiting_page(core: Core, project: str) -> str:
    """요청 대기 페이지를 만들고 ledger 목표·다음 할 일을 채운다."""
    spec = WAITING[project]
    page = new_page(core, project, spec.title, spec.kind)
    content = core.get(f"/pages/{page}/memory")["ledger"]["content"]
    parts = frontmatter.split(content)
    parts.body = ledger_body(spec)
    core.call(
        "PUT",
        f"/pages/{page}/memory/ledger",
        {"content": frontmatter.join(parts)},
    )
    for n, step in enumerate(spec.steps, 1):
        core.call(
            "PATCH",
            f"/pages/{page}/ledger/tasks",
            {"id": f"t{n}", "status": "todo", "title": step},
        )
    return page


def ledger_body(spec: WaitingPage) -> str:
    """요청 대기 페이지의 ledger 본문."""
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(spec.steps, 1))
    return (
        f"## 목표\n{spec.goal}\n\n## 결정 사항\n\n"
        "## 현재 상태\n아직 요청을 보내지 않았다.\n\n"
        f"## 다음 할 일\n{steps}\n\n## 막힌 점\n\n## 로그\n"
    )


# 기록과 확인


def run_rows(core: Core, project: str, page: str) -> list[str]:
    """페이지 실행마다 러너·결과·입력 추정 줄."""
    rows = []
    for ref in core.get(f"/pages/{page}")["runs"]:
        record = core.get(f"/pages/{page}/runs/{ref['n']}")
        total = (record.get("input") or {}).get("total_est")
        rows.append(
            f"| {project} | {page} | {ref['n']} | {record.get('kind')} | "
            f"{record.get('runner')}/{record.get('model')} | "
            f"{record.get('result_status')} | {total} |"
        )
    return rows


def verify(core: Core, dest: Path) -> list[str]:
    """새 앱 홈에 다시 등록해 프로젝트마다 페이지가 두 개인지 확인한다.

    Returns:
        프로젝트별 결과 줄.

    Raises:
        RuntimeError: 페이지 수가 두 개가 아닌 프로젝트가 있다.
    """
    register(core, dest)
    rows, bad = [], []
    for name in PROJECTS:
        cards = core.get(f"/projects/{name}/pages")
        titles = ", ".join(f"{c['title']}({c['status']})" for c in cards)
        rows.append(f"| {name} | {len(cards)} | {titles} |")
        if len(cards) != 2:
            bad.append(name)
    unregister(core)
    if bad:
        raise RuntimeError(f"expected 2 pages in {bad}")
    return rows


def build(repo: Path, dest: Path, work: Path, env: dict[str, str]) -> None:
    """임시 앱 홈에서 두 종류 페이지를 만들고 등록을 해제한다."""
    here = Path(__file__).resolve().parent
    lay_out(repo, here, dest)
    core = start_core(repo, work / "home", env)
    try:
        register(core, dest)
        core.call("POST", "/projects/code/git/init")
        print("commit", commit(core, "Add receipt module")[:12], flush=True)
        rows = []
        for name in PROJECTS:
            detail = run_done_page(core, name)
            rows += run_rows(core, name, detail["id"])
            print(f"done page: {name}/{detail['id']}", flush=True)
        shutil.copy(here / "bug-test" / "test_discount.py", dest / "code")
        sha = commit(core, "Add a discount test", ["test_discount.py"])
        print("commit", sha[:12], flush=True)
        for name in PROJECTS:
            print(f"waiting page: {name}/{make_waiting_page(core, name)}")
        unregister(core)
    finally:
        core.stop()
    print("\n| 프로젝트 | 페이지 | run | 종류 | 러너/모델 | 결과 | 입력 추정 |")
    print("|---|---|---|---|---|---|---|")
    print("\n".join(rows))


def main() -> int:
    """데모를 만들고 새 앱 홈에서 확인한다. 성공하면 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    repo, dest, work = (p.resolve() for p in (args.repo, args.dest, args.work))
    if dest.exists():
        print(f"{dest} already exists; move it away first", file=sys.stderr)
        return 2
    env = {
        **os.environ,
        **demo_git_env(work),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        build(repo, dest, work, env)
        core = start_core(repo, work / "verify-home", env)
        try:
            rows = verify(core, dest)
        finally:
            core.stop()
    except (ApiError, RuntimeError, TimeoutError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print("\n| 프로젝트 | 페이지 수 | 페이지 |\n|---|---|---|")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
