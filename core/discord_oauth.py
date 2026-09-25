"""Discord OAuth2 (Authorization Code) для входа на сайт.

Скоуп только identify — членство в гильдии проверяем не через OAuth
guilds-скоуп (требует лишнего согласия юзера и пагинации), а через
уже существующий внутренний API бота (core.discord_bot.verify_member),
который смотрит гильдию напрямую от лица бота.
"""
import logging

import requests

from core import config

log = logging.getLogger("discord_oauth")

AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"
TIMEOUT = 8


def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": config.DISCORD_OAUTH_CLIENT_ID,
        "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class OAuthError(Exception):
    pass


def exchange_code(code: str) -> dict:
    """code -> {'id','username','avatar', ...} профиль Discord-юзера."""
    try:
        token_resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": config.DISCORD_OAUTH_CLIENT_ID,
                "client_secret": config.DISCORD_OAUTH_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise OAuthError(f"Discord недоступен: {e}") from e

    if token_resp.status_code != 200:
        log.warning("discord_oauth: token exchange %s %s", token_resp.status_code, token_resp.text[:300])
        raise OAuthError("Не удалось подтвердить вход через Discord.")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise OAuthError("Discord не вернул токен доступа.")

    try:
        user_resp = requests.get(
            USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise OAuthError(f"Discord недоступен: {e}") from e

    if user_resp.status_code != 200:
        log.warning("discord_oauth: user fetch %s %s", user_resp.status_code, user_resp.text[:300])
        raise OAuthError("Не удалось получить профиль Discord.")

    return user_resp.json()


def avatar_url(discord_id: str, avatar_hash: str | None) -> str | None:
    if not avatar_hash:
        return None
    ext = "gif" if avatar_hash.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.{ext}?size=128"
