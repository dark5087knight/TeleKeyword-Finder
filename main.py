import asyncio
import logging
from telethon import events
from telethon.tl.types import Channel, Chat

from core import (
    load_app_config,
    TelegramClientManager,
    KeywordMatcher,
    SeenMessageStore,
    AlertNotifier,
    GracefulShutdown,
)

logger = logging.getLogger(__name__)


async def main():
    config = load_app_config()
    client_mgr = TelegramClientManager(config)
    client = client_mgr.client

    matcher = KeywordMatcher(config.keywords, config.exclude_keywords)
    seen_store = SeenMessageStore(config.seen_db_file)
    notifier = AlertNotifier(client, config)
    shutdown = GracefulShutdown(exit_key=config.exit_key, enable_keyboard=config.keyboard_enabled)

    # Prune seen database entries older than 30 days on startup
    seen_store.prune_old_messages(days=30)

    # 1. Connect to Telegram
    logger.info("Connecting to Telegram...")
    if not await client_mgr.connect_with_retry(shutdown.event):
        logger.warning("Shutdown signaled before connection established. Exiting...")
        return

    # 2. Setup OS signal & keyboard handlers
    shutdown.setup()

    # 3. Resolve target channels
    logger.info("Resolving monitored channels...")
    resolved_entities, _, by_id = await client_mgr.resolve_channels()

    if not resolved_entities:
        logger.error(
            "None of the channels in channels.conf could be resolved! "
            "Please check channel usernames and run 'python join.py' first."
        )
        await client.disconnect()
        return

    # 4. Helper to process any message (shared by catch-up & real-time)
    async def handle_message(msg, channel_entity) -> bool:
        raw_text = msg.raw_text or ""
        if not raw_text:
            return False

        # Check keyword matches
        matches = matcher.find_all_matches(raw_text)
        if not matches:
            return False

        channel_id = channel_entity.id
        channel_name = getattr(channel_entity, "title", str(channel_id))
        channel_username = getattr(channel_entity, "username", None)

        # Check deduplication
        if seen_store.is_seen(channel_id, msg.id):
            logger.debug(
                f"Skipping already notified message {msg.id} in '{channel_name}'"
            )
            return False

        # Send alert
        sent = await notifier.notify_users(
            matched_keywords=matches,
            channel_name=channel_name,
            channel_id=channel_id,
            message=msg,
            channel_username=channel_username,
        )

        if sent > 0:
            seen_store.mark_seen(channel_id, msg.id, matched_keyword=", ".join(matches))

        # Acknowledge read if configured
        if config.auto_read:
            try:
                await client.send_read_acknowledge(channel_entity, max_id=msg.id)
            except Exception as read_err:
                logger.debug(f"Could not mark message as read: {read_err}")

        return True

    # 5. Process unread catch-up messages on startup
    logger.info("Checking for unread messages received while offline...")
    try:
        dialogs = await client.get_dialogs()
        for dialog in dialogs:
            if shutdown.is_triggered:
                break

            if dialog.entity and dialog.entity.id in by_id:
                unread_count = dialog.unread_count
                if unread_count <= 0:
                    continue

                entity = by_id[dialog.entity.id]
                channel_name = getattr(entity, "title", str(entity.id))
                logger.info(f"Processing {unread_count} unread messages in '{channel_name}'...")

                try:
                    unread_messages = await client.get_messages(entity, limit=unread_count)
                    for msg in reversed(unread_messages):
                        if shutdown.is_triggered:
                            break
                        await handle_message(msg, entity)

                    if config.auto_read:
                        try:
                            await client.send_read_acknowledge(entity)
                        except Exception:
                            pass
                except Exception as unread_err:
                    logger.error(f"Error fetching unread messages for '{channel_name}': {unread_err}")
    except Exception as e:
        logger.error(f"Error during unread catch-up: {e}")

    # 6. Register targeted real-time event listener
    # Passing chats=resolved_entities prevents waking up on unrelated private chats/groups!
    @client.on(events.NewMessage(chats=resolved_entities))
    async def real_time_listener(event):
        try:
            chat = await event.get_chat()
            await handle_message(event.message, chat)
        except Exception as err:
            logger.error(f"Error in real-time message handler: {err}", exc_info=True)

    logger.info(f"Monitoring active across {len(resolved_entities)} channels in real-time...")
    logger.info("Waiting for matching posts. (Auto-read enabled)" if config.auto_read else "Waiting for matching posts.")

    # 7. Run until shutdown event is triggered or client disconnects
    async def wait_for_shutdown():
        await shutdown.wait()
        if client.is_connected():
            logger.info("Disconnecting client...")
            await client.disconnect()

    shutdown_task = asyncio.create_task(wait_for_shutdown())

    try:
        while not shutdown.is_triggered:
            try:
                await client.run_until_disconnected()
                if shutdown.is_triggered:
                    break
                logger.warning("Connection lost! Attempting to reconnect...")
                if not await client_mgr.connect_with_retry(shutdown.event):
                    break
            except (KeyboardInterrupt, SystemExit):
                shutdown.trigger("Interrupt received")
                break
            except Exception as e:
                if shutdown.is_triggered:
                    break
                logger.error(f"Unexpected connection error: {e}")
                if not await client_mgr.connect_with_retry(shutdown.event):
                    break
    finally:
        shutdown_task.cancel()
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass

        if client.is_connected():
            await client.disconnect()
        logger.info("Bot stopped successfully. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
