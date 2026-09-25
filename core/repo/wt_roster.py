"""Кэш состава/рейтинга полка с warthunder.com (см. core/wt_clan.py) и
промокоды, выданные по итогам сезона."""
from core.db import now, ro, tx


def save_snapshot(rows: list[dict]) -> None:
    """Полная замена кэша — таблица маленькая (макс. 128 строк), проще
    перезаписать, чем диффать построчно."""
    ts = now()
    with tx() as conn:
        conn.execute("DELETE FROM wt_roster_cache")
        conn.executemany(
            "INSERT INTO wt_roster_cache (position, nick, rating, activity, role, joined, fetched_at)"
            " VALUES (?,?,?,?,?,?,?)",
            [(r["position"], r["nick"], r["rating"], r["activity"], r.get("role"), r.get("joined"), ts)
             for r in rows],
        )


def get_snapshot() -> list:
    with ro() as conn:
        return conn.execute("SELECT * FROM wt_roster_cache ORDER BY position").fetchall()


def by_nick(nick: str):
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM wt_roster_cache WHERE nick=? COLLATE NOCASE", (nick,)
        ).fetchone()


def last_fetched_at() -> str | None:
    with ro() as conn:
        row = conn.execute("SELECT fetched_at FROM wt_roster_cache LIMIT 1").fetchone()
    return row["fetched_at"] if row else None


def create_season_promo(user_id: int, nick: str, tier: str, discount: int, code: str,
                        season_label: str, expires_at: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO season_promos (user_id, nick, tier, discount, code, season_label,"
            " issued_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, nick, tier, discount, code, season_label, now(), expires_at),
        )
        return cur.lastrowid


def season_promos_for(season_label: str):
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM season_promos WHERE season_label=? ORDER BY tier, nick COLLATE NOCASE",
            (season_label,),
        ).fetchall()


def unnotified_expired():
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM season_promos WHERE notified_expired=0 AND expires_at < datetime('now')"
        ).fetchall()


def mark_expired_notified(promo_id: int) -> None:
    with tx() as conn:
        conn.execute("UPDATE season_promos SET notified_expired=1 WHERE id=?", (promo_id,))
