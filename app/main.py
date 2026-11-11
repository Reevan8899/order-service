import os
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, request
from waitress import serve

from app.storage import OrderRepository
from app.user_client import UserClient, UserNotFound, UserServiceUnavailable

MAX_ID = 2**63 - 1
MAX_TOTAL = Decimal("999999999.99")


def order_fields(data: object) -> tuple[int, int]:
    if not isinstance(data, dict):
        raise ValueError("Передайте JSON-объект с полями user_id и total.")
    user_id, total = data.get("user_id"), data.get("total")
    if type(user_id) is not int or not 1 <= user_id <= MAX_ID:
        raise ValueError("user_id должен быть положительным целым числом.")
    if type(total) not in (int, float):
        raise ValueError("total должен быть числом.")
    amount = Decimal(str(total))
    if not amount.is_finite() or not 0 < amount <= MAX_TOTAL:
        raise ValueError("total должен быть положительным и не больше 999999999.99.")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError("Укажите total с точностью до копеек.")
    return user_id, int(cents)


def create_app(database: str | Path | None = None, user_client: UserClient | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    repository = OrderRepository(Path(database or os.environ.get("ORDER_DB_PATH", "data/orders.sqlite3")))
    users = user_client if user_client is not None else UserClient(os.environ.get("USER_SERVICE_URL", "http://127.0.0.1:5001"))

    @app.get("/health")
    def health():
        return jsonify(
            status="ok", service="order-service",
            dependencies={"user-service": "ok" if users.health() else "unavailable"},
            circuit_breaker=users.breaker.state,
        )

    @app.post("/orders")
    def create_order():
        try:
            user_id, total_cents = order_fields(request.get_json(silent=True))
        except ValueError as error:
            return jsonify(error=str(error), code="invalid_input"), 400
        try:
            users.get_user(user_id)
        except UserNotFound:
            return jsonify(error=f"Пользователь {user_id} не найден.", code="user_not_found"), 404
        except UserServiceUnavailable as error:
            return jsonify(error=str(error), code=error.code), 503
        order = repository.create(user_id, total_cents)
        return jsonify(order), 201, {"Location": f"/orders/{order['id']}"}

    @app.get("/orders")
    def list_orders():
        return jsonify(repository.list_all())

    @app.get("/orders/<int:order_id>")
    def get_order(order_id):
        order = repository.get(order_id) if order_id <= MAX_ID else None
        if order is None:
            return jsonify(error=f"Заказ {order_id} не найден.", code="order_not_found"), 404
        return jsonify(order)

    return app


if __name__ == "__main__":
    serve(create_app(), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5002")))
