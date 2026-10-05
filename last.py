import argparse
import asyncio
import logging
from typing import Optional
from telethon.tl.types import Channel, Chat

from core import (
    load_app_config,
    TelegramClientManager,
    KeywordMatcher,
    SeenMessageStore,
    AlertNotifier,
)
from core.client import clean_channel_identifier

logger = logging.getLogger(__name__)


async def scan_recent_messages(limit: int = 30, force_resend: bool = False):
    """
    Scans the recent messages in all monitored channels,
    matches keywords, and sends alerts for new posts.
    """
    config = load_app_config()
    client_mgr = TelegramClientManager(config)
    client = client_mgr.client

    matcher = KeywordMatcher(config.keywords, config.exclude_keywords)
    seen_store = SeenMessageStore(config.seen_db_file)
    notifier = AlertNotifier(client, config)

    if not config.channels:
        logger.warning(f"No channels defined in '{config.channels_file}'.")
        return
    if not config.keywords:
        logger.warning(f"No keywords defined in '{config.keywords_file}'.")
        return

    logger.info(f"Connecting to Telegram for scan (limit: {limit} messages per channel)...")
    if not await client_mgr.connect_with_retry():
        logger.error("Could not establish connection to Telegram. Exiting.")
        return

    # Resolve target channels
    resolved_entities, _, by_id = await client_mgr.resolve_channels()
    if not resolved_entities:
        logger.warning("None of the configured channels could be resolved. Exiting.")
        await client.disconnect()
        return

    total_scanned = 0
    total_matched = 0
    new_alerts = 0

    for entity in resolved_entities:
        channel_name = getattr(entity, "title", str(entity.id))
        channel_username = getattr(entity, "username", None)
        logger.info(f"Scanning last {limit} messages in '{channel_name}'...")

        try:
            messages = await client.get_messages(entity, limit=limit)
        except Exception as e:
            logger.error(f"Failed fetching messages for '{channel_name}': {e}")
            continue

        # Process messages in chronological order (oldest to newest)
        for msg in reversed(messages):
            raw_text = msg.raw_text or ""
            if not raw_text:
                continue

            total_scanned += 1
            matches = matcher.find_all_matches(raw_text)
            if not matches:
                continue

            total_matched += 1

            # Check deduplication
            if not force_resend and seen_store.is_seen(entity.id, msg.id):
                logger.debug(
                    f"Skipping already seen message {msg.id} in '{channel_name}' (matched: {matches})"
                )
                continue

            # Send alert
            sent = await notifier.notify_users(
                matched_keywords=matches,
                channel_name=channel_name,
                channel_id=entity.id,
                message=msg,
                channel_username=channel_username,
            )

            if sent > 0:
                seen_store.mark_seen(entity.id, msg.id, matched_keyword=", ".join(matches))
                new_alerts += 1

    await client.disconnect()

    logger.info("========================================")
    logger.info("SCAN SUMMARY")
    logger.info(f"  Channels Scanned : {len(resolved_entities)}")
    logger.info(f"  Messages Scanned : {total_scanned}")
    logger.info(f"  Keyword Matches  : {total_matched}")
    logger.info(f"  New Alerts Sent  : {new_alerts}")
    logger.info("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan recent channel messages for keywords and dispatch alerts."
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=30,
        help="Number of recent messages to check per channel (default: 30)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-send alerts even if they were previously seen and notified.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(scan_recent_messages(limit=args.limit, force_resend=args.force))