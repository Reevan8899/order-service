import os
from uuid import uuid4

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="Требуются запущенные сервисы")]
USERS = os.environ.get("USER_SERVICE_URL", "http://127.0.0.1:5001")
ORDERS = os.environ.get("ORDER_SERVICE_URL", "http://127.0.0.1:5002")


def test_full_order_flow_through_real_http():
    assert requests.get(f"{USERS}/health", timeout=3).json()["status"] == "ok"
    assert requests.get(f"{ORDERS}/health", timeout=3).json()["dependencies"]["user-service"] == "ok"
    user = requests.post(f"{USERS}/users", json={"email": f"{uuid4().hex}@example.com", "name": "Интеграция"}, timeout=5)
    assert user.status_code == 201
    order = requests.post(f"{ORDERS}/orders", json={"user_id": user.json()["id"], "total": 999.99}, timeout=10)
    assert order.status_code == 201
    assert order.json()["user_id"] == user.json()["id"] and order.json()["total"] == 999.99
    assert requests.get(f"{ORDERS}{order.headers['Location']}", timeout=3).json() == order.json()


def test_order_for_missing_user_returns_404_without_writing():
    original = requests.get(f"{ORDERS}/orders", timeout=3).json()
    result = requests.post(f"{ORDERS}/orders", json={"user_id": 2**63 - 1, "total": 100}, timeout=10)
    assert result.status_code == 404 and result.json()["code"] == "user_not_found"
    assert requests.get(f"{ORDERS}/orders", timeout=3).json() == original
