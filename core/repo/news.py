"""Новости полка."""
import re
import unicodedata

from core.db import now, ro, tx

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(title: str) -> str:
    text = "".join(TRANSLIT.get(ch, ch) for ch in title.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or "post")[:60]


def unique_slug(title: str, exclude_id: int | None = None) -> str:
    base = slugify(title)
    with ro() as conn:
        n, slug = 1, base
        while True:
            row = conn.execute("SELECT id FROM news WHERE slug=?", (slug,)).fetchone()
            if not row or (exclude_id and row["id"] == exclude_id):
                return slug
            n += 1
            slug = f"{base}-{n}"


def create(title: str, summary: str, body: str, cover: str | None,
           published: bool, pinned: bool, author_id: int) -> int:
    slug = unique_slug(title)
    ts = now()
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO news (slug, title, summary, body, cover, published, pinned, author_id,"
            " created_at, updated_at, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (slug, title, summary, body, cover, int(published), int(pinned), author_id,
             ts, ts, ts if published else None),
        )
        return cur.lastrowid


def update(post_id: int, title: str, summary: str, body: str, cover: str | None,
           published: bool, pinned: bool) -> None:
    with tx() as conn:
        current = conn.execute("SELECT published, published_at FROM news WHERE id=?", (post_id,)).fetchone()
        published_at = current["published_at"] if current else None
        if published and not published_at:
            published_at = now()
        conn.execute(
            "UPDATE news SET title=?, summary=?, body=?, cover=?, published=?, pinned=?,"
            " updated_at=?, published_at=? WHERE id=?",
            (title, summary, body, cover, int(published), int(pinned), now(), published_at, post_id),
        )


def set_slug(post_id: int, slug: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE news SET slug=? WHERE id=?", (slug, post_id))


def get(post_id: int):
    with ro() as conn:
        return conn.execute(
            "SELECT n.*, a.display_name AS author_name FROM news n"
            " LEFT JOIN admins a ON a.id = n.author_id WHERE n.id=?",
            (post_id,),
        ).fetchone()


def by_slug(slug: str, published_only: bool = True):
    sql = ("SELECT n.*, a.display_name AS author_name FROM news n"
           " LEFT JOIN admins a ON a.id = n.author_id WHERE n.slug=?")
    if published_only:
        sql += " AND n.published=1"
    with ro() as conn:
        return conn.execute(sql, (slug,)).fetchone()


def published(limit: int = 30, offset: int = 0):
    with ro() as conn:
        return conn.execute(
            "SELECT n.*, a.display_name AS author_name FROM news n"
            " LEFT JOIN admins a ON a.id = n.author_id"
            " WHERE n.published=1"
            " ORDER BY n.pinned DESC, n.published_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def count_published() -> int:
    with ro() as conn:
        return conn.execute("SELECT COUNT(*) c FROM news WHERE published=1").fetchone()["c"]


def count_all() -> int:
    with ro() as conn:
        return conn.execute("SELECT COUNT(*) c FROM news").fetchone()["c"]


def listing_all(limit: int = 200):
    with ro() as conn:
        return conn.execute(
            "SELECT n.*, a.display_name AS author_name FROM news n"
            " LEFT JOIN admins a ON a.id = n.author_id"
            " ORDER BY n.pinned DESC, n.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def bump_views(post_id: int) -> None:
    with tx() as conn:
        conn.execute("UPDATE news SET views = views + 1 WHERE id=?", (post_id,))


def delete(post_id: int) -> str | None:
    with tx() as conn:
        row = conn.execute("SELECT cover FROM news WHERE id=?", (post_id,)).fetchone()
        conn.execute("DELETE FROM news WHERE id=?", (post_id,))
    return row["cover"] if row else None
