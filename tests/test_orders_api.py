import pytest
import responses

from app.main import create_app
from app.user_client import UserClient

BASE_URL = "http://users.example.test"


@pytest.fixture
def client(tmp_path):
    return create_app(tmp_path / "orders.sqlite3", UserClient(BASE_URL, sleep=lambda seconds: None)).test_client()


@responses.activate
def test_order_lifecycle(client):
    responses.get(f"{BASE_URL}/health", json={"status": "ok"})
    responses.get(f"{BASE_URL}/users/1", json={"id": 1})
    assert client.get("/health").json["dependencies"] == {"user-service": "ok"}
    assert client.get("/orders").json == []
    result = client.post("/orders", json={"user_id": 1, "total": 1500.50})
    assert result.status_code == 201
    assert result.json["total"] == 1500.5 and result.json["user_id"] == 1
    assert result.json["status"] == "created" and result.json["created_at"].endswith("Z")
    assert client.get(result.headers["Location"]).json == result.json
    assert client.get("/orders").json == [result.json]


@pytest.mark.parametrize("payload", [[], {}, {"user_id": True, "total": 1}, {"user_id": 2**63, "total": 1},
                                     {"user_id": 1, "total": True}, {"user_id": 1, "total": "10"},
                                     {"user_id": 1, "total": -10}, {"user_id": 1, "total": 0.001},
                                     {"user_id": 1, "total": 10**12}, {"user_id": 1, "total": float("inf")}])
@responses.activate
def test_invalid_orders_are_rejected_before_http(client, payload):
    result = client.post("/orders", json=payload)
    assert result.status_code == 400 and result.json["code"] == "invalid_input"
    assert len(responses.calls) == 0
    assert client.get("/orders").json == []


@responses.activate
def test_nonexistent_user_has_no_order(client):
    responses.get(f"{BASE_URL}/users/99", status=404)
    assert client.post("/orders", json={"user_id": 99, "total": 10}).json["code"] == "user_not_found"
    assert len(responses.calls) == 1
    assert client.get("/orders").json == []


@responses.activate
def test_unavailable_dependency_preserves_read_api(client):
    responses.get(f"{BASE_URL}/users/1", status=503)
    responses.get(f"{BASE_URL}/health", status=503)
    result = client.post("/orders", json={"user_id": 1, "total": 10})
    assert result.status_code == 503 and result.json["code"] == "user_service_unavailable"
    assert client.get("/orders").json == []
    assert client.get("/health").json["dependencies"]["user-service"] == "unavailable"


@pytest.mark.parametrize("order_id", [12, 2**63])
def test_unknown_order(client, order_id):
    result = client.get(f"/orders/{order_id}")
    assert result.status_code == 404 and result.json["code"] == "order_not_found"


@responses.activate
def test_reopening_order_database_preserves_order(tmp_path):
    path = tmp_path / "orders.sqlite3"
    responses.get(f"{BASE_URL}/users/1", json={"id": 1})
    result = create_app(path, UserClient(BASE_URL)).test_client().post("/orders", json={"user_id": 1, "total": 99.99})
    assert create_app(path).test_client().get(result.headers["Location"]).json == result.json
