"""구현이 계약(openapi.yaml)과 의미상 같은지: 경로, 메서드, 스키마 필드."""

from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate
from typer.testing import CliRunner

from madang import cli
from madang.api.app import create_app, generated_openapi
from madang.api.contract import contract_path

METHODS = ("get", "post", "put", "patch", "delete")
# FastAPI가 요청 검사용으로 스스로 더하는 것. 우리는 400 ValidationFailure로
# 바꿔 돌려준다.
FASTAPI_ONLY = {"HTTPValidationError", "ValidationError"}


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict:
    app = create_app(tmp_path_factory.mktemp("home"))
    return generated_openapi(app)


def operations(doc: dict) -> set[tuple[str, str]]:
    return {
        (path, method)
        for path, item in doc["paths"].items()
        for method in item
        if method in METHODS
    }


def ref_name(schema: dict | None) -> str | None:
    if not schema:
        return None
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        inner = ref_name(schema.get("items"))
        return f"[{inner}]" if inner else "[]"
    return None


def json_schema(container: dict | None) -> dict | None:
    content = (container or {}).get("content", {})
    return content.get("application/json", {}).get("schema")


def test_contract_is_a_valid_openapi_document() -> None:
    validate(yaml.safe_load(contract_path().read_text()))


def test_openapi_command_prints_the_contract() -> None:
    result = CliRunner().invoke(cli.app, ["openapi"])
    assert result.exit_code == 0
    assert result.stdout == Path(contract_path()).read_text()


def test_server_serves_the_contract(client, contract) -> None:
    assert client.get("/openapi.json").json() == contract.doc


def test_paths_and_methods_match(generated, contract, tmp_path) -> None:
    implemented = operations(generated)
    app = create_app(tmp_path)
    for route in app.router.routes:
        for candidate in getattr(route, "original_router", app.router).routes:
            if type(candidate).__name__ == "APIWebSocketRoute":
                implemented.add((candidate.path, "get"))
    assert implemented == operations(contract.doc)


def test_operation_ids_match(generated, contract) -> None:
    for path, method in operations(generated):
        mine = generated["paths"][path][method]["operationId"]
        assert mine == contract.doc["paths"][path][method]["operationId"]


def test_request_and_response_schemas_match(generated, contract) -> None:
    for path, method in operations(generated):
        mine = generated["paths"][path][method]
        theirs = contract.doc["paths"][path][method]
        assert ref_name(json_schema(mine.get("requestBody"))) == ref_name(
            json_schema(theirs.get("requestBody"))
        ), f"{method} {path} request body"
        success = [c for c in mine["responses"] if c.startswith("2")]
        assert len(success) == 1, f"{method} {path}"
        code = success[0]
        assert code in theirs["responses"], f"{method} {path} status {code}"
        assert ref_name(json_schema(mine["responses"][code])) == ref_name(
            json_schema(theirs["responses"][code])
        ), f"{method} {path} response"


def test_component_fields_match(generated, contract) -> None:
    ours = {
        name: schema
        for name, schema in generated["components"]["schemas"].items()
        if name not in FASTAPI_ONLY and "properties" in schema
    }
    theirs = contract.doc["components"]["schemas"]
    assert ours, "no models were generated"
    for name, schema in ours.items():
        assert name in theirs, f"{name} is not in the contract"
        assert set(schema["properties"]) == set(
            theirs[name].get("properties", {})
        ), name
        assert set(schema.get("required", [])) == set(
            theirs[name].get("required", [])
        ), name
