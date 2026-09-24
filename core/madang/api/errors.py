"""오류 응답: ``ApiError``와 ``ValidationFailure`` 형태로 돌려준다."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from madang.validate import Issue

NOT_FOUND = "not_found"
CONFLICT = "conflict"
INVALID = "invalid"
BUSY = "busy"
NO_REPO = "no_repo"

_CODES = {400: INVALID, 404: NOT_FOUND, 405: INVALID, 409: CONFLICT}


class HttpError(Exception):
    """``ApiError``로 돌려줄 실패.

    Attributes:
        status: HTTP 상태 코드.
        error: 기계가 읽는 사유.
        message: 사람이 읽는 설명.
    """

    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


class ValidationFailureError(Exception):
    """400 ``ValidationFailure``로 돌려줄 검사 실패.

    Attributes:
        message: 요약.
        issues: ``Issue`` 형태의 dict 목록.
    """

    def __init__(self, message: str, issues: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.message = message
        self.issues = issues


def not_found(message: str) -> HttpError:
    """404 ``not_found``를 반환한다."""
    return HttpError(404, NOT_FOUND, message)


def conflict(message: str, error: str = CONFLICT) -> HttpError:
    """409 실패를 반환한다. ``error``는 ``conflict``, ``busy``, ``no_repo``."""
    return HttpError(409, error, message)


def invalid(
    message: str, issues: Iterable[Issue] = ()
) -> ValidationFailureError:
    """검사 문제로 400 실패를 반환한다. 문제가 없으면 요약만 담는다."""
    found = [issue_dict(issue) for issue in issues]
    if not found:
        found = [{"code": "invalid-value", "message": message}]
    return ValidationFailureError(message, found)


def issue_dict(issue: Issue, base: Path | None = None) -> dict[str, Any]:
    """검사 문제를 응답 형태로 반환한다.

    Args:
        issue: 검사 문제.
        base: 주면 ``path``를 이 폴더 기준 상대 경로로 바꾼다.

    Returns:
        ``{code, message, line, path}``.
    """
    data = issue.to_dict()
    if issue.path is not None and base is not None:
        try:
            data["path"] = (
                issue.path.resolve().relative_to(base.resolve()).as_posix()
            )
        except ValueError:
            data["path"] = issue.path.name
    return data


def install(app: FastAPI) -> None:
    """오류 처리기를 앱에 붙인다."""
    app.add_exception_handler(HttpError, _api_exception)
    app.add_exception_handler(ValidationFailureError, _validation_failed)
    app.add_exception_handler(RequestValidationError, _request_invalid)
    app.add_exception_handler(HTTPException, _http_exception)


def _api_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HttpError)
    body = {"error": exc.error, "message": exc.message}
    return JSONResponse(body, status_code=exc.status)


def _validation_failed(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ValidationFailureError)
    body = {"error": INVALID, "message": exc.message, "issues": exc.issues}
    return JSONResponse(body, status_code=400)


def _request_invalid(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    issues = [
        {
            "code": "invalid-value",
            "message": f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}",
            "line": None,
            "path": None,
        }
        for err in exc.errors()
    ]
    body = {
        "error": INVALID,
        "message": "request failed validation",
        "issues": issues,
    }
    return JSONResponse(body, status_code=400)


def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    body = {
        "error": _CODES.get(exc.status_code, INVALID),
        "message": str(exc.detail),
    }
    return JSONResponse(body, status_code=exc.status_code)
