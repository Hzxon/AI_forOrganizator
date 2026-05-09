#!/usr/bin/env python3
"""Monitor Agent — watches WhatsApp messages, extracts events/actions, forwards to dispatcher."""

import os
import re
import json
import uuid
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

import dateparser
import yaml

# ── paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"

logger = logging.getLogger("monitor")


def _load_config():
    """Load settings.yaml; return dict."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


# ── Monitor Agent ──────────────────────────────────────────────────────
class MonitorAgent:
    """Extract structured event / action data from WhatsApp messages."""

    def __init__(self, config=None):
        self.cfg = config or _load_config()
        ext = self.cfg.get("extraction", {})
        self.timezone      = ext.get("timezone", "Asia/Jakarta")
        self.conf_threshold = ext.get("confidence_threshold", 0.7)
        self.event_kw      = [w.lower() for w in ext.get("event_keywords", [])]
        self.action_kw     = [w.lower() for w in ext.get("action_keywords", [])]
        self.location_kw   = [w.lower() for w in ext.get("location_keywords", [])]

    # ── public API ─────────────────────────────────────────────────────
    def process_message(self, message: dict) -> Optional[dict]:
        """Main entry point.
        *message* keys: text, group (optional), sender (optional), timestamp (optional)
        Returns structured summary dict or None if irrelevant.
        """
        text  = message.get("text", "").strip()
        if not text:
            return None

        relevance = self._calculate_relevance(text)
        events    = self._extract_events(text)
        actions   = self._extract_actions(text)
        summary   = self._summarize(text, events, actions)

        result = {
            "original_message": text,
            "group":            message.get("group", ""),
            "sender":           message.get("sender", ""),
            "timestamp":        message.get("timestamp", datetime.now().isoformat()),
            "relevance_score":  relevance,
            "summary":          summary,
            "events":           events,
            "actions":          actions,
            "should_forward":   relevance >= self.conf_threshold or events or actions,
        }

        # log every processed message
        logger.info("processed msg [score=%.2f forward=%s] %s",
                     relevance, result["should_forward"], text[:80])
        return result

    def simulate_whatsapp_message(self, text: str, group: str = "", sender: str = "") -> dict:
        """Helper to build a message dict for testing."""
        return {"text": text, "group": group, "sender": sender,
                "timestamp": datetime.now().isoformat()}

    def forward_to_dispatcher(self, summary: dict):
        """Persist summary to a JSON queue file for the dispatcher to pick up."""
        queue_dir = PROJECT_ROOT / "storage" / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        path = queue_dir / f"{uuid.uuid4().hex}.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info("forwarded summary → %s", path)
        return str(path)

    # ── extraction helpers ─────────────────────────────────────────────
    def _extract_events(self, text: str) -> List[dict]:
        lower = text.lower()
        hits = [kw for kw in self.event_kw if kw in lower]
        if not hits:
            return []

        dt_info = self._extract_datetime(text)
        loc     = self._extract_location(text)

        # build title from first sentence or keyword context
        title = self._build_event_title(text, hits)

        return [{
            "title":      title,
            "date":       dt_info.get("date"),
            "time":       dt_info.get("time"),
            "location":   loc,
            "confidence": min(1.0, 0.5 + len(hits) * 0.15 + (0.2 if dt_info.get("date") else 0)),
            "keywords":   hits,
        }]

    def _extract_actions(self, text: str) -> List[dict]:
        lower = text.lower()
        hits = [kw for kw in self.action_kw if kw in lower]
        if not hits:
            return []

        # extract the clause after the action keyword
        descriptions: List[str] = []
        for kw in hits:
            idx = lower.find(kw)
            if idx != -1:
                # grab up to 120 chars after the keyword
                chunk = text[idx:idx + 120].strip()
                # trim at punctuation
                chunk = re.split(r'[.;]', chunk)[0].strip()
                if chunk:
                    descriptions.append(chunk)

        if not descriptions:
            descriptions = [text[:120]]

        dt_info = self._extract_datetime(text)
        deadline = dt_info.get("date")
        if dt_info.get("time") and deadline:
            deadline += f" {dt_info['time']}"

        urgency_kw = ["urgent", "asap", "important", "immediately", "critical"]
        priority = "high" if any(k in lower for k in urgency_kw) else "medium"

        return [{
            "description": desc,
            "deadline":    deadline,
            "priority":    priority,
            "confidence":  min(1.0, 0.5 + len(hits) * 0.15),
            "keywords":    hits,
        } for desc in descriptions]

    def _extract_datetime(self, text: str) -> dict:
        """Return {'date': str | None, 'time': str | None}."""
        result: dict = {"date": None, "time": None}

        # ── time regex ──
        time_pat = re.compile(
            r'(\d{1,2})[:\.](\d{2})\s*(am|pm)?', re.IGNORECASE)
        m = time_pat.search(text)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            ampm = (m.group(3) or "").lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            result["time"] = f"{hour:02d}:{minute:02d}"

        # also catch "3pm" / "9am" style
        if not result["time"]:
            simple = re.search(r'(\d{1,2})\s*(am|pm)', text, re.IGNORECASE)
            if simple:
                hour = int(simple.group(1))
                ampm = simple.group(2).lower()
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
                result["time"] = f"{hour:02d}:00"

        # ── date via dateparser ──
        settings = {"PREFER_DATES_FROM": "future", "TIMEZONE": self.timezone}
        parsed = dateparser.parse(text, settings=settings)
        if parsed and parsed.date() != datetime.now().date():
            result["date"] = parsed.strftime("%Y-%m-%d")

        # fallback: try extracting month-day patterns like "May 20th", "on June 5"
        if not result["date"]:
            month_day = re.search(
                r'(?:on\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?',
                text, re.IGNORECASE)
            if month_day:
                chunk = f"{month_day.group(1)} {month_day.group(2)}"
                parsed_chunk = dateparser.parse(chunk, settings=settings)
                if parsed_chunk:
                    result["date"] = parsed_chunk.strftime("%Y-%m-%d")

        # fallback: check "tomorrow", "next monday", "in X days"
        if not result["date"]:
            lower = text.lower()
            today = datetime.now()
            if "tomorrow" in lower:
                result["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
            elif "today" in lower:
                result["date"] = today.strftime("%Y-%m-%d")
            else:
                m_days = re.search(r'in\s+(\d+)\s+day', lower)
                if m_days:
                    result["date"] = (today + timedelta(days=int(m_days.group(1)))).strftime("%Y-%m-%d")

            # weekday names
            weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
            for i, wd in enumerate(weekdays):
                if (f"next {wd}" in lower or f"by {wd}" in lower or
                    (f"this {wd}" in lower and today.weekday() < i)):
                    days_ahead = (i - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    if f"next {wd}" in lower:
                        days_ahead += 7 if days_ahead <= 0 else 0
                    result["date"] = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                    break

        return result

    def _extract_location(self, text: str) -> Optional[str]:
        lower = text.lower()
        # Try specific venue keywords first (room, building, venue) — higher confidence
        specific = re.compile(
            r'(?:room|building|venue|hall|conference\s+room)\s*([A-Z0-9][\w\s&\-\.]{1,40})',
            re.IGNORECASE)
        m = specific.search(text)
        if m:
            loc = m.group(0).strip().rstrip(".,;:!")  # keep the full "Room 302" / "Conference Room A"
            return loc

        # Fall back to preposition-based extraction, but skip time-prefixed matches
        loc_pat = re.compile(
            r'(?:at|in|place|@)\s+([A-Z][\w\s&\-\.]{2,40})',
            re.IGNORECASE)
        for m in loc_pat.finditer(text):
            candidate = m.group(1).strip().rstrip(".,;:!")
            # skip if it starts with a time pattern like "3pm", "7pm", "15:00"
            if re.match(r'\d{1,2}\s*(am|pm)|\d{1,2}:\d{2}', candidate, re.IGNORECASE):
                continue
            return candidate
        return None

    def _calculate_relevance(self, text: str) -> float:
        lower = text.lower()
        score = 0.0
        score += sum(0.25 for kw in self.event_kw  if kw in lower)
        score += sum(0.25 for kw in self.action_kw if kw in lower)
        # date/time mention boosts relevance
        if self._extract_datetime(text)["date"]:
            score += 0.3
        # short messages (< 10 chars) are rarely important
        if len(text) < 10:
            score *= 0.3
        return min(1.0, round(score, 2))

    def _build_event_title(self, text: str, keywords: List[str]) -> str:
        # use first sentence, capitalise
        sentence = re.split(r'[.;\n]', text)[0].strip()
        if len(sentence) > 80:
            sentence = sentence[:77] + "..."
        return sentence if sentence else keywords[0].title()

    def _summarize(self, text: str, events: list, actions: list) -> str:
        parts = []
        if events:
            ev = events[0]
            parts.append(f"📅 {ev['title']}")
            if ev.get("date"):
                parts.append(f"   Date: {ev['date']}")
            if ev.get("time"):
                parts.append(f"   Time: {ev['time']}")
            if ev.get("location"):
                parts.append(f"   Location: {ev['location']}")
        if actions:
            for act in actions:
                parts.append(f"✅ {act['description']}")
                if act.get("deadline"):
                    parts.append(f"   Deadline: {act['deadline']}")
        if not parts:
            parts.append(text[:120])
        return "\n".join(parts)


# ── quick CLI test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    agent = MonitorAgent()
    msg_text = " ".join(sys.argv[1:]) or "Meeting tomorrow at 3pm in Room 302 — don't forget to prepare slides"
    msg = agent.simulate_whatsapp_message(msg_text, group="Team Updates", sender="Alice")
    result = agent.process_message(msg)
    print(json.dumps(result, indent=2, default=str))
