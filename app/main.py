import asyncio
import html
import logging
import time

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.config import (
    BOT_TOKEN,
    GROUP_MAX_MAGNETS,
    PRIVATE_MAX_MAGNETS,
    USER_COOLDOWN_SECONDS,
    JAVBUS_BASE_URL,
    validate_runtime_config,
)
from app.database import add_query, add_user, init_db, prune_cache
from app.javbus import (
    BlockedError,
    FetchError,
    InvalidCodeError,
    JavBusError,
    NotFoundError,
    ParseError,
    close_http_client,
    download_cover,
    query_javbus,
    start_http_client,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
router = Router()
_last_request_at: dict[tuple[int, int], float] = {}


@router.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user:
        await add_user(message.from_user.id)
    await message.answer(
        "发送番号查询：\n\n/av SSIS-001\n\n也支持 /av ssis001 或 /av SSIS_001"
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer("使用方法：/av 番号\n例如：/av SSIS-001")


def _error_message(exc: JavBusError) -> str:
    if isinstance(exc, InvalidCodeError):
        return "番号格式不正确，请使用类似 SSIS-001 的格式。"
    if isinstance(exc, NotFoundError):
        return "没有找到这个番号。"
    if isinstance(exc, BlockedError):
        return "目标站暂时要求验证或拒绝访问，请稍后再试。"
    if isinstance(exc, ParseError):
        return "目标站页面结构发生变化，暂时无法解析。"
    if isinstance(exc, FetchError):
        return "访问查询站点失败，请稍后重试。"
    return "查询失败，请稍后重试。"


async def _send_result(message: Message, result: dict, max_magnets: int) -> None:
    code = result["code"]
    title = result["title"]
    cover = result["cover"]
    magnets = result["magnets"]
    selected = magnets[:max_magnets]
    summary = (
        f"🎬 <b>{html.escape(code)}</b>\n"
        f"📝 {html.escape(title[:500])}\n"
        f"🧲 共找到 {len(magnets)} 个磁力链接\n"
        f"📌 当前显示前 {len(selected)} 个"
    )

    summary_sent = False
    if cover:
        try:
            cover_bytes = await download_cover(
                cover,
                referer=f"{JAVBUS_BASE_URL}/{code}",
            )
            await message.answer_photo(
                BufferedInputFile(cover_bytes, filename="cover.jpg"),
                caption=summary,
            )
            summary_sent = True
        except Exception:
            logger.exception("Cover delivery failed for %s", code)
    if not summary_sent:
        try:
            await message.answer(summary)
        except Exception:
            logger.exception("Summary delivery failed for %s", code)

    if not selected:
        try:
            await message.answer("没有找到磁力链接。")
        except Exception:
            logger.exception("Empty-result notice failed for %s", code)
        return

    for index, magnet in enumerate(selected, start=1):
        link = magnet["link"]
        if len(link) > 3900:
            logger.warning("Magnet link exceeds Telegram message size for %s", code)
            try:
                await message.answer(f"Magnet {index} 链接过长，无法通过 Telegram 发送。")
            except Exception:
                logger.exception("Long-link notice failed for %s", code)
            continue
        text = (
            f"🧲 <b>Magnet {index}</b>\n"
            f"📦 {html.escape(magnet.get('size', '')[:200])}\n\n"
            f"<code>{html.escape(link)}</code>"
        )
        try:
            await message.answer(text)
        except Exception:
            logger.exception("Magnet %s delivery failed for %s", index, code)


@router.message(Command("av"))
async def av_handler(message: Message):
    user = message.from_user
    if not user or not message.text:
        return
    await add_user(user.id)

    now = time.monotonic()
    key = (message.chat.id, user.id)
    previous = _last_request_at.get(key, 0)
    if now - previous < USER_COOLDOWN_SECONDS:
        await message.answer("查询太频繁，请稍等几秒再试。")
        return
    _last_request_at[key] = now
    if len(_last_request_at) > 10000:
        cutoff = now - max(USER_COOLDOWN_SECONDS * 10, 60)
        recent_requests = {
            entry: timestamp
            for entry, timestamp in _last_request_at.items()
            if timestamp >= cutoff
        }
        _last_request_at.clear()
        _last_request_at.update(recent_requests)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("请输入番号，例如：/av SSIS-001")
        return

    waiting_message = await message.answer("🔎 正在查询，请稍候…")
    try:
        result = await query_javbus(parts[1].strip())
        await add_query()
        limit = (
            GROUP_MAX_MAGNETS
            if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}
            else PRIVATE_MAX_MAGNETS
        )
        await _send_result(message, result, limit)
    except JavBusError as exc:
        logger.info("Lookup failed: %s", type(exc).__name__)
        await message.answer(_error_message(exc))
    except Exception:
        logger.exception("Unexpected command handler failure")
        await message.answer("查询或发送结果时发生错误，请稍后重试。")
    finally:
        try:
            await waiting_message.delete()
        except Exception:
            logger.debug("Could not delete waiting message", exc_info=True)


async def main():
    validate_runtime_config()
    await init_db()
    await prune_cache()
    await start_http_client()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    try:
        logger.info("Telegram bot is starting")
        await dp.start_polling(bot)
    finally:
        await close_http_client()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
