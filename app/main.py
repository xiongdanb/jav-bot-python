import asyncio
import html

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType, ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import (
    BOT_TOKEN,
    GROUP_MAX_MAGNETS,
    PRIVATE_MAX_MAGNETS,
)

from app.database import (
    init_db,
    add_query,
    add_user,
)

from app.javbus import query_javbus


router = Router()


@router.message(Command("start"))
async def start_handler(message: Message):
    await add_user(message.from_user.id)

    await message.answer(
        "👋 发送以下格式查询番号：\n\n"
        "/av SSIS-001\n\n"
        "也支持：\n"
        "/av ssis001\n"
        "/av SSIS_001"
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📖 使用方法\n\n"
        "/av 番号\n\n"
        "例如：\n"
        "/av SSIS-001"
    )


@router.message(Command("av"))
async def av_handler(message: Message):
    await add_user(message.from_user.id)

    if not message.text:
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "请输入番号，例如：\n"
            "/av SSIS-001"
        )
        return

    raw_code = parts[1].strip()

    waiting_message = await message.answer(
        "🔍 正在查询，请稍候……"
    )

    try:
        result = await query_javbus(raw_code)

        code = result["code"]
        title = result["title"]
        cover = result["cover"]
        magnets = result["magnets"]

        # 记录查询次数
        await add_query()

        if message.chat.type in {
            ChatType.GROUP,
            ChatType.SUPERGROUP,
        }:
            max_magnets = GROUP_MAX_MAGNETS
        else:
            max_magnets = PRIVATE_MAX_MAGNETS

        selected_magnets = magnets[:max_magnets]

        safe_code = html.escape(code)
        safe_title = html.escape(title)

        summary = (
            f"🎬 <b>{safe_code}</b>\n"
            f"📝 {safe_title}\n"
            f"🧲 共找到 {len(magnets)} 个磁力链接\n"
            f"📤 当前显示前 {len(selected_magnets)} 个"
        )

        if cover:
            try:
                await message.answer_photo(
                    photo=cover,
                    caption=summary,
                )
            except Exception as exc:
                print(
                    f"[封面发送失败] "
                    f"{type(exc).__name__}: {exc}"
                )

                await message.answer(summary)
        else:
            await message.answer(summary)

        if not selected_magnets:
            await message.answer(
                "⚠️ 没有找到磁力链接。"
            )
            return

        for index, magnet in enumerate(
            selected_magnets,
            start=1,
        ):
            link = magnet["link"]
            size = magnet.get("size", "")

            text = (
                f"🧲 <b>Magnet {index}</b>\n"
                f"📦 {html.escape(size)}\n\n"
                f"<code>{html.escape(link)}</code>"
            )

            await message.answer(text)

    except Exception as exc:
        print(
            f"[查询异常] {type(exc).__name__}: {exc}"
        )

        await message.answer(
            "❌ 查询失败。\n"
            "可能原因：番号不存在、网站暂时无法访问，"
            "或者页面结构发生变化。"
        )

    finally:
        try:
            await waiting_message.delete()
        except Exception:
            pass


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "没有配置 BOT_TOKEN，请检查 .env 文件"
        )

    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )

    dp = Dispatcher()
    dp.include_router(router)

    print("🤖 Telegram Bot 正在启动……")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())