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
MAGNET_CACHE_TTL = _int_setting("MAGNET_CACHE_TTL", 1800)
GROUP_MAX_MAGNETS = _int_setting("GROUP_MAX_MAGNETS", 3)
PRIVATE_MAX_MAGNETS = _int_setting("PRIVATE_MAX_MAGNETS", 20)
MAX_CONCURRENT_FETCHES = _int_setting("MAX_CONCURRENT_FETCHES", 3, minimum=1)
USER_COOLDOWN_SECONDS = _int_setting("USER_COOLDOWN_SECONDS", 3)
TELEGRAM_SEND_CONCURRENCY = _int_setting("TELEGRAM_SEND_CONCURRENCY", 2, minimum=1)
STATISTICS_TIMEZONE = os.getenv("STATISTICS_TIMEZONE", "Asia/Shanghai").strip()

_url = urlparse(JAVBUS_BASE_URL)
if (
    _url.scheme not in {"http", "https"}
    or not _url.netloc
    or _url.username is not None
    or _url.password is not None
    or _url.query
    or _url.fragment
    or _url.port not in {None, 80, 443}
):
    raise ValueError("JAVBUS_BASE_URL must be an absolute HTTP(S) URL")
UPSTREAM_ALLOWED_HOSTS = {
    host.strip().lower().rstrip(".")
    for host in os.getenv("UPSTREAM_ALLOWED_HOSTS", _url.hostname or "").split(",")
    if host.strip()
}
if (_url.hostname or "").lower().rstrip(".") not in UPSTREAM_ALLOWED_HOSTS:
    raise ValueError("UPSTREAM_ALLOWED_HOSTS must include JAVBUS_BASE_URL host")
try:
    ZoneInfo(STATISTICS_TIMEZONE)
except ZoneInfoNotFoundError as exc:
    raise ValueError("STATISTICS_TIMEZONE must be a valid IANA timezone") from exc


def validate_runtime_config() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing; configure it in .env")
