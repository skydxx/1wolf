"""Журнал действий: кто что сделал."""
from core.db import now, ro, tx


def log(actor_kind: str, actor_id: int | None, actor_name: str,
        action: str, target: str = "", details: str = "", ip: str = "") -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO audit (created_at, actor_kind, actor_id, actor_name, action, target, details, ip)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now(), actor_kind, actor_id, actor_name, action, target, details, ip),
        )


def listing(limit: int = 120):
    with ro() as conn:
        return conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
