"""요청·응답 모델. 이름과 필드는 ``openapi.yaml``의 components와 같다."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PageStatus = Literal["planning", "doing", "blocked", "review", "done"]
BlockType = Literal[
    "message", "doc", "data", "view", "code", "term", "site", "run"
]
MessageRole = Literal["user", "router", "agent"]
TargetMode = Literal["view", "edit"]
MemoryLayer = Literal["root", "project", "state"]
RunResultStatus = Literal[
    "planning", "doing", "blocked", "review", "done", "error", "cancelled"
]
TaskStatus = Literal["todo", "doing", "blocked", "review", "done"]
DecisionState = Literal["proposed", "confirmed", "superseded", "deferred"]
ProjectSort = Literal["updated", "created", "title"]
COLOR = r"^#[0-9a-fA-F]{6}$"


class _Body(BaseModel):
    """요청 본문. 모르는 키는 거부한다."""

    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    """응답. 저장된 파일의 추가 키는 그대로 보낸다."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# 오류


class ApiError(_Out):
    """오류 응답."""

    error: str
    message: str


class Issue(_Out):
    """검사 문제 하나."""

    code: str
    message: str
    line: int | None = None
    path: str | None = None


class ValidationFailure(_Out):
    """검사 실패 응답."""

    error: Literal["invalid"] = "invalid"
    message: str
    issues: list[Issue]


# 시스템과 설정


class Health(_Out):
    """core 상태."""

    status: Literal["ok"]
    version: str


class HomeStatus(_Out):
    """core가 쓰는 앱 홈(전역 설정 폴더)."""

    path: str
    initialized: bool


class HomeInit(_Body):
    """앱 홈 초기화 요청."""

    path: str


class RoutesDocument(_Body):
    """config.yaml의 routes 절 원문."""

    text: str


class RunnerStatus(_Out):
    """러너 하나의 사용 가능 여부."""

    name: str
    available: bool
    auth: Literal["subscription", "api"] | None = None
    reason: str | None = None


class RunnerAvailability(_Out):
    """러너 확인 결과."""

    checked: datetime
    runners: list[RunnerStatus]


# 프로젝트


class Project(_Out):
    """프로젝트: 페이지 기록을 ``.madang/``에 담는 로컬 폴더."""

    id: str
    title: str
    path: str
    parent: str | None = None
    icon: str | None = None
    color: str | None = None
    sort: ProjectSort | None = None
    pages: int | None = None
    active_pages: int | None = None


class ProjectCreate(_Body):
    """프로젝트 등록 요청."""

    path: str
    id: str | None = None
    title: str | None = None
    parent: str | None = None
    icon: str | None = None
    color: str | None = Field(default=None, pattern=COLOR)
    sort: ProjectSort | None = None


class ProjectUpdate(_Body):
    """프로젝트 수정 요청. 준 키만 바꾸며 null은 설정을 지운다."""

    title: str | None = None
    parent: str | None = None
    icon: str | None = None
    color: str | None = Field(default=None, pattern=COLOR)
    sort: ProjectSort | None = None


# 페이지


class RunRef(_Out):
    """카드에 보여 줄 마지막 실행."""

    n: int
    runner: str
    model: str
    result_status: RunResultStatus | None = None


class PageCard(_Out):
    """페이지 목록의 카드."""

    id: str
    project: str
    title: str
    kind: str | None = None
    status: PageStatus
    created: datetime | None = None
    updated: datetime | None = None
    pinned: bool
    tags: list[str]
    preview: str | None = None
    block_counts: dict[str, int]
    last_run: RunRef | None = None
    first_view: str | None = None


class PageCreate(_Body):
    """페이지 생성 요청."""

    title: str
    kind: str | None = None


class PageUpdate(_Body):
    """페이지 수정 요청."""

    title: str | None = None
    pinned: bool | None = None
    tags: list[str] | None = None
    blocks_order: list[str] | None = None
    project: str | None = None


# 블록


class Target(_Out):
    """메시지의 대상. 비어 있으면 페이지."""

    model_config = ConfigDict(extra="forbid")

    block: str | None = None
    elements: list[str] | None = None
    mode: TargetMode | None = None


class BlockHeader(_Out):
    """블록 머리부."""

    id: str
    type: BlockType
    file: str | None = None
    title: str | None = None
    created_by: str | None = None
    role: MessageRole | None = None
    ts: str | None = None
    run: int | None = None
    target: dict[str, Any] | None = None
    text: str | None = None
    format: Literal["json", "csv", "source"] | None = None
    schema_: str | None = Field(default=None, alias="schema")
    template: str | None = None
    bindings: dict[str, Any] | None = None
    presets: dict[str, Any] | None = None
    active_preset: str | None = None
    theme: dict[str, Any] | None = None
    path: str | None = None
    since_run: int | None = None
    cmd: str | None = None
    cwd: str | None = None
    proc: str | None = None
    url: str | None = None
    repo_bound: bool | None = None


class Block(_Out):
    """블록 머리부와 파일 내용."""

    header: BlockHeader
    content: str


class BlockContent(_Body):
    """블록 파일 전체."""

    content: str


class BlockHeaderPatch(_Body):
    """바꿀 머리부 키."""

    title: str | None = None
    bindings: dict[str, str] | None = None
    presets: dict[str, dict[str, str]] | None = None
    active_preset: str | None = None
    theme: dict[str, str] | None = None


class BlockCreate(_Body):
    """블록 생성 요청."""

    type: Literal["doc", "data", "view"]
    name: str
    content: str | None = None
    format: Literal["json", "csv"] | None = None
    template: str | None = None
    bindings: dict[str, str] | None = None
    data: list[str] | None = None
    title: str | None = None
    in_run: bool = False


# 메모리


class MemoryFile(_Out):
    """메모리 파일 하나."""

    layer: MemoryLayer
    path: str
    content: str
    tokens: int
    token_limit: int | None = None


class Memory(_Out):
    """세 층 메모리."""

    root: MemoryFile
    project: MemoryFile
    state: MemoryFile


class MemoryContent(_Body):
    """메모리 파일 전체."""

    content: str


# 메시지와 입력


class MessageCreate(_Body):
    """사용자 메시지."""

    text: str
    target: Target | None = None


class MessageAccepted(_Out):
    """저장한 메시지."""

    message: str


class InputParts(_Out):
    """입력 부분별 추정 토큰."""

    system_est: int
    root: int
    project: int
    state: int
    contract: int
    target: int
    request: int


class RunInput(_Out):
    """실행 입력 추정."""

    parts: InputParts
    total_est: int


class InputPreview(_Out):
    """다음 호출의 라우팅과 입력 추정."""

    kind: str
    tier: int
    runner: str
    model: str
    effort: str | None = None
    parts: InputParts
    total_est: int


# 실행


class RunTrigger(_Out):
    """실행을 일으킨 메시지와 대상."""

    message: str | None = None
    target: str | None = None
    elements: list[str] | None = None
    mode: TargetMode | None = None


class RunUsage(_Out):
    """토큰 수."""

    input: int
    cached: int
    output: int


class RunVerify(_Out):
    """검증 명령과 결과."""

    cmd: str | None = None
    ok: bool | None = None


class RunRecord(_Out):
    """runs/N.json."""

    n: int
    started: datetime | None = None
    finished: datetime | None = None
    trigger: RunTrigger | None = None
    kind: str | None = None
    tier: int | None = None
    runner: str | None = None
    model: str | None = None
    effort: str | None = None
    input: RunInput | None = None
    usage: RunUsage
    changed_files: list[str]
    unknown_files: list[str]
    verify: RunVerify
    result_status: RunResultStatus | None = None
    events_log: str | None = None


class RunStreamEvent(_Out):
    """도구에 중립인 러너 이벤트."""

    type: Literal[
        "text",
        "tool_call",
        "tool_result",
        "file_changed",
        "usage",
        "done",
        "error",
    ]
    text: str | None = None
    name: str | None = None
    summary: str | None = None
    path: str | None = None
    usage: RunUsage | None = None
    message: str | None = None


# 결정


class DecisionAnswer(_Body):
    """사람 결정의 답."""

    choice: str


class Task(_Out):
    """ledger.md 작업."""

    id: str
    title: str
    status: TaskStatus
    due: str | None = None


class TaskUpdate(_Body):
    """작업 추가·갱신."""

    id: str
    status: TaskStatus
    title: str | None = None
    due: str | None = None


class StateDecision(_Out):
    """ledger.md 결정."""

    id: str
    topic: str
    choice: str
    options: list[str]
    by: str | None = None
    run: int | None = None
    state: DecisionState
    supersedes: str | None = None


class DecisionCreate(_Body):
    """결정 기록 요청."""

    id: str
    topic: str
    choice: str
    options: list[str]
    supersedes: str | None = None
    state: DecisionState | None = None
    by: str | None = None
    in_run: bool = False


class ArtifactAdd(_Body):
    """산출물 등록 요청."""

    path: str


class RepoCommit(_Body):
    """프로젝트 저장소 커밋 요청."""

    message: str


class RepoCommitResult(_Out):
    """프로젝트 저장소 커밋 결과."""

    commit: str


class RepoPushResult(_Out):
    """프로젝트 저장소 push 결과."""

    branch: str
    remote: str | None = None


# 파일과 휴지통


class UnknownFile(_Out):
    """등록하지 않은 파일."""

    path: str
    run: int | None = None


class UnknownFileAction(_Body):
    """미등록 파일 처리."""

    action: Literal["artifact", "keep", "delete"]


class TrashEntry(_Out):
    """휴지통 항목 하나."""

    id: str
    deleted: str
    project: str
    page: str
    block: str | None = None
    paths: list[str]


class TrashRestore(_Out):
    """복원 결과."""

    id: str
    paths: list[str]


# 템플릿


class TemplateSlot(_Out):
    """템플릿 슬롯."""

    name: str
    schema_: str | None = Field(default=None, alias="schema")
    required: bool
    label: str | None = None


class TemplateEditable(_Out):
    """편집 허용 범위."""

    text: bool | None = None
    style: list[str] | None = None


class Template(_Out):
    """view 템플릿."""

    name: str
    version: int
    title: str
    slots: list[TemplateSlot]
    editable: TemplateEditable | None = None
    builtin: bool


class TemplateSchema(_Out):
    """템플릿 슬롯 스키마."""

    name: str
    version: int
    schema_: str = Field(alias="schema")


# 흐름


class Question(_Out):
    """사람에게 묻는 질문."""

    kind: Literal["choice", "yesno", "score"]
    prompt: str
    options: list[str] | None = None


class PendingDecision(_Out):
    """흐름이 기다리는 결정."""

    id: str
    run: int | None = None
    question: Question


class FlowWaitingData(_Out):
    """사람 결정 또는 흐름이 멈춘 이유."""

    decision: PendingDecision | None = None
    reason: str | None = None


class PageDetail(_Out):
    """page.md, 블록 머리부, 실행 기록."""

    id: str
    project: str
    title: str
    kind: str | None = None
    status: PageStatus
    created: datetime | None = None
    updated: datetime | None = None
    pinned: bool
    tags: list[str]
    overview: str | None = None
    blocks: list[BlockHeader]
    runs: list[RunRecord]
    unknown_files: list[UnknownFile]
    waiting: FlowWaitingData | None = None
