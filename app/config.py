import os
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


load_dotenv()


def _int_setting(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
JAVBUS_BASE_URL = os.getenv(
    "JAVBUS_BASE_URL", "https://www.javbus.com"
).strip().rstrip("/")
DATABASE_PATH = os.path.expanduser(
    os.getenv("DATABASE_PATH", "./data/bot.db").strip()
)
CACHE_TTL = _int_setting("CACHE_TTL", 21600)
GROUP_MAX_MAGNETS = _int_setting("GROUP_MAX_MAGNETS", 3)
PRIVATE_MAX_MAGNETS = _int_setting("PRIVATE_MAX_MAGNETS", 20)
MAX_CONCURRENT_FETCHES = _int_setting("MAX_CONCURRENT_FETCHES", 3, minimum=1)
USER_COOLDOWN_SECONDS = _int_setting("USER_COOLDOWN_SECONDS", 3)
DEBUG_SAVE_HTML = os.getenv("DEBUG_SAVE_HTML", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
DEBUG_DIR = os.getenv("DEBUG_DIR", "./debug").strip()
STATISTICS_TIMEZONE = os.getenv("STATISTICS_TIMEZONE", "Asia/Shanghai").strip()

_url = urlparse(JAVBUS_BASE_URL)
if _url.scheme not in {"http", "https"} or not _url.netloc:
    raise ValueError("JAVBUS_BASE_URL must be an absolute HTTP(S) URL")
try:
    ZoneInfo(STATISTICS_TIMEZONE)
except ZoneInfoNotFoundError as exc:
    raise ValueError("STATISTICS_TIMEZONE must be a valid IANA timezone") from exc


def validate_runtime_config() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing; configure it in .env")
