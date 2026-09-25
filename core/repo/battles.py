"""Лог боёв — заполняется вручную командой /logbattle в Discord
(нет автоматического источника результатов боёв, см. decisions.md)."""
from core.db import now, ro, tx


def create(opponent: str, result: str, mode: str | None, br: str | None,
          mvp_nick: str | None, note: str | None, logged_by: str,
          discord_message_id: str | None = None) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO battle_logs (opponent, result, mode, br, mvp_nick, note,"
            " logged_by, discord_message_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (opponent, result, mode, br, mvp_nick, note, logged_by, discord_message_id, now()),
        )
        return cur.lastrowid


def listing(limit: int = 100):
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM battle_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def counts() -> dict:
    with ro() as conn:
        r = conn.execute(
            "SELECT COUNT(*) total, COALESCE(SUM(result='win'),0) wins,"
            " COALESCE(SUM(result='loss'),0) losses FROM battle_logs"
        ).fetchone()
    return {k: r[k] for k in ("total", "wins", "losses")}
