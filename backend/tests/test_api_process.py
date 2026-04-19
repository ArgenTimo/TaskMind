import json

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
