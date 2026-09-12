import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}


JAVBUS_BASE_URL = os.getenv(
    "JAVBUS_BASE_URL",
    "https://www.javbus.com"
).rstrip("/")


DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "./data/bot.db"
)


CACHE_TTL = int(
    os.getenv("CACHE_TTL", "21600")
)


GROUP_MAX_MAGNETS = int(
    os.getenv("GROUP_MAX_MAGNETS", "3")
)


PRIVATE_MAX_MAGNETS = int(
    os.getenv("PRIVATE_MAX_MAGNETS", "20")
)