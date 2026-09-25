"""Пароли, CSRF, рейт-лимиты, разбор клиентского IP, заголовки безопасности."""
import hmac
import ipaddress
import re
import secrets
import time
from functools import wraps

from flask import abort, current_app, g, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from core import config, db

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,32}$")

def clip(value: str | None, max_len: int) -> str | None:
    """Жёсткий обрез поля — защита от вставки огромного текста мимо клиентского maxlength."""
    if value is None:
        return None
    value = value.strip()
    return value[:max_len] if value else None
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


# ── пароли ──

def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method="pbkdf2:sha256:390000")


def verify_password(stored_hash: str, raw: str) -> bool:
    return check_password_hash(stored_hash, raw)


def password_problem(raw: str, minimum: int = 8) -> str | None:
    if len(raw) < minimum:
        return f"Пароль — минимум {minimum} символов."
    if raw.lower() in ("password", "12345678", "qwertyui", "11111111"):
        return "Такой пароль подберут за секунду."
    return None


# ── клиентский IP ──

def client_ip() -> str:
    # Only the local reverse proxy may tell us the original client address.
    # A caller can otherwise forge CF-Connecting-IP and evade rate limits.
    remote = request.remote_addr or ""
    candidate = remote
    if remote in ("127.0.0.1", "::1"):
        candidate = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or remote
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "0.0.0.0"


# ── CSRF ──

def csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


def csrf_protect(exempt_paths: tuple[str, ...] = ()) -> None:
    """Вешается в before_request: любой POST без валидного токена — 400."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.path in exempt_paths:
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    real = session.get("_csrf", "")
    if not real or not sent or not hmac.compare_digest(sent, real):
        current_app.logger.warning("csrf: отклонён %s %s ip=%s", request.method, request.path, client_ip())
        abort(400)


# ── рейт-лимиты ──

def rate_ok(bucket: str, key: str) -> bool:
    """Проверка без списания — когда попытка может не дойти до сохранения."""
    return rate_left(bucket, key) > 0


def rate_note(bucket: str, key: str) -> None:
    """Списание после успешного действия."""
    with db.tx() as conn:
        conn.execute("INSERT INTO rate_events (bucket, key, ts) VALUES (?,?,?)",
                     (bucket, key, int(time.time())))


def rate_hit(bucket: str, key: str) -> bool:
    """Регистрирует попытку. True — можно, False — лимит исчерпан."""
    limit, window = config.RATE_LIMITS.get(bucket, (30, 900))
    cutoff = int(time.time()) - window
    with db.tx() as conn:
        conn.execute("DELETE FROM rate_events WHERE ts < ?", (int(time.time()) - 7 * 86400,))
        used = conn.execute(
            "SELECT COUNT(*) c FROM rate_events WHERE bucket=? AND key=? AND ts>?",
            (bucket, key, cutoff),
        ).fetchone()["c"]
        if used >= limit:
            return False
        conn.execute(
            "INSERT INTO rate_events (bucket, key, ts) VALUES (?,?,?)",
            (bucket, key, int(time.time())),
        )
    return True


def rate_reset(bucket: str, key: str) -> None:
    """Успешный вход — обнуляем счётчик неудач."""
    with db.tx() as conn:
        conn.execute("DELETE FROM rate_events WHERE bucket=? AND key=?", (bucket, key))


def rate_left(bucket: str, key: str) -> int:
    limit, window = config.RATE_LIMITS.get(bucket, (30, 900))
    cutoff = int(time.time()) - window
    with db.ro() as conn:
        used = conn.execute(
            "SELECT COUNT(*) c FROM rate_events WHERE bucket=? AND key=? AND ts>?",
            (bucket, key, cutoff),
        ).fetchone()["c"]
    return max(0, limit - used)


def limited(bucket: str, key_func=None, message: str = "Слишком много попыток. Попробуй позже."):
    """Декоратор для POST-роутов. При исчерпании — 429 с текстом."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            key = key_func() if key_func else client_ip()
            if not rate_hit(bucket, key):
                g.rate_message = message
                abort(429)
            return fn(*a, **kw)
        return wrapper
    return deco


# ── заголовки ──

def apply_security_headers(resp, *, csp: str):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault("Content-Security-Policy", csp)
    resp.headers.pop("Server", None)
    if config.ENV == "prod":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp
