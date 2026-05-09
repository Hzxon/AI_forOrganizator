#!/usr/bin/env python3
"""Ingest inbound WhatsApp messages directly from the bridge HTTP API.

This reads ALL messages from the WhatsApp bridge (port 3000), bypassing
the gateway's policy filters. This lets you set DM_POLICY=disabled and
GROUP_POLICY=disabled to silence Hermes auto-replies while still
capturing every message for the Event Organizer.

The bridge's /messages endpoint returns ALL inbound messages as JSON.
Each call returns and clears the message queue (polling pattern).
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"
STATE_FILE   = PROJECT_ROOT / "storage" / "ingest_state.json"
BRIDGE_URL   = "http://127.0.0.1:3000/messages"

logger = logging.getLogger("ingest")


def _load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


def load_seen_ids() -> set:
    """Load set of already-processed message IDs."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            data = json.load(f)
        return set(data.get("seen_ids", []))
    return set()


def save_seen_ids(seen: set, max_keep: int = 5000):
    """Save seen IDs, trimming to avoid unbounded growth."""
    # Keep only the most recent max_keep IDs
    trimmed = list(seen)[-max_keep:] if len(seen) > max_keep else list(seen)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"seen_ids": trimmed, "updated_at": datetime.now().isoformat()}, f)


def poll_bridge() -> list[dict]:
    """Poll the bridge /messages endpoint for new inbound messages."""
    try:
        req = Request(BRIDGE_URL, method="GET")
        with urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return json.loads(resp.read())
    except URLError as e:
        logger.warning("Bridge unreachable at %s: %s", BRIDGE_URL, e)
    except Exception as e:
        logger.warning("Bridge poll error: %s", e)
    return []


def extract_message_id(data: dict) -> str:
    """Get a unique ID from bridge message data."""
    # Try common ID fields from the bridge
    for key in ["id", "messageId", "msgId", "_id"]:
        if data.get(key):
            return str(data[key])
    # Fallback: hash of sender + body + timestamp
    body = data.get("body", "")
    sender = data.get("from", data.get("senderId", ""))
    ts = data.get("timestamp", "")
    return f"{sender}:{ts}:{body[:40]}"


def should_process(msg: dict, cfg: dict) -> bool:
    """Check if a message should be processed based on Event Organizer config."""
    wa_cfg = cfg.get("whatsapp", {})
    is_group = msg.get("isGroup", False)

    if is_group:
        return True  # Process all group messages (monitor filters by relevance)
    else:
        return wa_cfg.get("monitor_private", True)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(PROJECT_ROOT / "logs" / "organizer.log", encoding="utf-8"),
        ],
    )

    cfg = _load_config()
    seen_ids = load_seen_ids()

    # Poll the bridge
    raw_messages = poll_bridge()

    if not raw_messages:
        logger.info("No new messages from bridge")
        return

    logger.info("Bridge returned %d message(s)", len(raw_messages))

    # Filter: skip already-seen, skip own messages, skip system messages
    new_messages = []
    for data in raw_messages:
        msg_id = extract_message_id(data)

        # Skip duplicates
        if msg_id in seen_ids:
            continue

        # Skip messages from self (fromMe flag)
        if data.get("fromMe", False):
            seen_ids.add(msg_id)
            continue

        # Skip empty/system messages
        body = str(data.get("body", "")).strip()
        if not body or len(body) < 2:
            seen_ids.add(msg_id)
            continue

        # Skip notification/system messages
        if data.get("type") in ["notification", "protocol", "e2e_notification", "gp2"]:
            seen_ids.add(msg_id)
            continue

        new_messages.append(data)
        seen_ids.add(msg_id)

    save_seen_ids(seen_ids)

    if not new_messages:
        logger.info("No new processable messages")
        return

    # Filter by Event Organizer config
    processable = [m for m in new_messages if should_process(m, cfg)]
    logger.info("Processing %d/%d messages", len(processable), len(new_messages))

    # Import agents
    sys.path.insert(0, str(PROJECT_ROOT))
    from agents.monitor import MonitorAgent
    from agents.dispatcher import DispatcherAgent

    monitor    = MonitorAgent(cfg)
    dispatcher = DispatcherAgent(cfg)

    processed = 0
    forwarded = 0

    for data in processable:
        processed += 1
        body = str(data.get("body", "")).strip()
        sender = data.get("pushName", data.get("sender", "Unknown"))
        is_group = data.get("isGroup", False)
        chat_id = data.get("chatId", data.get("from", ""))

        message_obj = {
            "text":      body,
            "group":     chat_id if is_group else "",
            "sender":    sender,
            "timestamp": datetime.now().isoformat(),
        }

        summary = monitor.process_message(message_obj)
        if summary and summary.get("should_forward"):
            monitor.forward_to_dispatcher(summary)
            created = dispatcher.process_summary(summary)
            forwarded += 1
            logger.info("→ Forwarded: %d events, %d actions from '%s' in %s",
                        len(created["events"]), len(created["actions"]),
                        body[:60], chat_id[:30])

    dispatcher.close()
    logger.info("Done: %d processed, %d forwarded", processed, forwarded)


if __name__ == "__main__":
    main()
