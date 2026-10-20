"""Interactive Telethon login script.

Used by the operator to authenticate the reading account once via CLI.
Credentials and login codes never pass through the bot or conversational LLM.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, cast
from telethon import TelegramClient
from dotenv import load_dotenv


async def authenticate() -> None:
    load_dotenv()
    api_id_raw = os.getenv("TG_API_ID") or os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TG_API_HASH") or os.getenv("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE")

    if not api_id_raw or not api_hash:
        print("Error: TG_API_ID (or TELEGRAM_API_ID) and TG_API_HASH (or TELEGRAM_API_HASH) must be set in your .env file.")
        return

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    session_file = data_dir / "default.session"

    client = TelegramClient(str(session_file), int(api_id_raw), api_hash)
    # Telethon's start() returns a coroutine when an event loop is running,
    # but its static type signature is annotated as TelegramClient instead of Awaitable.
    if phone:
        await cast(Awaitable[Any], client.start(phone=phone))
    else:
        await cast(Awaitable[Any], client.start())

    me = await client.get_me()
    print(f"Successfully authenticated as: {me.first_name} (@{me.username})")
    await client.disconnect()


def main() -> None:
    asyncio.run(authenticate())


if __name__ == "__main__":
    main()
