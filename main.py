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
#  LOAD CONFIGURATION
# =======================================
def load_config():
    """Load configuration from YAML file"""
    try:
        with open("teljobs.d/config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("[ERROR] teljobs.d/config.yaml file not found!")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[ERROR] Error parsing teljobs.d/config.yaml: {e}")
        sys.exit(1)

# Load configuration file
CONFIG = load_config()

# Extract configuration values
api_id = CONFIG['telegram']['api_id']
api_hash = CONFIG['telegram']['api_hash']
PHONE = CONFIG['telegram']['phone']

# Validate Telegram credentials
if not api_id or api_id == '#' or not isinstance(api_id, int) or not api_hash or api_hash == '#' or not PHONE or PHONE == '#':
    print("\n[ERROR] Telegram API credentials are missing or invalid!")
    print("Please configure them directly in 'teljobs.d/config.yaml'.\n")
    sys.exit(1)

SEND_TO_USERS_FILE = CONFIG['bot']['send_to_users_file']
CHANNELS_FILE = CONFIG['paths']['channels_file']
KEYWORDS_FILE = CONFIG['paths']['keywords_file']
SESSION_FILE = CONFIG['paths']['session_file']
LOGS_DIR = CONFIG['paths']['logs_dir']
LOG_FILE = CONFIG['paths']['log_file']
RETRY_WAIT = CONFIG['retry']['retry_wait_seconds']
KEYBOARD_EXIT_KEY = CONFIG['keyboard']['exit_key']

# =======================================
#  LOGGING SETUP
# =======================================
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create formatters
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %I:%M:%S %p'
)

# File handler with rotation
file_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, LOG_FILE),
    maxBytes=5*1024*1024,  # 5MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(detailed_formatter)

# Console handler with UTF-8 encoding for Windows compatibility
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.stream.reconfigure(encoding='utf-8')
console_formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# =======================================
#  LOAD CHANNELS + KEYWORDS + USERS
# =======================================
def load_channels():
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_keywords():
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_send_to_users():
    with open(SEND_TO_USERS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

CHANNELS = load_channels()
KEYWORDS = load_keywords()
SEND_TO_USERS = load_send_to_users()

client = TelegramClient(SESSION_FILE, api_id, api_hash)

# Global flag for graceful shutdown
shutdown_flag = threading.Event()

# =======================================
#  MATCHING FUNCTION
# =======================================
def keyword_match(msg_text):
    for kw in KEYWORDS:
        pattern = rf"(?i)(?<!\w){re.escape(kw)}(?!\w)"
        if re.search(pattern, msg_text):
            return kw
    return None

# =======================================
#  PROCESS MESSAGE
# =======================================
async def process_message(event, channel_username):
    msg_text = event.raw_text or ""
    if not msg_text:
        return
    matched_keyword = keyword_match(msg_text)

    # mark single message as read
    try:
        await client.send_read_acknowledge(event.chat_id, event.message)
    except:
        pass

    if not matched_keyword:
        return

    # Get date and time from the message
    msg_date = event.message.date
    date_str = msg_date.strftime("%Y-%m-%d")
    time_str = msg_date.strftime("%I:%M:%S %p")

    final_msg = (
        f"Matched keyword: `{matched_keyword}`\n"
        f"Channel: {channel_username}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"-----------\n\n"
        f"Message:\n{msg_text}"
    )

    # Log the matched post with full details
    logger.info(f"MATCHED POST FOUND - Keyword: '{matched_keyword}' | Channel: {channel_username} | Date: {date_str} {time_str}")
    logger.debug(f"Message content: {msg_text[:200]}..." if len(msg_text) > 200 else f"Message content: {msg_text}")

    # Send to all configured users
    for user in SEND_TO_USERS:
        try:
            await client.send_message(user, final_msg, parse_mode="markdown")
            logger.info(f"POST SENT - Keyword: '{matched_keyword}' | Channel: {channel_username} | Recipient: {user}")
        except Exception as e:
            logger.error(f"Failed to send matched post to {user} from {channel_username}: {e}")


# =======================================
#  PROCESS ALL UNREAD MESSAGES
# =======================================
async def process_unread_messages():
    dialogs = await client.get_dialogs()

    for dialog in dialogs:
        if dialog.is_channel and dialog.entity.username:

            channel_username = f"@{dialog.entity.username}"

            if channel_username not in CHANNELS:
                continue

            unread_count = dialog.unread_count

            if unread_count == 0:
                continue

            logger.info(f"Checking {unread_count} unread messages in {channel_username}...")

            # fetch exactly the unread messages
            messages = await client.get_messages(dialog.entity, limit=unread_count)

            for msg in reversed(messages):
                msg_text = msg.raw_text or ""
                if not msg_text:
                    continue
                matched_keyword = keyword_match(msg_text)
                
                if not matched_keyword:
                    continue
                
                # Get date and time from the message
                msg_date = msg.date
                date_str = msg_date.strftime("%Y-%m-%d")
                time_str = msg_date.strftime("%I:%M:%S %p")
                
                final_msg = (
                    f"Matched keyword: `{matched_keyword}`\n"
                    f"Channel: {channel_username}\n"
                    f"Date: {date_str}\n"
                    f"Time: {time_str}\n"
                    f"-----------\n\n"
                    f"Message:\n{msg_text}"
                )
                
                # Log the matched post with full details
                logger.info(f"MATCHED POST FOUND - Keyword: '{matched_keyword}' | Channel: {channel_username} | Date: {date_str} {time_str}")
                logger.debug(f"Message content: {msg_text[:200]}..." if len(msg_text) > 200 else f"Message content: {msg_text}")
                
                # Send to all configured users
                for user in SEND_TO_USERS:
                    try:
                        await client.send_message(user, final_msg, parse_mode="markdown")
                        logger.info(f"POST SENT - Keyword: '{matched_keyword}' | Channel: {channel_username} | Recipient: {user}")
                    except Exception as e:
                        logger.error(f"Failed to send matched post to {user} from {channel_username}: {e}")

            # Mark ALL unread messages as read at once
            try:
                await client.send_read_acknowledge(dialog.entity)
            except:
                pass


# =======================================
#  REAL-TIME LISTENER
# =======================================
@client.on(events.NewMessage)
async def monitor_channels(event):

    if not event.is_channel:
        return

    chat = await event.get_chat()
    channel_username = f"@{chat.username}"

    if channel_username not in CHANNELS:
        return

    await process_message(event, channel_username)


# =======================================
#  KEYBOARD INPUT HANDLER
# =======================================
def keyboard_listener():
    """Listen for exit key press in a separate thread"""
    try:
        import keyboard
        logger.info(f"Press {KEYBOARD_EXIT_KEY.upper()} to safely exit the application...")
        keyboard.wait(KEYBOARD_EXIT_KEY)
        logger.info(f"{KEYBOARD_EXIT_KEY.upper()} pressed. Shutting down gracefully...")
        shutdown_flag.set()
    except ImportError:
        # Fallback to stdin if keyboard library not available
        logger.info("Press Enter to safely exit the application...")
        try:
            input()
            logger.info("Shutdown requested. Shutting down gracefully...")
            shutdown_flag.set()
        except:
            pass
    except Exception as e:
        logger.error(f"Keyboard listener error: {e}")

# =======================================
#  MAIN
# =======================================
async def connect_with_retry():
    """Connect to Telegram with retry logic"""
    retry_count = 0
    while not shutdown_flag.is_set():
        try:
            retry_count += 1
            logger.debug("Attempting to connect to Telegram...")
            await client.start(PHONE)
            if retry_count > 1:
                logger.info(f"CONNECTION RESTORED - Successfully reconnected to Telegram after {retry_count - 1} attempts")
            else:
                logger.info("Successfully connected to Telegram!")
            return True
        except OSError as e:
            if shutdown_flag.is_set():
                return False
            logger.error(f"CONNECTION FAILED - Attempt #{retry_count} - Network error: {e}")
            logger.warning(f"No internet connection or network error. Waiting {RETRY_WAIT} seconds before retry attempt #{retry_count + 1}...")
            await asyncio.sleep(RETRY_WAIT)
        except Exception as e:
            if shutdown_flag.is_set():
                return False
            logger.error(f"CONNECTION FAILED - Attempt #{retry_count} failed: {e}")
            logger.warning(f"Connection error. Waiting {RETRY_WAIT} seconds before retry attempt #{retry_count + 1}...")
            await asyncio.sleep(RETRY_WAIT)
    return False

async def main():
    # Connect with retry logic
    if not await connect_with_retry():
        logger.warning("Shutdown requested before connection. Exiting...")
        return

    logger.info("Checking unread messages…")
    try:
        await process_unread_messages()
    except Exception as e:
        logger.error(f"Error processing unread messages: {e}")

    logger.info("Monitoring new messages (auto-read enabled)…")
    
    # Start keyboard listener in a separate thread
    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()
    
    # Monitor shutdown flag while running client
    async def monitor_shutdown():
        while not shutdown_flag.is_set():
            await asyncio.sleep(0.5)
        if client.is_connected():
            logger.debug("Disconnecting...")
            await client.disconnect()
    
    # Create task to monitor shutdown
    shutdown_task = asyncio.create_task(monitor_shutdown())
    
    # Run client until disconnected, with reconnection logic
    try:
        while not shutdown_flag.is_set():
            try:
                await client.run_until_disconnected()
                # If we get here, connection was lost
                if shutdown_flag.is_set():
                    break
                logger.warning("CONNECTION LOST - Connection to Telegram was lost. Attempting to reconnect...")
                if not await connect_with_retry():
                    break
                logger.info("Reconnected! Resuming monitoring...")
            except KeyboardInterrupt:
                logger.warning("Interrupted. Shutting down gracefully...")
                shutdown_flag.set()
                break
            except OSError as e:
                if shutdown_flag.is_set():
                    break
                logger.error(f"CONNECTION ERROR - Network error: {e}")
                logger.warning(f"Connection aborted or network error detected. Waiting {RETRY_WAIT} seconds before reconnecting...")
                await asyncio.sleep(RETRY_WAIT)
                if not await connect_with_retry():
                    break
            except Exception as e:
                if shutdown_flag.is_set():
                    break
                logger.error(f"CONNECTION ERROR - Unexpected error: {e}")
                logger.warning(f"Waiting {RETRY_WAIT} seconds before reconnecting...")
                await asyncio.sleep(RETRY_WAIT)
                if not await connect_with_retry():
                    break
    finally:
        shutdown_task.cancel()
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass
        
        if client.is_connected():
            logger.debug("Disconnecting...")
            await client.disconnect()
        logger.info("Disconnected successfully. Goodbye!")

asyncio.run(main())
