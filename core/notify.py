"""Уведомления о новых заявках в Discord.

ЗАГОТОВКА: по умолчанию выключено (DISCORD_NOTIFY_ENABLED=false) — вызовы
превращаются в no-op с записью в лог. Включается одной строчкой в .env,
код трогать не надо.

Два режима:
  webhook — POST на Webhook URL канала. Бот не нужен, поднимается за минуту:
            Discord → канал → Настройки → Интеграции → Вебхуки → Новый вебхук.
  bot     — POST через Bot API в DISCORD_ADMIN_CHANNEL_ID. Нужен бот в гильдии
            с правами View Channel + Send Messages. Пригодится, когда захочется
            кнопок «Принять/Отклонить» прямо в дискорде (interactions) —
            вебхук так не умеет, бот умеет.

Отправка синхронная, но в отдельном потоке — чтобы отвалившийся discord
не подвешивал отправку формы пользователю.
"""
import logging
import threading

import requests

from core import config

log = logging.getLogger("notify")

API_BASE = "https://discord.com/api/v10"
STATUS_COLORS = {"new": 0x5EB1FF, "review": 0xFFB864, "accepted": 0x10B981, "rejected": 0xEF4444}


def _embed(app_row, files_count: int, admin_url: str) -> dict:
    def f(name, value, inline=True):
        return {"name": name, "value": (str(value) if value else "—")[:1024], "inline": inline}

    return {
        "title": f"Новая заявка #{app_row['id']} — {app_row['nick']}",
        "url": admin_url,
        "color": STATUS_COLORS["new"],
        "fields": [
            f("Ник в игре", app_row["nick"]),
            f("Discord", app_row["discord_nick"]),
            f("Возраст", app_row["age"]),
            f("Направление", app_row["main_mode"]),
            f("Топ-техника / БР", app_row["top_br"]),
            f("Наиграно", app_row["hours"]),
            f("Микрофон", "да" if app_row["has_mic"] else "нет"),
            f("Вступил в дискорд", "да" if app_row["joined_discord"] else "нет"),
            f("Онлайн", app_row["playtime"]),
            f("Откуда узнал", app_row["source"]),
            f("Вложений", files_count),
            f("О себе", (app_row["about"] or "")[:900], False),
        ],
        "footer": {"text": f"{config.CLAN_TAG_DISPLAY} · 1wolf.ru"},
        "timestamp": app_row["created_at"],
    }


def _payload(app_row, files_count: int, admin_url: str) -> dict:
    content = ""
    if config.DISCORD_PING_ROLE_ID:
        content = f"<@&{config.DISCORD_PING_ROLE_ID}>"
    return {
        "content": content,
        "embeds": [_embed(app_row, files_count, admin_url)],
        "allowed_mentions": {"roles": [config.DISCORD_PING_ROLE_ID] if config.DISCORD_PING_ROLE_ID else []},
    }


def _send(payload: dict) -> bool:
    mode = config.DISCORD_NOTIFY_MODE
    try:
        if mode == "webhook":
            if not config.DISCORD_WEBHOOK_URL:
                log.warning("notify: webhook-режим, но DISCORD_WEBHOOK_URL пуст")
                return False
            r = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        elif mode == "bot":
            if not (config.DISCORD_BOT_TOKEN and config.DISCORD_ADMIN_CHANNEL_ID):
                log.warning("notify: bot-режим, но нет токена или channel_id")
                return False
            r = requests.post(
                f"{API_BASE}/channels/{config.DISCORD_ADMIN_CHANNEL_ID}/messages",
                json=payload,
                headers={"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"},
                timeout=10,
            )
        else:
            log.error("notify: неизвестный режим %r", mode)
            return False
        if r.status_code >= 300:
            log.error("notify: discord ответил %s: %s", r.status_code, r.text[:400])
            return False
        return True
    except Exception as e:  # noqa: BLE001 — уведомление не должно ронять заявку
        log.error("notify: не отправилось: %s", e)
        return False


def new_application(app_row, files_count: int, admin_url: str, on_success=None) -> None:
    """Дёргается из app.py после сохранения заявки. Не бросает исключений."""
    if not config.DISCORD_NOTIFY_ENABLED:
        log.info("notify: выключено, заявка #%s не отправлена в discord", app_row["id"])
        return

    payload = _payload(app_row, files_count, admin_url)

    def worker():
        if _send(payload) and on_success:
            try:
                on_success()
            except Exception as e:  # noqa: BLE001
                log.error("notify: on_success упал: %s", e)

    threading.Thread(target=worker, daemon=True).start()
