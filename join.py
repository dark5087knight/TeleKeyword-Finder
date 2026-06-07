import asyncio
import yaml
import logging
import sys
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel

# =======================================
# LOAD CONFIG
# =======================================
def load_config():
    try:
        with open("teljobs.d/config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load config: {e}")
        exit(1)

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
SESSION_FILE = CONFIG['paths']['session_file']

# =======================================
# LOGGING
# =======================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# =======================================
# LOAD CHANNELS
# =======================================
def load_channels():
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Failed to load channels file: {e}")
        return []

CHANNELS = load_channels()

# =======================================
# CLIENT
# =======================================
client = TelegramClient(SESSION_FILE, api_id, api_hash)

# =======================================
# JOIN LOGIC
# =======================================
async def join_channels():
    await client.start(PHONE)
    logger.info("Connected to Telegram")

    success = 0
    failed = 0

    for channel in CHANNELS:
        try:
            logger.info(f"Processing: {channel}")

            # Resolve username → entity
            entity = await client.get_entity(channel)

            # Ensure it's a real channel
            if not isinstance(entity, Channel):
                logger.warning(f"SKIPPED (Not a channel): {channel}")
                failed += 1
                continue

            # Try joining
            await client(JoinChannelRequest(entity))
            logger.info(f"SUCCESS: Joined {channel}")
            success += 1

            await asyncio.sleep(3)  # avoid rate limit

        except Exception as e:
            msg = str(e).lower()

            if "already" in msg:
                logger.info(f"ALREADY JOINED: {channel}")
                success += 1
            elif "private" in msg:
                logger.warning(f"PRIVATE CHANNEL: {channel}")
                failed += 1
            elif "invalid" in msg or "cannot find" in msg:
                logger.error(f"INVALID USERNAME: {channel}")
                failed += 1
            elif "flood" in msg:
                logger.error("FLOOD WAIT detected. Sleeping 60 seconds...")
                await asyncio.sleep(60)
                failed += 1
            else:
                logger.error(f"FAILED: {channel} -> {e}")
                failed += 1

    await client.disconnect()

    logger.info("===================================")
    logger.info(f"JOIN COMPLETE")
    logger.info(f"SUCCESS: {success}")
    logger.info(f"FAILED: {failed}")
    logger.info("===================================")


# =======================================
# MAIN
# =======================================
if __name__ == "__main__":
    asyncio.run(join_channels())