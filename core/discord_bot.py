"""Клиент внутреннего API бота kviyx-discord (заявки в =1W0LF=).

Бот живёт на том же сервере — обращаемся по 127.0.0.1, наружу этот API
не торчит. Всё лучшее-усилие: бот недоступен/упал → сайт не должен
падать вместе с ним, просто заявка идёт без Discord-канала.
"""
import base64
import logging

import requests

from core import config

log = logging.getLogger("discord_bot")

TIMEOUT = 6


def _headers() -> dict:
    return {"X-API-Key": config.DISCORD_BOT_API_KEY, "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> dict | None:
    if not (config.DISCORD_APPS_ENABLED and config.DISCORD_BOT_API_KEY):
        return None
    try:
        r = requests.post(f"{config.DISCORD_BOT_API_URL}{path}", json=payload,
                          headers=_headers(), timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("discord_bot: %s -> %s %s", path, r.status_code, r.text[:300])
            return None
        return r.json()
    except requests.RequestException as e:
        log.warning("discord_bot: %s недоступен (%s)", path, e)
        return None


def verify_member(discord_id: str | None, discord_nick: str | None) -> dict | None:
    """None — бот недоступен/выключен (не блокируем пользователя).
    {'found': False} — бот ответил, но в гильдии такого нет."""
    return _post("/applications/verify", {"discord_id": discord_id, "discord_nick": discord_nick})


def create_application_channel(app_row, files: list[dict]) -> dict | None:
    attachments = []
    for f in files[:5]:
        try:
            blob = (config.UPLOAD_DIR / f["stored_name"]).read_bytes()
            attachments.append({"name": f["original_name"], "data_b64": base64.b64encode(blob).decode()})
        except OSError:
            continue
    payload = {
        "application": {k: app_row[k] for k in app_row.keys()},
        "attachments": attachments,
    }
    return _post("/applications/create", payload)


def sync_decision(app_row, channel_id: int | None, log_message_id: int | None,
                  status: str, note: str | None) -> dict | None:
    payload = {
        "application": {k: app_row[k] for k in app_row.keys()},
        "channel_id": channel_id,
        "log_message_id": log_message_id,
        "status": status,
        "note": note,
    }
    return _post("/applications/decide", payload)
