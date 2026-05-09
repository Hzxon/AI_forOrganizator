# 🎯 Event Organizer — Agentic AI WhatsApp Monitor

A multi-agent AI system that monitors WhatsApp groups, extracts events/action items automatically, and sends you smart reminders.

## Architecture

```
WhatsApp Groups/DM → Hermes Gateway → Monitor Agent → Dispatcher Agent → SQLite DB
                                                                    ↓
                                                          Reminder Cron Job → WhatsApp DM
```

### Agents

| Agent | Role | File |
|-------|------|------|
| **Monitor** | Listens to WhatsApp messages, extracts events/actions/dates/locations | `agents/monitor.py` |
| **Dispatcher** | Stores extracted data in DB, schedules reminders, provides CLI | `agents/dispatcher.py` |
| **Reminder** | Cron-triggered script that sends due reminders via WhatsApp | `scripts/reminder_cron.py` |

## Quick Start

### 1. Configure

Edit `config/settings.yaml`:
```yaml
whatsapp:
  owner_number: "+6281234567890"  # ← YOUR WhatsApp number
  monitored_groups:
    - "Event Planning Committee"
    - "Team Updates"
```

### 2. Initialize Database

```bash
python3 scripts/init_db.py
```

### 3. Test Extraction

```bash
# Single message
python3 scripts/test_extraction.py "Meeting tomorrow at 3pm in Room 302"

# Full test suite
python3 scripts/test_extraction.py --suite
```

### 4. Run Demo

```bash
python3 demo.py
```

## CLI Commands

```bash
# Add event manually
python3 agents/dispatcher.py add-event \
  --title "Team Sync" --date "2026-05-15" --time "15:00" --location "Room 302"

# List upcoming events
python3 agents/dispatcher.py list-events --days 7

# List pending actions
python3 agents/dispatcher.py list-actions

# Complete an action
python3 agents/dispatcher.py complete act_xxxxx

# Full summary
python3 agents/dispatcher.py summary

# Process queued messages from monitor
python3 agents/dispatcher.py process-queue
```

## Extraction Capabilities

### Dates
- ✅ `tomorrow`, `today`, `next Monday`, `in 3 days`
- ✅ `by Friday`, `this Thursday`
- ✅ `May 20th`, `on June 5`
- ✅ ISO format: `2026-05-15`

### Times
- ✅ `3pm`, `9am`, `14:00`, `09:30`

### Locations
- ✅ `Room 302`, `Conference Room A`, `Building B`
- ✅ `at Grand Hotel`, `in the main hall`

### Events
- Keywords: meeting, deadline, event, party, conference, workshop, seminar, presentation, interview, exam, submission, launch

### Actions
- Keywords: need to, must, remember to, don't forget, task, action item, to do, prepare, submit, complete
- Priority detection: URGENT, ASAP, important, critical → `high`

### Relevance Scoring
Messages are scored 0.0–1.0 based on keyword matches and date presence. Only messages above the confidence threshold (default 0.7) or with extracted events/actions are forwarded.

## Reminder System

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

## WhatsApp Integration

The reminder system prepares messages and logs them to `logs/sent_reminders.log`. To enable actual WhatsApp sending, edit `scripts/reminder_cron.py` and replace the `send_whatsapp_message()` function body with your Hermes gateway call:

```python
# Option 1: Hermes CLI
os.system(f'hermes send --platform whatsapp --to "{phone}" "{message}"')

# Option 2: HTTP API
import requests
requests.post("http://localhost:3000/send", json={"to": phone, "text": message})
```

## Project Structure

```
AI_forOrganizator/
├── agents/
│   ├── __init__.py
│   ├── monitor.py          # Monitor Agent — message extraction
│   └── dispatcher.py       # Dispatcher Agent — storage + CLI
├── config/
│   └── settings.yaml       # Configuration
├── scripts/
│   ├── init_db.py          # Database initialization
│   ├── reminder_cron.py    # Reminder cron job
│   └── test_extraction.py  # Extraction test suite
├── storage/
│   ├── events.db           # SQLite database
│   └── queue/              # Message queue (JSON files)
├── logs/
│   ├── organizer.log       # Application log
│   └── sent_reminders.log  # Sent reminders log
├── demo.py                 # End-to-end demo
└── README.md               # This file
```

## Troubleshooting

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

### Reset database
```bash
rm storage/events.db
python3 scripts/init_db.py
```
