import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


class OrderRepository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total_cents INTEGER NOT NULL CHECK (total_cents > 0),
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL
            )""")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def create(self, user_id: int, total_cents: int) -> dict:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self.connect() as db:
            row = db.execute(
                "INSERT INTO orders (user_id, total_cents, created_at) VALUES (?, ?, ?) RETURNING *",
                (user_id, total_cents, created_at),
            ).fetchone()
            return serialize(row)

    def list_all(self) -> list[dict]:
        with self.connect() as db:
            return [serialize(row) for row in db.execute("SELECT * FROM orders ORDER BY id")]

    def get(self, order_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return serialize(row) if row is not None else None


def serialize(row: sqlite3.Row) -> dict:
    order = dict(row)
    order["total"] = order.pop("total_cents") / 100
    return order
