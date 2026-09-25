"""Состав полка. Заполняется вручную в админке, показывается на сайте всем."""
from core.db import now, ro, tx

BRANCHES = ("Авиация", "Танки", "Авиация и танки")


def create(nick: str, discord_nick: str | None, title: str | None, branch: str | None,
           note: str | None, sort_order: int, joined_at: str | None,
           active: bool, added_by: int | None, user_id: int | None = None) -> int:
    ts = now()
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO members (nick, discord_nick, title, branch, note, sort_order,"
            " active, joined_at, created_at, updated_at, added_by, user_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (nick, discord_nick, title, branch, note, sort_order,
             1 if active else 0, joined_at, ts, ts, added_by, user_id),
        )
        return cur.lastrowid


def update(member_id: int, nick: str, discord_nick: str | None, title: str | None,
           branch: str | None, note: str | None, sort_order: int,
           joined_at: str | None, active: bool) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE members SET nick=?, discord_nick=?, title=?, branch=?, note=?,"
            " sort_order=?, active=?, joined_at=?, updated_at=? WHERE id=?",
            (nick, discord_nick, title, branch, note, sort_order,
             1 if active else 0, joined_at, now(), member_id),
        )


def get(member_id: int):
    with ro() as conn:
        return conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()


def by_nick(nick: str):
    with ro() as conn:
        return conn.execute("SELECT * FROM members WHERE nick=? COLLATE NOCASE", (nick,)).fetchone()


def by_user_id(user_id: int):
    with ro() as conn:
        return conn.execute("SELECT * FROM members WHERE user_id=?", (user_id,)).fetchone()


def public_list():
    """То, что видно на сайте: только активные, в заданном порядке."""
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM members WHERE active=1 ORDER BY sort_order, nick COLLATE NOCASE"
        ).fetchall()


def listing_all():
    with ro() as conn:
        return conn.execute(
            "SELECT m.*, a.display_name AS added_name FROM members m"
            " LEFT JOIN admins a ON a.id = m.added_by"
            " ORDER BY m.active DESC, m.sort_order, m.nick COLLATE NOCASE"
        ).fetchall()


def counts() -> dict:
    with ro() as conn:
        r = conn.execute(
            "SELECT COUNT(*) total,"
            " COALESCE(SUM(active=1),0) active,"
            " COALESCE(SUM(active=1 AND branch LIKE 'Авиация%'),0) air,"
            " COALESCE(SUM(active=1 AND branch LIKE '%анки%'),0) ground"
            " FROM members"
        ).fetchone()
    return {k: r[k] for k in ("total", "active", "air", "ground")}


def delete(member_id: int) -> None:
    with tx() as conn:
        conn.execute("DELETE FROM members WHERE id=?", (member_id,))


def sync_from_wt(wt_rows: list[dict]) -> None:
    """Состав тянется из warthunder.com (core/wt_clan.py), не руками:
    новых ников добавляет, ушедших (нет в свежем списке) — деактивирует
    (не удаляет: заметки/должность остаются на случай возвращения). Заметки/
    должность/направление уже существующих записей не трогает — только это
    и правится вручную в админке."""
    if not wt_rows:
        return  # пустой список — 404 у клана, не значит "все вышли"
    ts = now()
    incoming_nicks = {r["nick"].lower() for r in wt_rows}
    with tx() as conn:
        existing = {row["nick"].lower(): row["id"] for row in
                   conn.execute("SELECT id, nick FROM members").fetchall()}
        for r in wt_rows:
            key = r["nick"].lower()
            if key in existing:
                conn.execute("UPDATE members SET active=1, updated_at=? WHERE id=?",
                            (ts, existing[key]))
            else:
                conn.execute(
                    "INSERT INTO members (nick, sort_order, active, created_at, updated_at)"
                    " VALUES (?,?,1,?,?)",
                    (r["nick"], 100, ts, ts),
                )
        for nick_l, member_id in existing.items():
            if nick_l not in incoming_nicks:
                conn.execute("UPDATE members SET active=0, updated_at=? WHERE id=?",
                            (ts, member_id))
