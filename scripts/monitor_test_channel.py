"""Standalone test script to monitor @testagentf and verify live message arrival and alert delivery."""

import asyncio
import sys
from datetime import datetime, timezone
from telethon import events

# Ensure UTF-8 console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tgagent.config import load_config
from tgagent.llm.factory import create_classifier_model
from tgagent.telegram.client import TelegramSessionManager, clean_identifier
from tgagent.telegram.monitor import RealtimeMonitorEngine
from tgagent.telegram.notifier import TelegramNotifier

CHANNEL_HANDLE = "testagentf"
RECIPIENT_HANDLE = "dark5087knight"
CRITERIA = "Posts containing silly jokes"


async def main() -> None:
    print("=" * 60)
    print("TeleKeyword Finder - Live Channel Monitor Test")
    print(f"Target Channel   : @{CHANNEL_HANDLE}")
    print(f"Target Recipient : @{RECIPIENT_HANDLE}")
    print(f"Criteria         : {CRITERIA}")
    print("=" * 60)

    cfg = load_config()
    session_mgr = TelegramSessionManager(cfg)
    connected = await session_mgr.connect()
    if not connected:
        print("ERROR: Could not connect or authenticate Telethon session.")
        return

    client = session_mgr.client
    me = await client.get_me()
    print(f"[AUTH] Logged in as: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')})")

    # 1. Resolve channel
    try:
        channel_ent = await session_mgr.resolve_entity(CHANNEL_HANDLE)
        print(f"[CHANNEL] Successfully resolved: {channel_ent.title} (ID: {channel_ent.id})")
    except Exception as e:
        print(f"[ERROR] Could not resolve channel @{CHANNEL_HANDLE}: {e}")
        return

    # 2. Resolve recipient
    recipient_ent = None
    try:
        recipient_ent = await session_mgr.resolve_entity(RECIPIENT_HANDLE)
        print(f"[RECIPIENT] Successfully resolved: {getattr(recipient_ent, 'first_name', '')} (@{getattr(recipient_ent, 'username', RECIPIENT_HANDLE)})")
    except Exception as e:
        print(f"[WARNING] Could not directly resolve recipient @{RECIPIENT_HANDLE}: {e}")
        print(f"[RECIPIENT] Will attempt delivery using handle '{RECIPIENT_HANDLE}'")

    # 3. Initialize Classifier Model & Monitor Engine
    classifier_model = create_classifier_model(cfg)
    notifier = TelegramNotifier(client)
    engine = RealtimeMonitorEngine(
        session_mgr=session_mgr,
        classifier_model=classifier_model,
        notifier=notifier,
    )

    # 4. Check recent messages in channel
    print("\n--- Recent Messages in Channel ---")
    recent_msgs = await client.get_messages(channel_ent, limit=3)
    seen_ids = set()
    for m in recent_msgs:
        seen_ids.add(m.id)
        text_preview = (m.message or "").replace("\n", " ")[:60]
        print(f"  [Msg #{m.id}] {m.date.strftime('%Y-%m-%d %H:%M:%S UTC')} -> {text_preview}")

    print("\n" + "=" * 60)
    print(">>> LISTENER ACTIVATED! Waiting for new messages in @testagentf...")
    print(">>> Please send your test message to the channel now!")
    print("=" * 60 + "\n", flush=True)

    # 5. Live Message Event Handler
    @client.on(events.NewMessage(chats=[channel_ent]))
    async def on_new_msg(event: events.NewMessage.Event) -> None:
        msg = event.message
        if not msg or msg.id in seen_ids:
            return
        seen_ids.add(msg.id)

        post_text = (msg.message or msg.text or "").strip()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        print("\n" + "#" * 60)
        print(f"[LIVE MSG DETECTED] at {now_str}")
        print(f"Post ID: #{msg.id}")
        print(f"Content:\n{post_text}")
        print("#" * 60)

        # Run semantic evaluation
        print(f"[EVALUATING] Comparing post #{msg.id} against criteria: '{CRITERIA}'...")
        is_match, reason = await engine.evaluate_post(CRITERIA, post_text)
        print(f"[RESULT] Match={is_match} | Reason: {reason}")

        if is_match:
            print(f"[FORWARDING] Dispatching alert to @{RECIPIENT_HANDLE}...")
            delivered = await notifier.send_alert(
                recipient_entity=recipient_ent or RECIPIENT_HANDLE,
                post_message=msg,
                channel_name=getattr(channel_ent, "title", "Test Channel"),
                channel_handle=CHANNEL_HANDLE,
                matched_topics=[reason],
                agent_name="LiveTestAgent",
            )
            if delivered:
                print(f"[SUCCESS] Alert successfully forwarded to @{RECIPIENT_HANDLE}!")
            else:
                print(f"[FAILED] Could not deliver alert to @{RECIPIENT_HANDLE}.")
        else:
            print(f"[INFO] Post #{msg.id} did not match criteria.")

        print("\n>>> Continuing to listen for more messages...\n", flush=True)

    # Keep running until cancelled
    try:
        await client.run_until_disconnected()
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nStopping monitor...")
    finally:
        await session_mgr.disconnect()
        print("Disconnected cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
