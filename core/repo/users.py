"""Пользователи сайта — обычная регистрация, без прав в админке."""
import secrets
from datetime import datetime, timedelta, timezone

from core.db import now, ro, tx

TELEGRAM_LINK_CODE_TTL = timedelta(minutes=10)


def by_username(username: str):
    with ro() as conn:
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def by_email(email: str):
    with ro() as conn:
        return conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def by_login(login: str):
    """Вход по нику или по e-mail — одним полем."""
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?", (login, login)
        ).fetchone()


def get(user_id: int):
    with ro() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def by_discord_id(discord_id: str):
    with ro() as conn:
        return conn.execute("SELECT * FROM users WHERE discord_id=?", (discord_id,)).fetchone()


def by_telegram_id(telegram_id: str):
    with ro() as conn:
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


def by_wt_nick(nick: str):
    """Юзер сам привязывает свой ник WT в /account — так матчим состав
    (синкается из warthunder.com) с аккаунтом без ручной привязки в админке."""
    with ro() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE wt_nick=? COLLATE NOCASE", (nick,)
        ).fetchone()


def create(username: str, email: str | None, password_hash: str, ip: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at, ip) VALUES (?,?,?,?,?)",
            (username, email, password_hash, now(), ip),
        )
        return cur.lastrowid


def create_from_discord(discord_id: str, discord_username: str, discord_avatar: str | None,
                        placeholder_username: str, placeholder_password_hash: str, ip: str) -> int:
    """Аккаунт создан через Discord OAuth, ещё без своего логина/пароля —
    завершается через complete_profile()."""
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, discord_id, discord_username, discord_avatar, "
            "discord_linked_at, profile_completed, created_at, ip) VALUES (?,?,?,?,?,?,0,?,?)",
            (placeholder_username, placeholder_password_hash, discord_id, discord_username,
             discord_avatar, now(), now(), ip),
        )
        return cur.lastrowid


def complete_profile(user_id: int, username: str, password_hash: str) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET username=?, password_hash=?, profile_completed=1 WHERE id=?",
            (username, password_hash, user_id),
        )


def set_intent(user_id: int, intent: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE users SET intent=? WHERE id=?", (intent, user_id))


def listing_with_telegram_by_intent(intent: str | None):
    """intent=None — все с привязанным Telegram (без фильтра)."""
    with ro() as conn:
        if intent:
            return conn.execute(
                "SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL AND active=1 AND intent=?",
                (intent,),
            ).fetchall()
        return conn.execute(
            "SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL AND active=1"
        ).fetchall()


def link_discord(user_id: int, discord_id: str, discord_username: str, discord_avatar: str | None) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET discord_id=?, discord_username=?, discord_avatar=?, discord_linked_at=? WHERE id=?",
            (discord_id, discord_username, discord_avatar, now(), user_id),
        )


def link_telegram(user_id: int, telegram_id: str, telegram_username: str | None) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET telegram_id=?, telegram_username=?, telegram_linked_at=? WHERE id=?",
            (telegram_id, telegram_username, now(), user_id),
        )


def unlink_telegram(user_id: int) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET telegram_id=NULL, telegram_username=NULL, telegram_linked_at=NULL WHERE id=?",
            (user_id,),
        )


def create_telegram_link_code(user_id: int) -> str:
    code = secrets.token_urlsafe(9)
    expires_at = (datetime.now(timezone.utc) + TELEGRAM_LINK_CODE_TTL).isoformat(timespec="seconds")
    with tx() as conn:
        conn.execute("DELETE FROM telegram_link_codes WHERE user_id=?", (user_id,))
        conn.execute(
            "INSERT INTO telegram_link_codes (user_id, code, created_at, expires_at) VALUES (?,?,?,?)",
            (user_id, code, now(), expires_at),
        )
    return code


def resolve_telegram_link_code(code: str) -> int | None:
    """Возвращает user_id и гасит код, если он живой и не использован."""
    with tx() as conn:
        row = conn.execute(
            "SELECT * FROM telegram_link_codes WHERE code=? AND used=0", (code,)
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        conn.execute("UPDATE telegram_link_codes SET used=1 WHERE id=?", (row["id"],))
        return row["user_id"]


def update_profile(user_id: int, wt_nick: str | None, discord_nick: str | None) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET wt_nick=?, discord_nick=? WHERE id=?",
            (wt_nick, discord_nick, user_id),
        )


def set_password(user_id: int, password_hash: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def touch_login(user_id: int) -> None:
    with tx() as conn:
        conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), user_id))


def set_active(user_id: int, active: bool) -> None:
    with tx() as conn:
        conn.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user_id))


def listing(q: str | None = None, limit: int = 200):
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM applications a WHERE a.user_id=u.id) AS apps"
           " FROM users u")
    args = []
    if q:
        sql += " WHERE u.username LIKE ? OR u.email LIKE ? OR u.wt_nick LIKE ?"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY u.id DESC LIMIT ?"
    args.append(limit)
    with ro() as conn:
        return conn.execute(sql, args).fetchall()


def listing_with_telegram():
    with ro() as conn:
        return conn.execute(
            "SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL AND active=1"
        ).fetchall()


def count() -> int:
    with ro() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
