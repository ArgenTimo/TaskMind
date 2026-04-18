from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
