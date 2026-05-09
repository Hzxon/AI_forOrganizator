#!/usr/bin/env python3
"""Reminder cron script — checks for due reminders and sends WhatsApp notifications."""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"

logger = logging.getLogger("reminder_cron")


def _load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


def _in_quiet_hours(cfg) -> bool:
    """Return True if current time falls within quiet_hours."""
    qh = cfg.get("reminders", {}).get("quiet_hours", {})
    if not qh:
        return False
    start = qh.get("start", "22:00")
    end   = qh.get("end", "07:00")
    now   = datetime.now().strftime("%H:%M")
    # handle overnight range
    if start > end:
        return now >= start or now <= end
    return start <= now <= end


def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send a WhatsApp message via Hermes gateway HTTP API."""
    logger.info("📱 WhatsApp → %s\n%s", phone, message)

    try:
        import urllib.request
        import urllib.error

        # Format chatId: strip + and append @s.whatsapp.net
        clean = phone.lstrip("+").replace(" ", "").replace("-", "")
        chat_id = f"{clean}@s.whatsapp.net"

        payload = json.dumps({"chatId": chat_id, "message": message}).encode()
        req = urllib.request.Request(
            "http://localhost:3000/send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("success"):
                raise RuntimeError(f"Gateway returned: {result}")

    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)
        log_path = PROJECT_ROOT / "logs" / "failed_reminders.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] ERROR={exc} → {phone}\n{message}\n---\n")
        return False

    # Log successful send
    log_path = PROJECT_ROOT / "logs" / "sent_reminders.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] → {phone}\n{message}\n---\n")

    return True


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(PROJECT_ROOT / "logs" / "organizer.log", encoding="utf-8"),
        ],
    )

    cfg   = _load_config()
    owner = cfg.get("whatsapp", {}).get("owner_number", "")
    if not owner:
        logger.error("No owner_number configured — check config/settings.yaml")
        sys.exit(1)

    if _in_quiet_hours(cfg):
        logger.info("Quiet hours — skipping reminders")
        return

    # import dispatcher here to avoid circular issues
    sys.path.insert(0, str(PROJECT_ROOT))
    from agents.dispatcher import EventDatabase, _db_path

    db = EventDatabase(_db_path(cfg))
    reminders = db.get_due_reminders()
    db.close()

    if not reminders:
        logger.info("No due reminders right now ✓")
        return

    logger.info("Found %d due reminder(s)", len(reminders))
    sent = 0
    for rem in reminders:
        if send_whatsapp_message(owner, rem["message"]):
            # mark as sent
            db2 = EventDatabase(_db_path(cfg))
            db2.mark_reminder_sent(rem["id"])
            db2.close()
            sent += 1

    logger.info("Sent %d/%d reminders", sent, len(reminders))


if __name__ == "__main__":
    main()
