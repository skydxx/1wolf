"""Подключение к SQLite и схема. Одна база на оба приложения."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from core import config

SCHEMA = """
PRAGMA journal_mode = WAL;

-- ─────────── заявки в полк ───────────
CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',   -- new | review | accepted | rejected
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    real_name       TEXT,
    nick            TEXT NOT NULL,
    discord_nick    TEXT NOT NULL,
    discord_id      TEXT,
    age             TEXT,
    tz              TEXT,
    main_mode       TEXT,
    top_br          TEXT,
    hours           TEXT,
    playtime        TEXT,
    has_mic         INTEGER NOT NULL DEFAULT 0,
    joined_discord  INTEGER NOT NULL DEFAULT 0,
    prev_clans      TEXT,
    source          TEXT,
    about           TEXT,
    ip              TEXT,
    user_agent      TEXT,
    admin_note      TEXT,
    decided_by      INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    decided_at      TEXT,
    processed       INTEGER NOT NULL DEFAULT 0,    -- решение отработано в игре
    processed_by    INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    processed_at    TEXT,
    notified        INTEGER NOT NULL DEFAULT 0,
    discord_channel_id     TEXT,
    discord_log_message_id TEXT,
    discord_verified        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    stored_name     TEXT NOT NULL,
    original_name   TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    mime            TEXT,
    created_at      TEXT NOT NULL
);

-- ─────────── админы (создаются ТОЛЬКО владельцем) ───────────
CREATE TABLE IF NOT EXISTS admins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    role            TEXT NOT NULL DEFAULT 'admin', -- owner | lead | admin
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    created_by      INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    last_login_at   TEXT,
    must_change_pw  INTEGER NOT NULL DEFAULT 0
);

-- ─────────── passkey (WebAuthn) для админов ───────────
CREATE TABLE IF NOT EXISTS passkeys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    credential_id   TEXT NOT NULL UNIQUE,          -- base64url
    public_key      TEXT NOT NULL,                 -- base64url
    sign_count      INTEGER NOT NULL DEFAULT 0,
    transports      TEXT,
    label           TEXT,
    created_at      TEXT NOT NULL,
    last_used_at    TEXT
);

-- ─────────── пользователи сайта (обычная регистрация) ───────────
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email             TEXT UNIQUE COLLATE NOCASE,
    password_hash     TEXT NOT NULL,
    wt_nick           TEXT,
    discord_nick      TEXT,
    discord_id        TEXT,
    discord_username  TEXT,
    discord_avatar    TEXT,
    discord_linked_at TEXT,
    telegram_id       TEXT,
    telegram_username TEXT,
    telegram_linked_at TEXT,
    profile_completed INTEGER NOT NULL DEFAULT 1,
    intent            TEXT,                     -- clan | music — зачем регистрировался
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    last_login_at     TEXT,
    ip                TEXT
);

-- ─────────── одноразовые коды привязки Telegram ───────────
CREATE TABLE IF NOT EXISTS telegram_link_codes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0
);

-- ─────────── кэш состава/рейтинга с warthunder.com (обновляется краном) ───────────
CREATE TABLE IF NOT EXISTS wt_roster_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position        INTEGER NOT NULL,
    nick            TEXT NOT NULL,
    rating          INTEGER NOT NULL,
    activity        INTEGER NOT NULL,
    role            TEXT,
    joined          TEXT,
    fetched_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wt_roster_cache_nick ON wt_roster_cache(nick COLLATE NOCASE);

-- ─────────── промокоды VPN за сезон (топ полка) ───────────
CREATE TABLE IF NOT EXISTS season_promos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nick            TEXT NOT NULL,
    tier            TEXT NOT NULL,
    discount        INTEGER NOT NULL,
    code            TEXT NOT NULL,
    season_label    TEXT NOT NULL,
    issued_at       TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    notified_issued INTEGER NOT NULL DEFAULT 0,
    notified_expired INTEGER NOT NULL DEFAULT 0
);

-- ─────────── лог боёв (логируется вручную командой /logbattle в Discord) ───────────
CREATE TABLE IF NOT EXISTS battle_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opponent        TEXT NOT NULL,
    result          TEXT NOT NULL,             -- win | loss | draw
    mode            TEXT,                      -- realistic/simulator и т.п., свободный текст
    br              TEXT,
    mvp_nick        TEXT,
    note            TEXT,
    logged_by       TEXT NOT NULL,              -- discord ник того, кто залогировал
    discord_message_id TEXT,
    created_at      TEXT NOT NULL
);

-- ─────────── состав полка (ведётся вручную в админке) ───────────
CREATE TABLE IF NOT EXISTS members (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nick            TEXT NOT NULL,                 -- ник в War Thunder
    discord_nick    TEXT,
    title           TEXT,                          -- должность: командир, капитан, пилот
    branch          TEXT,                          -- авиация | танки | авиация и танки
    note            TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 100,  -- меньше — выше в списке
    active          INTEGER NOT NULL DEFAULT 1,    -- неактивный не показывается на сайте
    joined_at       TEXT,                          -- когда вступил, произвольный текст
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    added_by        INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- ─────────── новости ───────────
CREATE TABLE IF NOT EXISTS news (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    summary         TEXT,
    body            TEXT NOT NULL,                 -- лёгкий markdown-подобный текст
    cover           TEXT,                          -- stored_name картинки в uploads
    published       INTEGER NOT NULL DEFAULT 0,
    pinned          INTEGER NOT NULL DEFAULT 0,
    views           INTEGER NOT NULL DEFAULT 0,
    author_id       INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    published_at    TEXT
);

-- ─────────── рейт-лимиты ───────────
CREATE TABLE IF NOT EXISTS rate_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket          TEXT NOT NULL,                 -- имя лимита
    key             TEXT NOT NULL,                 -- ip / username / ...
    ts              INTEGER NOT NULL               -- unixtime
);

-- ─────────── аудит ───────────
CREATE TABLE IF NOT EXISTS audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    actor_kind      TEXT NOT NULL DEFAULT 'admin', -- admin | user | system
    actor_id        INTEGER,
    actor_name      TEXT,
    action          TEXT NOT NULL,
    target          TEXT,
    details         TEXT,
    ip              TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_status   ON applications(status);
CREATE INDEX IF NOT EXISTS idx_app_created  ON applications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_user     ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_att_app      ON attachments(application_id);
CREATE INDEX IF NOT EXISTS idx_pk_admin     ON passkeys(admin_id);
CREATE INDEX IF NOT EXISTS idx_news_pub     ON news(published, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_members_sort ON members(active, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_rate         ON rate_events(bucket, key, ts);
CREATE INDEX IF NOT EXISTS idx_audit_id     ON audit(id DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx():
    """Транзакция: коммит на выходе, откат на исключении, всегда close()."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def ro():
    """Только чтение — тот же close(), без коммита."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


MIGRATIONS = (
    ("applications", "discord_channel_id", "TEXT"),
    ("applications", "discord_log_message_id", "TEXT"),
    ("applications", "discord_verified", "INTEGER NOT NULL DEFAULT 0"),
    ("members", "user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
    ("users", "discord_id", "TEXT"),
    ("users", "discord_username", "TEXT"),
    ("users", "discord_avatar", "TEXT"),
    ("users", "discord_linked_at", "TEXT"),
    ("users", "telegram_id", "TEXT"),
    ("users", "telegram_username", "TEXT"),
    ("users", "telegram_linked_at", "TEXT"),
    ("users", "profile_completed", "INTEGER NOT NULL DEFAULT 1"),
    ("applications", "real_name", "TEXT"),
    ("users", "intent", "TEXT"),
)


def _migrate(conn) -> None:
    """Точечные ALTER TABLE для полей, добавленных после первого релиза —
    CREATE TABLE IF NOT EXISTS их не подхватывает на уже существующей базе."""
    for table, column, decl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_discord_id ON users(discord_id) WHERE discord_id IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id) WHERE telegram_id IS NOT NULL")


def init() -> None:
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with tx() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
