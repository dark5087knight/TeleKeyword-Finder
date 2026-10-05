import html
import asyncio
import logging
from typing import List, Optional, Union
from telethon import TelegramClient, errors
from telethon.tl.types import Message

from .config import AppConfig

logger = logging.getLogger(__name__)


def build_telegram_post_link(
    channel_username: Optional[str],
    channel_id: Union[str, int],
    message_id: int,
) -> Optional[str]:
    """
    Constructs a direct, clickable Telegram link to the post.
    Works for both public channels (@username) and joined private channels (-100...).
    """
    if channel_username and channel_username.strip():
        clean_user = channel_username.strip().lstrip("@")
        if clean_user and clean_user.lower() != "none":
            return f"https://t.me/{clean_user}/{message_id}"

    # Handle numeric channel IDs
    try:
        raw_id = int(str(channel_id).strip())
        str_id = str(abs(raw_id))
        # Telethon channel IDs usually start with 100 for supergroups/channels
        if str_id.startswith("100") and len(str_id) > 3:
            clean_id = str_id[3:]
        else:
            clean_id = str_id
        return f"https://t.me/c/{clean_id}/{message_id}"
    except (ValueError, TypeError):
        return None


def is_real_media(media) -> bool:
    """
    Check if media is an actual visual or document attachment (photo, flyer, doc)
    and not just an external web page link preview.
    """
    if not media:
        return False
    from telethon.tl.types import MessageMediaWebPage, MessageMediaEmpty, MessageMediaPoll
    if isinstance(media, (MessageMediaWebPage, MessageMediaEmpty, MessageMediaPoll)):
        return False
    return True


class AlertNotifier:
    """
    Handles robust alert delivery to Telegram users with:
    - Crash-proof HTML formatting (escapes raw text to prevent markdown syntax failures)
    - Direct post link generation
    - Telegram 4096-character limit truncation protection
    - Media attachment support (photos, PDF flyers, documents attached directly)
    - Caption limit (1024 chars) handling with automatic split
    - FloodWait and rate-limit backoff
    """

    def __init__(self, client: TelegramClient, config: AppConfig):
        self.client = client
        self.config = config

    def format_alert_card(
        self,
        matched_keywords: List[str] | str,
        channel_name: str,
        message: Message,
        post_link: Optional[str] = None,
    ) -> str:
        """Constructs a clean HTML alert card."""
        if isinstance(matched_keywords, list):
            kw_display = ", ".join(f"<code>{html.escape(k)}</code>" for k in matched_keywords)
        else:
            kw_display = f"<code>{html.escape(str(matched_keywords))}</code>"

        msg_date = message.date
        date_str = msg_date.strftime("%Y-%m-%d") if msg_date else "N/A"
        time_str = msg_date.strftime("%I:%M:%S %p") if msg_date else "N/A"

        link_line = f"<b>Link:</b> <a href=\"{post_link}\">Open Post in Telegram</a>\n" if post_link else ""

        header = (
            f"<b>Keyword Matched:</b> {kw_display}\n"
            f"<b>Channel:</b> {html.escape(channel_name)}\n"
            f"{link_line}"
            f"<b>Date:</b> {date_str} {time_str}\n"
            f"────────────────────────\n\n"
        )

        raw_text = message.raw_text or ""
        escaped_body = html.escape(raw_text)

        # Telegram hard limit is 4096. Reserve room for header and footer.
        max_body_len = 3800 - len(header)
        if len(escaped_body) > max_body_len:
            escaped_body = escaped_body[:max_body_len] + "\n\n<i>[Message truncated — click the link above for full post]</i>"

        return header + escaped_body

    def format_short_media_caption(
        self,
        matched_keywords: List[str] | str,
        channel_name: str,
        message: Message,
        post_link: Optional[str] = None,
    ) -> str:
        """Constructs a concise caption (under 1024 chars) to accompany media."""
        if isinstance(matched_keywords, list):
            kw_display = ", ".join(f"<code>{html.escape(k)}</code>" for k in matched_keywords)
        else:
            kw_display = f"<code>{html.escape(str(matched_keywords))}</code>"

        msg_date = message.date
        date_str = msg_date.strftime("%Y-%m-%d %I:%M %p") if msg_date else "N/A"
        link_line = f"<b>Link:</b> <a href=\"{post_link}\">Open Post in Telegram</a>\n" if post_link else ""

        header = (
            f"<b>Keyword Matched:</b> {kw_display}\n"
            f"<b>Channel:</b> {html.escape(channel_name)}\n"
            f"{link_line}"
            f"<b>Date:</b> {date_str}\n"
            f"────────────────────────\n"
        )
        raw_text = (message.raw_text or "").strip()
        available_len = 1000 - len(header) - 35
        if len(raw_text) > available_len:
            preview = html.escape(raw_text[:available_len]) + "...\n<i>[Full text in next message]</i>"
        else:
            preview = html.escape(raw_text)

        return header + preview

    async def notify_users(
        self,
        matched_keywords: List[str] | str,
        channel_name: str,
        channel_id: Union[str, int],
        message: Message,
        channel_username: Optional[str] = None,
    ) -> int:
        """
        Sends notifications to all configured recipients.
        Returns number of successfully sent recipients.
        """
        if not self.config.recipients:
            logger.warning("No recipient users configured in send_to_users.conf!")
            return 0

        post_link = build_telegram_post_link(channel_username, channel_id, message.id)
        card_text = self.format_alert_card(matched_keywords, channel_name, message, post_link)

        kw_str = ", ".join(matched_keywords) if isinstance(matched_keywords, list) else str(matched_keywords)
        logger.info(
            f"MATCH FOUND: [{kw_str}] in '{channel_name}' (ID: {channel_id}, Msg: {message.id})"
        )

        has_media = is_real_media(message.media) and self.config.attach_media
        success_count = 0

        for user in self.config.recipients:
            try:
                # Mode A: Forward original post directly
                if self.config.forward_original:
                    notice = (
                        f"<b>Keyword Matched:</b> <code>{html.escape(kw_str)}</code> from <b>{html.escape(channel_name)}</b>\n"
                        f"{'<a href=\"' + post_link + '\">Original Post</a>' if post_link else ''}"
                    )

                    await self.client.send_message(user, notice, parse_mode="html")
                    await self.client.forward_messages(user, message)
                else:
                    # Mode B: Send card with picture attached
                    if has_media:
                        if len(card_text) <= 1024:
                            # Attach picture directly with full card text as caption
                            try:
                                await self.client.send_message(
                                    user,
                                    card_text,
                                    parse_mode="html",
                                    file=message.media,
                                )
                            except Exception as media_err:
                                logger.warning(
                                    f"Could not send media with caption to {user}: {media_err}. Falling back to text."
                                )
                                await self.client.send_message(user, card_text, parse_mode="html", link_preview=False)
                        else:
                            # Caption exceeds 1024 limit: send media with short preview caption, followed by full text
                            short_cap = self.format_short_media_caption(matched_keywords, channel_name, message, post_link)
                            try:
                                await self.client.send_message(
                                    user,
                                    short_cap,
                                    parse_mode="html",
                                    file=message.media,
                                )
                                await self.client.send_message(user, card_text, parse_mode="html", link_preview=False)
                            except Exception as media_err:
                                logger.warning(
                                    f"Could not send media attachment to {user}: {media_err}. Falling back to text."
                                )
                                await self.client.send_message(user, card_text, parse_mode="html", link_preview=False)
                    else:
                        await self.client.send_message(user, card_text, parse_mode="html", link_preview=False)

                logger.info(f"ALERT SENT -> {user} for match [{kw_str}]" + (" (with picture)" if has_media else ""))
                success_count += 1
                await asyncio.sleep(0.5)  # Slight rate-limit cushion

            except errors.FloodWaitError as fwe:
                logger.warning(f"Telegram FloodWait while sending to {user}. Waiting {fwe.seconds}s...")
                await asyncio.sleep(fwe.seconds + 1)
                # Retry once
                try:
                    await self.client.send_message(user, card_text, parse_mode="html", link_preview=False)
                    success_count += 1
                except Exception as retry_err:
                    logger.error(f"Retry failed for {user}: {retry_err}")

            except errors.UserIsBlockedError:
                logger.error(f"Cannot send to {user}: User has blocked this account or bot.")
            except (errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
                logger.error(f"Cannot send to {user}: Username does not exist or is invalid.")
            except Exception as e:
                logger.error(f"Failed sending alert to {user}: {e}")

        return success_count

