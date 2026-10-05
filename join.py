import re
import asyncio
import logging
from telethon import errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat

from core import load_app_config, TelegramClientManager
from core.client import clean_channel_identifier

logger = logging.getLogger(__name__)


async def join_channels():
    config = load_app_config()
    client_mgr = TelegramClientManager(config)
    client = client_mgr.client

    if not config.channels:
        logger.warning(
            f"No channels found in '{config.channels_file}'. "
            "Please add channel usernames or links (one per line)."
        )
        return

    logger.info(f"Loaded {len(config.channels)} channels from {config.channels_file}")
    if not await client_mgr.connect_with_retry():
        logger.error("Could not establish connection to Telegram.")
        return

    success = 0
    already_joined = 0
    failed = 0

    for raw_channel in config.channels:
        logger.info(f"Processing: {raw_channel}")
        clean = clean_channel_identifier(raw_channel)

        try:
            # Handle private invite links (e.g. +hash or joinchat/hash)
            if "+" in raw_channel or "joinchat/" in raw_channel:
                match = re.search(r"(?:\+|joinchat/)([a-zA-Z0-9_-]+)", raw_channel)
                if match:
                    invite_hash = match.group(1)
                    try:
                        await client(ImportChatInviteRequest(invite_hash))
                        logger.info(f"SUCCESS: Joined via invite link: {raw_channel}")
                        success += 1
                    except errors.UserAlreadyParticipantError:
                        logger.info(f"ALREADY JOINED: {raw_channel}")
                        already_joined += 1
                else:
                    logger.warning(f"Could not extract invite hash from: {raw_channel}")
                    failed += 1
                await asyncio.sleep(config.join_delay_seconds)
                continue

            # Standard public channel/group resolution
            target = int(clean) if re.match(r"^-?\d+$", clean) else clean
            entity = await client.get_entity(target)

            if not isinstance(entity, (Channel, Chat)):
                logger.warning(f"SKIPPED (Not a channel or supergroup): {raw_channel}")
                failed += 1
                continue

            # Attempt to join
            await client(JoinChannelRequest(entity))
            logger.info(f"SUCCESS: Joined channel {raw_channel} ('{entity.title}')")
            success += 1

            # Prevent flood wait
            await asyncio.sleep(config.join_delay_seconds)

        except errors.UserAlreadyParticipantError:
            logger.info(f"ALREADY JOINED: {raw_channel}")
            already_joined += 1

        except errors.FloodWaitError as fwe:
            wait_time = fwe.seconds + 2
            logger.error(
                f"FLOOD WAIT: Telegram rate-limit reached. Required cooldown: {fwe.seconds} seconds."
            )
            logger.info(f"Sleeping for {wait_time}s before continuing...")
            await asyncio.sleep(wait_time)
            failed += 1

        except errors.ChannelPrivateError:
            logger.warning(f"PRIVATE CHANNEL: You do not have permission to join: {raw_channel}")
            failed += 1

        except (errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
            logger.error(f"INVALID USERNAME: Channel does not exist: {raw_channel}")
            failed += 1

        except Exception as e:
            msg = str(e).lower()
            if "already" in msg:
                logger.info(f"ALREADY JOINED: {raw_channel}")
                already_joined += 1
            else:
                logger.error(f"FAILED to join {raw_channel}: {e}")
                failed += 1

    await client.disconnect()

    logger.info("========================================")
    logger.info("CHANNEL JOIN SUMMARY")
    logger.info(f"  Total Processed : {len(config.channels)}")
    logger.info(f"  Newly Joined    : {success}")
    logger.info(f"  Already Member  : {already_joined}")
    logger.info(f"  Failed / Skipped: {failed}")
    logger.info("========================================")


if __name__ == "__main__":
    asyncio.run(join_channels())