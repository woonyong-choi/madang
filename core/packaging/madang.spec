# PyInstaller 명세: core를 Python 없이 도는 onedir 번들 ``madang-core/``로 만든다.
#
# 실행 파일 이름은 ``madang``이다. 런타임 훅이 그 폴더를 PATH 앞에 두므로
# 에이전트가 Bash로 부르는 ``madang``도 같은 실행 파일이 된다.
# 빌드는 scripts/build-core.sh가 한다. 그 스크립트가 TIKTOKEN_CACHE_DIR에
# 토큰 인코딩을 미리 받아 두고 이 명세를 실행한다.
import os
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

core = Path(SPECPATH).parent
repo = core.parent
tiktoken_cache = Path(os.environ["TIKTOKEN_CACHE_DIR"])


def runtime_distributions(root):
    """root 배포판과 그 실행 의존성(선택 기능 제외) 이름을 모두 돌려준다."""
    seen, todo = set(), [root]
    while todo:
        name = todo.pop()
        try:
            requires = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            continue
        if name in seen:
            continue
        seen.add(name)
        for spec in requires:
            requirement = Requirement(spec)
            marker = requirement.marker
            if marker is None or marker.evaluate({"extra": ""}):
                todo.append(requirement.name)
    return sorted(seen)


hidden = [
    *collect_submodules("madang"),
    *collect_submodules("uvicorn"),
    *collect_submodules("langgraph"),
    *collect_submodules("langgraph.checkpoint.sqlite"),
    *collect_submodules("tiktoken_ext"),
    "sqlite3",
    "aiosqlite",
]

datas = [
    *collect_data_files("madang"),
    (str(core / "openapi.yaml"), "madang"),
    (str(tiktoken_cache), "tiktoken_cache"),
]
# 각 패키지의 라이선스 원문이 든 배포 메타데이터(*.dist-info)를 함께 싣는다.
for name in runtime_distributions("madang"):
    datas += copy_metadata(name)
# 템플릿은 렌더러·뷰어만 싣고 템플릿 테스트는 뺀다.
for path in sorted((repo / "templates").rglob("*")):
    relative = path.relative_to(repo)
    if path.is_file() and not {"_tests", "node_modules"} & set(relative.parts):
        datas.append((str(path), str(relative.parent)))

a = Analysis(
    [str(Path(SPECPATH) / "madang_main.py")],
    pathex=[str(core)],
    datas=datas,
    hiddenimports=hidden,
    runtime_hooks=[str(Path(SPECPATH) / "runtime_hook.py")],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="madang",
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="madang-core", upx=False)
