"""게시: 문서 렌더러 하나로 정적 사이트를 만들어 폴더나 gh-pages에 싣는다.

게시 단위는 프로젝트 ``.madang/config.yaml``의 ``publish:``다::

    publish:
      include: [docs, README.md]   # 프로젝트 기준 경로. .madang/은 빠진다
      target: gh-pages             # 또는 folder:<경로>

사이트는 문서마다 HTML 껍데기에 md 원문과 렌더러 context를 싣고
브라우저에서 ``templates/_runtime``의 ``renderDocument``로 그린다. 문서가
쓰는 뷰어는 게시 시점 해시로 고정한 사본을 싣는다. 게시마다
``.madang/published/<n>.json``에 되감기 기록이 남는다.
"""

from madang.publish.deploy import PublishResult, publish, undo
from madang.publish.settings import (
    GH_PAGES,
    PublishError,
    Target,
    parse_target,
)
from madang.publish.site import SITE_DIR, SITE_MANIFEST, build, collect
from madang.publish.views import list_fences

__all__ = [
    "GH_PAGES",
    "SITE_DIR",
    "SITE_MANIFEST",
    "PublishError",
    "PublishResult",
    "Target",
    "build",
    "collect",
    "list_fences",
    "parse_target",
    "publish",
    "undo",
]
