"""동봉 core가 시작할 때 번들 안의 자원을 가리키게 한다.

- ``TIKTOKEN_CACHE_DIR``: 빌드 때 받아 둔 토큰 인코딩. 오프라인에서도 센다.
- ``MADANG_TEMPLATES``: 게시 렌더러와 내장 뷰어가 든 템플릿 폴더.
- ``PATH``: 에이전트가 Bash로 부르는 ``madang``이 이 실행 파일이 되도록
  실행 파일 폴더를 앞에 둔다.

이미 설정된 값은 덮어쓰지 않는다(``PATH``는 앞에 더하기만 한다).
"""

import os
import sys

_bundle = getattr(sys, "_MEIPASS", "")
if _bundle:
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR", os.path.join(_bundle, "tiktoken_cache")
    )
    os.environ.setdefault(
        "MADANG_TEMPLATES", os.path.join(_bundle, "templates")
    )
    _bin_dir = os.path.dirname(sys.executable)
    os.environ["PATH"] = os.pathsep.join([_bin_dir, os.environ.get("PATH", "")])
