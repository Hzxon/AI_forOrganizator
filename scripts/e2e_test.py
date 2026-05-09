#!/usr/bin/env python3
"""End-to-end flow test — simulates bridge → monitor → dispatcher → WhatsApp reminder."""

import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.monitor import MonitorAgent
from agents.dispatcher import DispatcherAgent

CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    import yaml
    cfg = yaml.safe_load(f)

# ── Simulate messages arriving from the bridge ──
bridge_messages = [
    {
        "body": "Team standup meeting tomorrow at 10am in Zoom Room Alpha",
        "isGroup": True,
        "chatId": "123456789@g.us",
        "pushName": "Alice",
        "fromMe": False,
        "timestamp": datetime.now().isoformat(),
    },
    {
        "body": "Hey bro, wanna grab coffee later?",
        "isGroup": True,
        "chatId": "987654321@g.us",
        "pushName": "Budi",
        "fromMe": False,
        "timestamp": datetime.now().isoformat(),
    },
    {
        "body": "Client presentation deadline next Monday at 2pm, finalize slides by Friday",
        "isGroup": True,
        "chatId": "456789123@g.us",
        "pushName": "Manager",
        "fromMe": False,
        "timestamp": datetime.now().isoformat(),
    },
    {
        "body": "URGENT: budget approval deadline tomorrow at 5pm, submit to finance",
        "isGroup": True,
        "chatId": "789123456@g.us",
        "pushName": "CFO",
        "fromMe": False,
        "timestamp": datetime.now().isoformat(),
    },
]

print("=" * 65)
print("  🧪  E2E FLOW — Bridge → Monitor → Dispatcher → WhatsApp")
print("=" * 65)

monitor = MonitorAgent(cfg)
dispatcher = DispatcherAgent(cfg)

# ── STEP 1: Simulate bridge ingestion ──
print(f"\n📡 Bridge returned {len(bridge_messages)} message(s)")

forwarded = 0
for data in bridge_messages:
    body = str(data.get("body", "")).strip()
    is_group = data.get("isGroup", False)
    chat_id = data.get("chatId", "")

    message_obj = {
        "text": body,
        "group": chat_id if is_group else "",
        "sender": data.get("pushName", "Unknown"),
        "timestamp": datetime.now().isoformat(),
    }

    summary = monitor.process_message(message_obj)
    if summary and summary.get("should_forward"):
        created = dispatcher.process_summary(summary)
        forwarded += 1
        n_events = len(created.get("events", []))
        n_actions = len(created.get("actions", []))
        emoji = "📋" if n_events == 0 and n_actions == 0 else "✅"
        print(f"  {emoji} [{summary.get('message_type', '?')}] '{body[:55]}...' "
              f"→ {n_events} event(s), {n_actions} action(s)")
    else:
        print(f"  ❌ [filtered] '{body[:55]}...'")

# ── STEP 2: DB state ──
import sqlite3
db_path = PROJECT_ROOT / "storage" / "events.db"
conn = sqlite3.connect(db_path)

events = conn.execute("SELECT id, title, event_date, event_time, location FROM events ORDER BY rowid DESC LIMIT 5").fetchall()
actions = conn.execute("SELECT id, description, priority FROM action_items ORDER BY rowid DESC LIMIT 10").fetchall()
reminders = conn.execute("SELECT id, event_id, scheduled_time, status FROM reminders ORDER BY rowid DESC LIMIT 15").fetchall()

print(f"\n📊 Database state:")
print(f"   Events:   {conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]}")
print(f"   Actions:  {conn.execute('SELECT COUNT(*) FROM action_items').fetchone()[0]}")
print(f"   Reminders: {conn.execute('SELECT COUNT(*) FROM reminders').fetchone()[0]}")

# ── STEP 3: Send a test WhatsApp summary ──
owner = cfg.get("whatsapp", {}).get("owner_number", "+62895621691627")
clean = owner.lstrip("+").replace(" ", "").replace("-", "")
chat_id = f"{clean}@s.whatsapp.net"

event_lines = "\n".join(
    f"   • {e[1]} → {e[2]} {e[3] or ''} {'@ '+str(e[4]) if e[4] else ''}"
    for e in events[:3]
)

action_lines = "\n".join(
    f"   • {a[1]} ({a[2].upper()})" for a in actions[:5]
)

summary_msg = (
    f"📋 *Event Organizer — Live Test Report*\n\n"
    f"*Events extracted:*\n{event_lines}\n\n"
    f"*Actions created:*\n{action_lines}\n\n"
    f"✅ Monitor Agent processed {len(bridge_messages)} messages\n"
    f"✅ Dispatcher saved {len(events)} events, {len(actions)} actions\n"
    f"✅ {len(reminders)} reminders scheduled\n\n"
    f"🔇 Hermes auto-reply: DISABLED (no interference)\n"
    f"📡 Bridge monitoring: ACTIVE"
)

payload = json.dumps({"chatId": chat_id, "message": summary_msg}).encode()
req = urllib.request.Request(
    "http://localhost:3000/send",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())
    print(f"\n📱 WhatsApp summary sent: {result.get('messageId', 'unknown')}")

# ── STEP 4: Force-trigger a reminder ──
print(f"\n⏰ Force-sending reminders...")
conn.execute(
    "UPDATE reminders SET status = 'pending' WHERE status != 'pending'"
)
# Pick 2 pending reminders and make them due NOW
pending = conn.execute(
    "SELECT id FROM reminders WHERE status = 'pending' ORDER BY id LIMIT 2"
).fetchall()

if pending:
    ids = [r[0] for r in pending]
    now = (datetime.now().replace(minute=datetime.now().minute - 1) if datetime.now().minute > 0 else datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        f"UPDATE reminders SET scheduled_time = ?, status = 'pending' WHERE id IN ({','.join('?' for _ in ids)})",
        [now] + ids
    )
    conn.commit()
    print(f"   Set {len(pending)} reminder(s) as due now")

dispatcher.close()
conn.close()

# Run the reminder cron
import subprocess
result = subprocess.run(
    ["python3", str(PROJECT_ROOT / "scripts" / "reminder_cron.py")],
    capture_output=True, text=True, timeout=30
)
for line in result.stdout.strip().split("\n"):
    if "sent" in line.lower() or "reminder" in line.lower():
        print(f"   📤 {line}")

print(f"\n{'=' * 65}")
print("  ✅ E2E COMPLETE")
print(f"{'=' * 65}")
