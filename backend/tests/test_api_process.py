import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def llm_stub_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "stub")


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runtime_config() -> None:
    response = client.get("/runtime_config")
    assert response.status_code == 200
    data = response.json()
    assert "default_llm_mode" in data
    assert "default_prompt_version" in data
    assert "default_model" in data
    assert "default_base_url" in data
    assert "available_prompt_versions" in data
    assert isinstance(data["available_prompt_versions"], list)
    assert "real_mode_supported" in data
    assert "json_object_request_enabled" in data


def test_process_runtime_override_stub_bypasses_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request-scoped stub mode must not require OPENAI_API_KEY even if LLM_MODE=real in env."""
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/process",
        json={
            "text": "hello",
            "mode": "analyze",
            "runtime": {"llm_mode": "stub"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"].startswith("[analyze]")


def test_process_valid() -> None:
    response = client.post(
        "/process",
        json={"text": "hello world", "mode": "analyze"},
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"summary", "intent", "reply", "tasks"}
    assert isinstance(data["tasks"], list)


def test_process_invalid_mode() -> None:
    response = client.post(
        "/process",
        json={"text": "hello", "mode": "full"},
    )
    assert response.status_code == 422


def test_process_real_mode_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "analyze"},
    )
    assert response.status_code == 503
    body = response.json()
    assert "detail" in body
    assert "OPENAI_API_KEY" in body["detail"]


def test_process_real_mode_whitespace_only_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "   \t  ")

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "analyze"},
    )
    assert response.status_code == 503
    body = response.json()
    assert "OPENAI_API_KEY" in body["detail"]


def test_process_real_mode_unknown_prompt_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("PROMPT_VERSION", "v999")

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "analyze"},
    )
    assert response.status_code == 503
    body = response.json()
    assert "PROMPT_VERSION" in body["detail"]
    assert "prompt file" in body["detail"].lower()


def test_process_real_mode_accepts_sk_prefixed_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real provider keys often start with sk-; must not be rejected as placeholders."""
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "sk-proj-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"S","intent":"I","reply":"R","tasks":["t"]}'
                            ),
                        },
                    },
                ],
            }

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.httpx.Client", FakeClient)

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "analyze"},
    )
    assert response.status_code == 200


def test_process_real_mode_success_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"S","intent":"I","reply":"R","tasks":["one","two"]}'
                            ),
                        },
                    },
                ],
            }

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.httpx.Client", FakeClient)

    response = client.post(
        "/process",
        json={"text": "hello world", "mode": "analyze"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "summary": "S",
        "intent": "I",
        "reply": "R",
        "tasks": ["one", "two"],
    }


def test_process_real_mode_guardrails_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    long_summary = "s" * 500

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            payload = {
                "summary": f"  {long_summary}  ",
                "intent": "   \t  ",
                "reply": " trimmed ",
                "tasks": ["", "  task one  ", " ", "\t"],
            }
            content = json.dumps(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": content,
                        },
                    },
                ],
            }

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.httpx.Client", FakeClient)

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "analyze"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == long_summary[:400]
    assert data["intent"] == "unknown"
    assert data["reply"] == "trimmed"
    assert data["tasks"] == ["task one"]


def test_process_real_mode_reply_mode_empty_reply_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"S","intent":"I","reply":"   \\n  ","tasks":["t"]}'
                            ),
                        },
                    },
                ],
            }

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.httpx.Client", FakeClient)

    response = client.post(
        "/process",
        json={"text": "hello", "mode": "reply"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "No reply text was produced."


def test_process_batch_all_success() -> None:
    response = client.post(
        "/process_batch",
        json={
            "items": [
                {"text": "hello", "mode": "analyze"},
                {"text": "world", "mode": "reply"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["success"] is True
    assert data["items"][1]["success"] is True
    assert "summary" in data["items"][0]["result"]


def test_process_batch_mixed_validation_and_success() -> None:
    response = client.post(
        "/process_batch",
        json={
            "items": [
                {"text": "ok", "mode": "analyze"},
                {"text": "   ", "mode": "analyze"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["success"] is True
    assert data["items"][1]["success"] is False
    assert data["items"][1]["error"]["status_code"] == 422


def test_process_batch_mixed_process_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/process_batch",
        json={
            "items": [
                {"text": "ok", "mode": "analyze"},
                {"text": "also ok", "mode": "analyze"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["success"] is False
    assert data["items"][0]["error"]["status_code"] == 503
    assert data["items"][1]["success"] is False
    assert data["items"][1]["error"]["status_code"] == 503


def test_process_batch_invalid_empty_items() -> None:
    response = client.post("/process_batch", json={"items": []})
    assert response.status_code == 422


def test_process_batch_invalid_top_level() -> None:
    response = client.post("/process_batch", json={})
    assert response.status_code == 422


def test_models_list_stub_mode() -> None:
    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == []
    assert data["source"] == "stub_mode"
    assert data["detail"]
    assert "base_url" in data


def test_models_list_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == []
    assert data["source"] == "no_api_key"
    assert data["detail"]
    assert data["base_url"].startswith("http")


@patch("httpx.Client")
def test_models_list_live_ok(mock_client_class: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_cm = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_cm
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "gpt-4o-mini", "object": "model"},
            {"id": "gpt-4o", "object": "model"},
        ],
    }
    mock_cm.get.return_value = mock_resp

    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "live"
    assert data["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert data["detail"] is None
    mock_cm.get.assert_called_once()
    call_kw = mock_cm.get.call_args
    assert "/models" in str(call_kw)


@patch("httpx.Client")
def test_models_list_provider_http_error(
    mock_client_class: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_cm = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_cm
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"
    mock_cm.get.return_value = mock_resp

    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == []
    assert data["source"] == "provider_error"
    assert "401" in (data["detail"] or "")
