#!.venv/bin/python3
from telethon import TelegramClient, events
import re
import asyncio
from datetime import datetime
import threading
import sys
import logging
from logging.handlers import RotatingFileHandler
import os
import yaml

# =======================================
# LOAD CONFIGURATION
# =======================================
def load_config():
    try:
        with open("teljobs.d/config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

# Load configuration file
CONFIG = load_config()

api_id = CONFIG['telegram']['api_id']
api_hash = CONFIG['telegram']['api_hash']
PHONE = CONFIG['telegram']['phone']

# Validate Telegram credentials
if not api_id or api_id == '#' or not isinstance(api_id, int) or not api_hash or api_hash == '#' or not PHONE or PHONE == '#':
    print("\n[ERROR] Telegram API credentials are missing or invalid!")
    print("Please configure them directly in 'teljobs.d/config.yaml'.\n")
    sys.exit(1)

CHANNELS_FILE = CONFIG['paths']['channels_file']
KEYWORDS_FILE = CONFIG['paths']['keywords_file']
SEND_TO_USERS_FILE = CONFIG['bot']['send_to_users_file']
SESSION_FILE = CONFIG['paths']['session_file']
LOGS_DIR = CONFIG['paths']['logs_dir']
LOG_FILE = CONFIG['paths']['log_file']
RETRY_WAIT = CONFIG['retry']['retry_wait_seconds']
EXIT_KEY = CONFIG['keyboard']['exit_key']

# =======================================
# LOGGING SETUP
# =======================================
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %I:%M:%S %p'
)

file_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, LOG_FILE),
    maxBytes=5*1024*1024,
    backupCount=3
)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# =======================================
# LOAD FILES
# =======================================
def load_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

CHANNELS = load_file(CHANNELS_FILE)
KEYWORDS = load_file(KEYWORDS_FILE)
SEND_TO_USERS = load_file(SEND_TO_USERS_FILE)

client = TelegramClient(SESSION_FILE, api_id, api_hash)
shutdown_flag = threading.Event()

# =======================================
# KEYWORD MATCH
# =======================================
def keyword_match(text):
    for kw in KEYWORDS:
        if re.search(rf"(?i)(?<!\w){re.escape(kw)}(?!\w)", text):
            return kw
    return None

# =======================================
# PROCESS MESSAGE
# =======================================
async def process_message(msg, channel_username):
    msg_text = msg.raw_text or ""
    if not msg_text:
        return

    matched = keyword_match(msg_text)
    if not matched:
        return

    msg_date = msg.date
    date_str = msg_date.strftime("%Y-%m-%d")
    time_str = msg_date.strftime("%I:%M:%S %p")

    final_msg = (
        f"Matched keyword: `{matched}`\n"
        f"Channel: {channel_username}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"-----------\n\n"
        f"{msg_text}"
    )

    logger.info(f"MATCHED: {matched} | {channel_username} | {date_str} {time_str}")

    for user in SEND_TO_USERS:
        try:
            await client.send_message(user, final_msg, parse_mode="markdown")
        except Exception as e:
            logger.error(f"Send failed to {user}: {e}")

# =======================================
# PROCESS LAST 30 MESSAGES
# =======================================
async def process_last_messages():
    dialogs = await client.get_dialogs()

    for dialog in dialogs:
        if not (dialog.is_channel and dialog.entity.username):
            continue

        channel = f"@{dialog.entity.username}"

        if channel not in CHANNELS:
            continue

        logger.info(f"Checking last 30 messages in {channel}")

        try:
            messages = await client.get_messages(dialog.entity, limit=30)
        except Exception as e:
            logger.error(f"Failed fetching {channel}: {e}")
            continue

        for msg in reversed(messages):
            await process_message(msg, channel)

# =======================================
# REAL-TIME MONITOR
# =======================================
@client.on(events.NewMessage)
async def monitor(event):
    if not event.is_channel:
        return

    chat = await event.get_chat()
    channel = f"@{chat.username}"

    if channel not in CHANNELS:
        return

    await process_message(event.message, channel)

# =======================================
# CONNECTION
# =======================================
async def connect():
    while not shutdown_flag.is_set():
        try:
            await client.start(PHONE)
            logger.info("Connected to Telegram")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await asyncio.sleep(RETRY_WAIT)
    return False

# =======================================
# KEYBOARD EXIT
# =======================================
def keyboard_listener():
    try:
        import keyboard
        keyboard.wait(EXIT_KEY)
    except:
        input()
    shutdown_flag.set()

# =======================================
# MAIN
# =======================================
async def main():
    if not await connect():
        return

    await process_last_messages()

    logger.info("Monitoring new messages...")

    threading.Thread(target=keyboard_listener, daemon=True).start()

    async def shutdown_monitor():
        while not shutdown_flag.is_set():
            await asyncio.sleep(0.5)
        await client.disconnect()

    asyncio.create_task(shutdown_monitor())

    await client.run_until_disconnected()

asyncio.run(main())