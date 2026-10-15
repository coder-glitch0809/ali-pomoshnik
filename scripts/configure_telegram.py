"""Set public bot branding without sending messages or exposing credentials."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telegram import Bot, BotCommand, MenuButtonCommands
from ali.config import config
from ali.telegram_bot import PUBLIC_COMMANDS


async def main():
    async with Bot(config.telegram_token) as bot:
        await bot.set_my_name(config.telegram_name)
        await bot.set_my_description("✨ Ali — AI yordamchingiz. Savol bering, kontent uchun ruxsat so‘rang, ob-havoni bilib oling va mutaxassis agentlardan foydalaning. Boshlash: /start")
        await bot.set_my_short_description("Ali Pomoshnik — shaxsiy yordamchingiz va AI jamoangiz.")
        await bot.set_my_commands([BotCommand(c, d) for c, d in PUBLIC_COMMANDS])
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        me = await bot.get_me()
        print(f"Bot configured: @{me.username}; name={me.first_name}")


if __name__ == "__main__":
    asyncio.run(main())
