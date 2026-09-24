"""뷰어: 등록부, 규격 검사, pinned 캐시, live 감시, 데이터 스키마 검사.

뷰어는 ``viewer.json``과 진입 HTML이 있는 폴더이며 원래 자리에 둔 채
등록부 ``~/.madang/viewers.yaml``에서 참조한다. 문서의 view 펜스는
``document_context()``로 해석해 렌더러에 넘긴다.
"""

from madang.viewers.embed import (
    STATUS_INVALID,
    ViewEntry,
    ViewRef,
    document_context,
    find_views,
    parse_view_info,
    resolve_view,
)
from madang.viewers.manifest import (
    MANIFEST_FILE,
    Manifest,
    ViewerError,
    load_manifest,
)
from madang.viewers.pinning import content_hash, source_pin
from madang.viewers.registry import (
    FOLLOW_LIVE,
    FOLLOW_PINNED,
    STATUS_BROKEN,
    STATUS_MISSING,
    STATUS_OK,
    Registration,
    Registry,
    Resolved,
    project_viewers,
)
from madang.viewers.schema import SchemaIssue, check
from madang.viewers.watch import ViewerWatcher

__all__ = [
    "FOLLOW_LIVE",
    "FOLLOW_PINNED",
    "MANIFEST_FILE",
    "STATUS_BROKEN",
    "STATUS_INVALID",
    "STATUS_MISSING",
    "STATUS_OK",
    "Manifest",
    "Registration",
    "Registry",
    "Resolved",
    "SchemaIssue",
    "ViewEntry",
    "ViewRef",
    "ViewerError",
    "ViewerWatcher",
    "check",
    "content_hash",
    "document_context",
    "find_views",
    "load_manifest",
    "parse_view_info",
    "project_viewers",
    "resolve_view",
    "source_pin",
]
