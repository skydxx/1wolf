"""Configuration for the public 1wolf site. Put private values in .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _b(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


def _i(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


ENV = os.getenv("ENV", "dev")
DEBUG = _b("DEBUG", "true" if ENV == "dev" else "false")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
PUBLIC_SECRET_KEY = os.getenv("PUBLIC_SECRET_KEY", "dev-public-insecure")
if ENV == "prod" and (len(PUBLIC_SECRET_KEY) < 32 or PUBLIC_SECRET_KEY == "dev-public-insecure"):
    raise RuntimeError("Production requires PUBLIC_SECRET_KEY of at least 32 characters")
PUBLIC_COOKIE = "wolf_s"
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "127.0.0.1")
PUBLIC_PORT = _i("PUBLIC_PORT", 5055)
SITE_URL = os.getenv("SITE_URL", "http://localhost:5055")
ADMIN_URL = os.getenv("ADMIN_URL", "https://admin.1wolf.ru")

CLAN_NAME = os.getenv("CLAN_NAME", "Wings Of Lethal Force")
CLAN_TAG = os.getenv("CLAN_TAG", "1W0LF")
CLAN_TAG_DISPLAY = os.getenv("CLAN_TAG_DISPLAY", "=1W0LF=")
CLAN_MOTTO = os.getenv("CLAN_MOTTO", "We hunt. We don't hope.")
CLAN_REGION = os.getenv("CLAN_REGION", "Россия / СНГ")
DISCORD_INVITE = os.getenv("DISCORD_INVITE", "")
KVIYX_URL = os.getenv("KVIYX_URL", "https://kviyx.xyz")
BATTLES_API_KEY = os.getenv("BATTLES_API_KEY", "")

DISCORD_OAUTH_CLIENT_ID = os.getenv("DISCORD_OAUTH_CLIENT_ID", "")
DISCORD_OAUTH_CLIENT_SECRET = os.getenv("DISCORD_OAUTH_CLIENT_SECRET", "")
DISCORD_OAUTH_REDIRECT_URI = os.getenv("DISCORD_OAUTH_REDIRECT_URI", f"{SITE_URL}/auth/discord/callback")
DISCORD_APPS_ENABLED = _b("DISCORD_APPS_ENABLED")
DISCORD_BOT_API_URL = os.getenv("DISCORD_BOT_API_URL", "http://127.0.0.1:8757")
DISCORD_BOT_API_KEY = os.getenv("DISCORD_BOT_API_KEY", "")
DISCORD_NOTIFY_ENABLED = _b("DISCORD_NOTIFY_ENABLED")
DISCORD_NOTIFY_MODE = os.getenv("DISCORD_NOTIFY_MODE", "webhook")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "")
DISCORD_PING_ROLE_ID = os.getenv("DISCORD_PING_ROLE_ID", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

MAX_FILES = _i("MAX_FILES", 5)
MAX_FILE_MB = _i("MAX_FILE_MB", 8)
MAX_CONTENT_MB = _i("MAX_CONTENT_MB", 48)
ALLOWED_EXT = {e.strip().lower() for e in os.getenv(
    "ALLOWED_EXT", "png,jpg,jpeg,webp,gif,pdf,txt,log,mp4,webm"
).split(",") if e.strip()}
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

RATE_LIMITS = {
    "apply_ip": (_i("RL_APPLY_IP", 15), _i("RL_APPLY_IP_WINDOW", 86400)),
    "apply_burst": (_i("RL_APPLY_BURST", 1), _i("RL_APPLY_BURST_WINDOW", 120)),
    "login_ip": (_i("RL_LOGIN_IP", 20), _i("RL_LOGIN_IP_WINDOW", 900)),
    "login_user": (_i("RL_LOGIN_USER", 8), _i("RL_LOGIN_USER_WINDOW", 900)),
}

STATUS_RU = {"new": "Новая", "review": "На рассмотрении", "accepted": "Принят", "rejected": "Отклонена"}
