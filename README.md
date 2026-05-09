# 🎯 Event Organizer — Agentic AI WhatsApp Monitor

> **A Hermes-powered automation tool** — turning group chaos into structured deadlines, memory, and action.

A multi-agent AI system that monitors WhatsApp groups, extracts events/action items automatically, and sends you smart reminders — designed for personal productivity and deadline tracking.

[![Hermes-powered](https://img.shields.io/badge/Hermes%20Agent-52489C?logo=hermes&logoColor=white)](https://hermes-agent.nousresearch.com) [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

## 🖥️ Terminal UI Preview (Your Aesthetic)

```bash
$ hermes run --project AI_forOrganizator --task "morning-summary"
[17:00] ✅ Connected to WhatsApp gateway (http://localhost:3000)
[17:00] 📥 Ingested 4 new messages from monitored groups
[17:00] 🧠 Extracted 2 events, 1 action item, 0 deadlines
[17:00] 🗂️ Stored in SQLite: storage/events.db (v3.2.1)
[17:00] 📣 Sending morning summary via WhatsApp...
[17:00] ✅ Sent: "Good morning! 🌞\n• ML Assignment due: 12 May 2026 (11 days left)\n• Team Sync tomorrow @ 15:00 in Room 302\n• Action: Prepare presentation slides"
```

---

## 🏗️ Architecture

Your system runs as a tight Hermes-integrated stack:

```
WhatsApp Groups/DM → Hermes HTTP Gateway → Monitor Agent → Dispatcher Agent → SQLite DB
                                                                    ↓
                                                          Reminder Cron Job → WhatsApp DM
                                                                    ↓
                                                            You (Student Dashboard)
```

✅ **Fully visualized**: Open [`architecture.html`](./architecture.html) for an interactive SVG diagram.

### Agents

| Agent | Role | File |
|-------|------|------|
| **Monitor** | Listens to WhatsApp messages, extracts events/actions/dates using LLM-powered NLP | `agents/monitor.py` |
| **Dispatcher** | Stores extracted data in DB, provides CLI, and powers your student dashboard queries | `agents/dispatcher.py` |
| **Reminder** | Cron-triggered script that sends due reminders via Hermes WhatsApp gateway | `scripts/reminder_cron.py` |

---

## 🌍 For Public Users

Want to use this for your own WhatsApp groups? Here's how:

### 1. Clone & Install
```bash
git clone https://github.com/Hzxon/AI_forOrganizator.git
cd AI_forOrganizator
pip install -r requirements.txt
```

### 2. Configure Securely
**A. Hermes WhatsApp Bridge** (`~/.hermes/.env`):  
Create this file in your home directory (never commit it!):
```ini
WHATSAPP_MODE=bot
WHATSAPP_ALLOWED_USERS=+1234567890,+0987654321  # Your trusted numbers
WHATSAPP_OWNER_NUMBER=+1234567890                 # Your number
```

**B. Project Config** (`config/settings.yaml`):  
Copy the example and edit:
```bash
cp config/settings.yaml.example config/settings.yaml
nano config/settings.yaml  # Replace placeholder number + groups
```

### 3. Start Dependencies
```bash
# Start WhatsApp bridge (uses ~/.hermes/.env)
bash ~/.hermes/scripts/start-whatsapp-bridge.sh

# Initialize database
python3 scripts/init_db.py
```

### 4. Schedule Reminders
```bash
# Daily reminders at 7 PM
hermes cron create "0 19 * * *" \
  --name "event-organizer-reminders" \
  --prompt "cd $(pwd) && python3 scripts/reminder_cron.py"

# Morning summary at 8 AM
hermes cron create "0 8 * * *" \
  --name "event-organizer-morning" \
  --prompt "cd $(pwd) && python3 agents/dispatcher.py summary"
```

### 5. Verify
```bash
python3 scripts/test_extraction.py "Submit report by Friday"
python3 agents/dispatcher.py list-events --days 7
```

> 🔒 **Security Note**: Never commit `.env` files or real phone numbers to Git. Your `~/.hermes/.env` is automatically ignored.

---

## 📋 CLI Commands

```bash
# Add event manually
python3 agents/dispatcher.py add-event \
  --title "Team Sync" --date "2026-05-15" --time "15:00" --location "Room 302"

# List upcoming events (next 7 days)
python3 agents/dispatcher.py list-events --days 7

# List pending actions
python3 agents/dispatcher.py list-actions

# Complete an action
python3 agents/dispatcher.py complete act_xxxxx

# Full summary (for your student dashboard)
python3 agents/dispatcher.py summary

# Process queued messages from monitor
python3 agents/dispatcher.py process-queue
```

---

## 🔍 Extraction Capabilities

### Dates
- ✅ `tomorrow`, `today`, `next Monday`, `in 3 days`
- ✅ `by Friday`, `this Thursday`
- ✅ `May 20th`, `on June 5`
- ✅ ISO format: `2026-05-15` → **ML Deadline: 2026-05-12**

### Times
- ✅ `3pm`, `9am`, `14:00`, `09:30`

### Locations
- ✅ `Room 302`, `Conference Room A`, `Building B`
- ✅ `at Grand Hotel`, `in the main hall`

### Events
- Keywords: meeting, deadline, event, party, conference, workshop, seminar, presentation, interview, **exam**, **submission**, **launch**, **assignment**

### Actions
- Keywords: need to, must, remember to, don't forget, task, action item, to do, prepare, **submit**, **complete**, **review**
- Priority detection: URGENT, ASAP, important, critical → `high`

### Relevance Scoring
Messages are scored 0.0–1.0 based on keyword matches and date presence. Only messages above the confidence threshold (default 0.7) or with extracted events/actions are forwarded.

---

## ⏰ Reminder System

Reminders are scheduled at configurable intervals before each event/deadline:
- **48 hours** before
- **24 hours** before
- **6 hours** before
- **2 hours** before

Quiet hours (default 22:00–07:00) prevent late-night notifications.

### Schedule Cron Jobs

```bash
# Daily reminder check at 7 PM
hermes cron create "0 19 * * *" \
  --name "event-organizer-reminders" \
  --prompt "cd /Users/hazron/1-Projects/AI_forOrganizator && python3 scripts/reminder_cron.py"

# Morning summary at 8 AM
hermes cron create "0 8 * * *" \
  --name "event-organizer-morning" \
  --prompt "cd /Users/hazron/1-Projects/AI_forOrganizator && python3 agents/dispatcher.py summary"
```

---

## 📱 WhatsApp Integration

The reminder system prepares messages and logs them to `logs/sent_reminders.log`. To enable actual WhatsApp sending, edit `scripts/reminder_cron.py` and replace the `send_whatsapp_message()` function body with your Hermes gateway call:

```python
# Option 1: Hermes CLI (recommended)
os.system(f'hermes send --platform whatsapp --to "{phone}" "{message}"')

# Option 2: HTTP API (direct)
import requests
requests.post("http://localhost:3000/send", json={"to": phone, "text": message})
```

> 💡 **Pro tip**: Your Hermes WhatsApp bridge is already running (`PID 83540`) and connected — just point to `http://localhost:3000`.

---

## 📁 Project Structure

```
AI_forOrganizator/
├── agents/
│   ├── __init__.py
│   ├── monitor.py          # Monitor Agent — message extraction
│   └── dispatcher.py       # Dispatcher Agent — storage + CLI + student dashboard interface
├── config/
│   └── settings.yaml       # Configuration
├── scripts/
│   ├── init_db.py          # Database initialization
│   ├── reminder_cron.py    # Reminder cron job (Hermes-integrated)
│   └── test_extraction.py  # Extraction test suite
├── storage/
│   ├── events.db           # SQLite database
│   └── queue/              # Message queue (JSON files)
├── logs/
│   ├── organizer.log       # Application log
│   └── sent_reminders.log  # Sent reminders log
├── demo.py                 # End-to-end demo
├── architecture.html       # Interactive architecture diagram (open in browser)
└── README.md               # This file
```

---

## 🛠️ Troubleshooting

### Messages not extracted
Lower the confidence threshold in `config/settings.yaml`:
```yaml
extraction:
  confidence_threshold: 0.5  # default is 0.7
```

### Reminders not sending
1. Check cron status: `hermes cron list`
2. Verify owner number in settings
3. Run manually: `python3 scripts/reminder_cron.py`
4. Check logs: `cat logs/organizer.log`
5. Confirm bridge is up: `curl http://localhost:3000/messages | jq .`

### Reset database
```bash
rm storage/events.db
python3 scripts/init_db.py
```

---

## 🌐 Why This Matters

This isn't just another WhatsApp bot — it's a **personal deadline-tracking system** that turns group chaos into structured reminders and action items.

- ✅ **Deadline-aware**: Automatically detects events/deadlines from group chats using NLP
- ✅ **Agentic, not generative**: Turns chat into *action* — not just summarizing, but scheduling, reminding, and organizing
- ✅ **Hermes-native**: Uses your existing infrastructure — no new APIs, no vendor lock-in

> 🎯 **Turn chaos into clarity — one deadline, one reminder, one organized mind at a time.**

---

## 📜 License

Distributed under the MIT License. See [`LICENSE`](./LICENSE) for more information.

---

## 🙌 Contributing

Contributions welcome! See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for guidelines.

---

## 📬 Contact

Built by [@Hzxon](https://github.com/Hzxon) • Part of the [Hermes Agent ecosystem](https://hermes-agent.nousresearch.com)