#!/usr/bin/env python3
"""Dispatcher Agent — stores events/actions, schedules reminders, provides CLI."""

import os
import sys
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yaml
import click
from rich.console import Console
from rich.table import Table

# ── paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"

logger   = logging.getLogger("dispatcher")
console  = Console()


def _load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


def _db_path(cfg):
    raw = cfg.get("database", {}).get("path", "storage/events.db")
    return PROJECT_ROOT / raw


# ── Database helper ────────────────────────────────────────────────────
class EventDatabase:
    """Thin wrapper around SQLite for events/actions/reminders."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def _now(self):
        return datetime.now().isoformat(timespec="seconds")

    # -- events --
    def add_event(self, data: dict) -> str:
        eid = data.get("id", f"evt_{uuid.uuid4().hex[:12]}")
        self.conn.execute("""
            INSERT OR REPLACE INTO events
            (id, title, description, event_date, event_time, location,
             source_group, source_sender, source_message, created_at, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
            eid, data["title"], data.get("description"),
            data.get("date"), data.get("time"), data.get("location"),
            data.get("source_group"), data.get("source_sender"),
            data.get("source_message"), self._now(), "upcoming"))
        self.conn.commit()
        return eid

    def get_upcoming_events(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.conn.execute("""
            SELECT * FROM events
            WHERE status='upcoming' AND event_date <= ? AND event_date >= ?
            ORDER BY event_date, event_time""",
            (cutoff, datetime.now().strftime("%Y-%m-%d"))).fetchall()
        return [dict(r) for r in rows]

    def get_all_events(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()
        return [dict(r) for r in rows]

    # -- actions --
    def add_action(self, data: dict) -> str:
        aid = data.get("id", f"act_{uuid.uuid4().hex[:12]}")
        self.conn.execute("""
            INSERT OR REPLACE INTO action_items
            (id, description, deadline, priority, status,
             source_event_id, source_group, source_sender, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (
            aid, data["description"], data.get("deadline"),
            data.get("priority", "medium"), "pending",
            data.get("source_event_id"), data.get("source_group"),
            data.get("source_sender"), self._now()))
        self.conn.commit()
        return aid

    def get_pending_actions(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT * FROM action_items WHERE status='pending'
            ORDER BY priority DESC, deadline""").fetchall()
        return [dict(r) for r in rows]

    def complete_action(self, action_id: str):
        self.conn.execute("""
            UPDATE action_items SET status='completed', completed_at=?
            WHERE id=?""", (self._now(), action_id))
        self.conn.commit()

    # -- reminders --
    def add_reminder(self, data: dict) -> str:
        rid = data.get("id", f"rem_{uuid.uuid4().hex[:12]}")
        self.conn.execute("""
            INSERT OR REPLACE INTO reminders
            (id, event_id, action_id, scheduled_time, message, status)
            VALUES (?,?,?,?,?,?)""", (
            rid, data.get("event_id"), data.get("action_id"),
            data["scheduled_time"], data["message"], "pending"))
        self.conn.commit()
        return rid

    def get_due_reminders(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT * FROM reminders
            WHERE status='pending' AND scheduled_time <= ?
            ORDER BY scheduled_time""", (self._now(),)).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: str):
        self.conn.execute("""
            UPDATE reminders SET status='sent', sent_at=?
            WHERE id=?""", (self._now(), reminder_id))
        self.conn.commit()

    # -- message log --
    def log_message(self, data: dict):
        self.conn.execute("""
            INSERT INTO message_log
            (id, group_name, sender, message_text, extracted_summary,
             relevance_score, processed_at)
            VALUES (?,?,?,?,?,?,?)""", (
            data.get("id", f"msg_{uuid.uuid4().hex[:12]}"),
            data.get("group"), data.get("sender"),
            data.get("message_text"), data.get("summary"),
            data.get("relevance_score"), self._now()))
        self.conn.commit()

    def close(self):
        self.conn.close()


# ── Dispatcher Agent ───────────────────────────────────────────────────
class DispatcherAgent:
    """Receive summaries from Monitor, persist to DB, schedule reminders."""

    def __init__(self, config=None):
        self.cfg = config or _load_config()
        self.db  = EventDatabase(_db_path(self.cfg))
        self.reminder_cfg = self.cfg.get("reminders", {})
        self.owner_number = self.cfg.get("whatsapp", {}).get("owner_number", "")

    def process_summary(self, summary: dict) -> dict:
        """Store events & actions from a monitor summary; schedule reminders."""
        created = {"events": [], "actions": []}

        # log original message
        self.db.log_message({
            "group": summary.get("group"),
            "sender": summary.get("sender"),
            "message_text": summary.get("original_message"),
            "summary": summary.get("summary"),
            "relevance_score": summary.get("relevance_score"),
        })

        # store events
        for ev in summary.get("events", []):
            eid = self.db.add_event({
                "title": ev["title"],
                "date": ev.get("date"),
                "time": ev.get("time"),
                "location": ev.get("location"),
                "source_group": summary.get("group"),
                "source_sender": summary.get("sender"),
                "source_message": summary.get("original_message"),
            })
            created["events"].append(eid)
            self._schedule_event_reminders(eid, ev)

        # store actions
        for act in summary.get("actions", []):
            aid = self.db.add_action({
                "description": act["description"],
                "deadline": act.get("deadline"),
                "priority": act.get("priority", "medium"),
                "source_group": summary.get("group"),
                "source_sender": summary.get("sender"),
            })
            created["actions"].append(aid)
            self._schedule_action_reminders(aid, act)

        logger.info("stored %d events, %d actions", len(created["events"]), len(created["actions"]))
        return created

    def _schedule_event_reminders(self, event_id: str, event: dict):
        """Create reminder entries based on escalation_hours config."""
        date_str = event.get("date")
        if not date_str:
            return
        try:
            event_dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        hours = self.reminder_cfg.get("escalation_hours", [48, 24, 6, 2])
        title = event.get("title", "Event")
        time_str = event.get("time", "")
        loc      = event.get("location", "")

        for h in hours:
            sched = event_dt - timedelta(hours=h)
            if sched < datetime.now():
                continue
            msg = f"⏰ Reminder: {title}"
            if time_str:
                msg += f" at {time_str}"
            if loc:
                msg += f" ({loc})"
            msg += f"\n📅 {h}h from now"
            self.db.add_reminder({
                "event_id": event_id,
                "scheduled_time": sched.isoformat(timespec="seconds"),
                "message": msg,
            })

    def _schedule_action_reminders(self, action_id: str, action: dict):
        """Schedule reminders for action deadlines."""
        deadline_str = action.get("deadline")
        if not deadline_str:
            return
        try:
            dl = datetime.fromisoformat(deadline_str)
        except ValueError:
            return

        hours = self.reminder_cfg.get("escalation_hours", [48, 24, 6, 2])
        desc = action.get("description", "Task")

        for h in hours:
            sched = dl - timedelta(hours=h)
            if sched < datetime.now():
                continue
            msg = f"📌 Action reminder: {desc}\n⏳ Deadline in {h}h"
            self.db.add_reminder({
                "action_id": action_id,
                "scheduled_time": sched.isoformat(timespec="seconds"),
                "message": msg,
            })

    def get_summary(self) -> str:
        """Formatted text summary of upcoming events and pending actions."""
        events  = self.db.get_upcoming_events(14)
        actions = self.db.get_pending_actions()

        lines = ["📋 *Event Organizer Summary*", ""]

        if events:
            lines.append("📅 *Upcoming Events:*")
            for e in events:
                line = f"  • {e['title']}"
                if e.get("event_date"):
                    line += f" — {e['event_date']}"
                if e.get("event_time"):
                    line += f" {e['event_time']}"
                if e.get("location"):
                    line += f" @ {e['location']}"
                lines.append(line)
        else:
            lines.append("📅 No upcoming events in the next 14 days.")

        lines.append("")
        if actions:
            lines.append("✅ *Pending Actions:*")
            for a in actions:
                line = f"  • [{a['priority'].upper()}] {a['description']}"
                if a.get("deadline"):
                    line += f" (due: {a['deadline']})"
                lines.append(f"{line}  `id: {a['id']}`")
        else:
            lines.append("✅ No pending actions.")

        return "\n".join(lines)

    def close(self):
        self.db.close()


# ── CLI ────────────────────────────────────────────────────────────────
@click.group()
def cli():
    """Event Organizer Dispatcher CLI."""
    logging.basicConfig(level=logging.INFO)


@cli.command()
@click.option("--title", required=True, help="Event title")
@click.option("--date", "event_date", required=True, help="YYYY-MM-DD")
@click.option("--time", "event_time", default="", help="HH:MM")
@click.option("--location", default="", help="Location")
@click.option("--description", default="", help="Description")
def add_event(title, event_date, event_time, location, description):
    """Manually add an event."""
    disp = DispatcherAgent()
    eid = disp.db.add_event({
        "title": title, "date": event_date, "time": event_time,
        "location": location, "description": description,
    })
    disp._schedule_event_reminders(eid, {"date": event_date, "time": event_time,
                                          "location": location, "title": title})
    disp.close()
    console.print(f"[green]✓ Event created:[/green] {eid}")


@cli.command()
@click.option("--days", default=7, help="Look ahead N days")
def list_events(days):
    """List upcoming events."""
    disp = DispatcherAgent()
    events = disp.db.get_upcoming_events(days)
    disp.close()

    if not events:
        console.print(f"[yellow]No events in the next {days} days.[/yellow]")
        return

    table = Table(title=f"Upcoming Events (next {days} days)")
    table.add_column("Date", style="cyan")
    table.add_column("Time", style="green")
    table.add_column("Title")
    table.add_column("Location")
    for e in events:
        table.add_row(
            e.get("event_date") or "—",
            e.get("event_time") or "—",
            e["title"],
            e.get("location") or "—",
        )
    console.print(table)


@cli.command()
@click.option("--status", "filter_status", default="pending", help="pending|completed|all")
def list_actions(filter_status):
    """List action items."""
    disp = DispatcherAgent()
    if filter_status == "all":
        rows = disp.db.conn.execute("SELECT * FROM action_items ORDER BY created_at DESC").fetchall()
    elif filter_status == "completed":
        rows = disp.db.conn.execute("SELECT * FROM action_items WHERE status='completed' ORDER BY completed_at DESC").fetchall()
    else:
        rows = disp.db.conn.execute("SELECT * FROM action_items WHERE status='pending' ORDER BY priority DESC, deadline").fetchall()
    disp.close()

    actions = [dict(r) for r in rows]
    if not actions:
        console.print("[yellow]No action items found.[/yellow]")
        return

    table = Table(title=f"Action Items ({filter_status})")
    table.add_column("ID", style="dim")
    table.add_column("Priority", style="magenta")
    table.add_column("Description")
    table.add_column("Deadline")
    table.add_column("Status")
    for a in actions:
        table.add_row(
            a["id"],
            a.get("priority", "medium").upper(),
            a["description"],
            a.get("deadline") or "—",
            a["status"],
        )
    console.print(table)


@cli.command()
@click.argument("action_id")
def complete(action_id):
    """Mark an action as completed."""
    disp = DispatcherAgent()
    disp.db.complete_action(action_id)
    disp.close()
    console.print(f"[green]✓ Action completed:[/green] {action_id}")


@cli.command()
def summary():
    """Print full summary of events and actions."""
    disp = DispatcherAgent()
    console.print(disp.get_summary())
    disp.close()


@cli.command()
@click.argument("json_file", required=False)
def process_queue(json_file=None):
    """Process queued summaries from monitor agent."""
    queue_dir = PROJECT_ROOT / "storage" / "queue"
    if json_file:
        files = [Path(json_file)]
    else:
        files = sorted(queue_dir.glob("*.json"))

    if not files:
        console.print("[yellow]No queued messages.[/yellow]")
        return

    disp = DispatcherAgent()
    for fpath in files:
        try:
            with open(fpath) as f:
                summary = json.load(f)
            created = disp.process_summary(summary)
            console.print(f"[green]✓ Processed:[/green] {fpath.name} → {len(created['events'])} events, {len(created['actions'])} actions")
            fpath.unlink()  # remove after processing
        except Exception as exc:
            console.print(f"[red]✗ Failed {fpath.name}: {exc}[/red]")
    disp.close()


if __name__ == "__main__":
    cli()
