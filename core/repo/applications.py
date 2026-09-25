"""Заявки в полк и вложения."""
from core.db import now, ro, tx

FIELDS = (
    "user_id real_name nick discord_nick discord_id age tz main_mode top_br hours playtime "
    "has_mic joined_discord prev_clans source about ip user_agent"
).split()


def create(data: dict, files: list[dict]) -> int:
    cols = ["created_at", "status"] + FIELDS
    values = [now(), "new"] + [data.get(c) for c in FIELDS]
    with tx() as conn:
        cur = conn.execute(
            f"INSERT INTO applications ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            values,
        )
        app_id = cur.lastrowid
        for f in files:
            conn.execute(
                "INSERT INTO attachments (application_id, stored_name, original_name, size_bytes, mime, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (app_id, f["stored_name"], f["original_name"], f["size_bytes"], f.get("mime"), now()),
            )
    return app_id


def get(app_id: int):
    with ro() as conn:
        row = conn.execute(
            "SELECT a.*, d.display_name AS decided_name, p.display_name AS processed_name,"
            " u.username AS user_login"
            " FROM applications a"
            " LEFT JOIN admins d ON d.id = a.decided_by"
            " LEFT JOIN admins p ON p.id = a.processed_by"
            " LEFT JOIN users  u ON u.id = a.user_id"
            " WHERE a.id = ?",
            (app_id,),
        ).fetchone()
        if not row:
            return None, []
        files = conn.execute(
            "SELECT * FROM attachments WHERE application_id=? ORDER BY id", (app_id,)
        ).fetchall()
    return row, files


def listing(status: str | None = None, q: str | None = None, limit: int = 300):
    sql = ("SELECT a.*, (SELECT COUNT(*) FROM attachments t WHERE t.application_id=a.id) AS files_count"
           " FROM applications a")
    where, args = [], []
    if status and status != "all":
        where.append("a.status = ?")
        args.append(status)
    if q:
        where.append("(a.nick LIKE ? OR a.discord_nick LIKE ? OR a.discord_id LIKE ?)")
        args += [f"%{q}%"] * 3
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.created_at DESC LIMIT ?"
    args.append(limit)
    with ro() as conn:
        return conn.execute(sql, args).fetchall()


def by_user(user_id: int):
    with ro() as conn:
        return conn.execute(
            "SELECT id, created_at, status, nick, discord_nick, processed"
            " FROM applications WHERE user_id=? ORDER BY id DESC",
            (user_id,),
        ).fetchall()


def counts_by_status() -> dict:
    with ro() as conn:
        rows = conn.execute("SELECT status, COUNT(*) c FROM applications GROUP BY status").fetchall()
    d = {r["status"]: r["c"] for r in rows}
    d.setdefault("new", 0)
    d["all"] = sum(v for k, v in d.items() if k != "all")
    return d


def set_status(app_id: int, status: str, admin_id: int | None, note: str | None) -> None:
    """Смена решения сбрасывает отметку «выполнено»: новое решение надо отработать заново."""
    with tx() as conn:
        current = conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
        changed = current is None or current["status"] != status
        if changed:
            conn.execute(
                "UPDATE applications SET status=?, admin_note=?, decided_by=?, decided_at=?,"
                " processed=0, processed_by=NULL, processed_at=NULL WHERE id=?",
                (status, note, admin_id, now(), app_id),
            )
        else:
            conn.execute(
                "UPDATE applications SET admin_note=?, decided_by=?, decided_at=? WHERE id=?",
                (note, admin_id, now(), app_id),
            )


def set_processed(app_id: int, processed: bool, admin_id: int | None) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE applications SET processed=?, processed_by=?, processed_at=? WHERE id=?",
            (1 if processed else 0, admin_id if processed else None, now() if processed else None, app_id),
        )


def decided(status: str = "all", processed: str = "all", q: str | None = None):
    """Реестр решённых заявок — для владельца и капитана."""
    sql = (
        "SELECT a.id, a.created_at, a.status, a.nick, a.discord_nick, a.discord_id,"
        " a.decided_at, a.processed, a.processed_at, a.admin_note,"
        " d.display_name AS decided_name, p.display_name AS processed_name"
        " FROM applications a"
        " LEFT JOIN admins d ON d.id = a.decided_by"
        " LEFT JOIN admins p ON p.id = a.processed_by"
        " WHERE a.status IN ('accepted','rejected')"
    )
    args = []
    if status in ("accepted", "rejected"):
        sql += " AND a.status = ?"
        args.append(status)
    if processed == "yes":
        sql += " AND a.processed = 1"
    elif processed == "no":
        sql += " AND a.processed = 0"
    if q:
        sql += " AND (a.nick LIKE ? OR a.discord_nick LIKE ?)"
        args += [f"%{q}%"] * 2
    sql += " ORDER BY a.processed ASC, a.decided_at DESC"
    with ro() as conn:
        return conn.execute(sql, args).fetchall()


def roster_counts() -> dict:
    with ro() as conn:
        r = conn.execute(
            "SELECT COALESCE(SUM(status='accepted'),0) accepted,"
            " COALESCE(SUM(status='rejected'),0) rejected,"
            " COALESCE(SUM(status IN ('accepted','rejected') AND processed=0),0) pending,"
            " COALESCE(SUM(status IN ('accepted','rejected') AND processed=1),0) done"
            " FROM applications"
        ).fetchone()
    return {k: r[k] for k in ("accepted", "rejected", "pending", "done")}


def delete(app_id: int) -> list[str]:
    with tx() as conn:
        names = [r["stored_name"] for r in conn.execute(
            "SELECT stored_name FROM attachments WHERE application_id=?", (app_id,))]
        conn.execute("DELETE FROM attachments WHERE application_id=?", (app_id,))
        conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
    return names


def mark_notified(app_id: int) -> None:
    with tx() as conn:
        conn.execute("UPDATE applications SET notified=1 WHERE id=?", (app_id,))


def set_discord_channel(app_id: int, channel_id, log_message_id, verified: bool) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE applications SET discord_channel_id=?, discord_log_message_id=?, discord_verified=? WHERE id=?",
            (str(channel_id) if channel_id else None,
             str(log_message_id) if log_message_id else None,
             1 if verified else 0, app_id),
        )


def recent_rejection(nick: str, hours: int = 24):
    """Последний отказ по этому нику за N часов — None, если можно подавать заново."""
    with ro() as conn:
        return conn.execute(
            "SELECT id, decided_at FROM applications"
            " WHERE nick = ? COLLATE NOCASE AND status = 'rejected'"
            " AND datetime(decided_at) > datetime('now', ?)"
            " ORDER BY decided_at DESC LIMIT 1",
            (nick, f"-{hours} hours"),
        ).fetchone()


def attachment(app_id: int, stored_name: str):
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM attachments WHERE application_id=? AND stored_name=?",
            (app_id, stored_name),
        ).fetchone()
