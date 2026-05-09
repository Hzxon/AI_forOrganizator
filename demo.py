#!/usr/bin/env python3
"""Full end-to-end demo of the Event Organizer system."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.monitor import MonitorAgent
from agents.dispatcher import DispatcherAgent


def main():
    print("=" * 60)
    print("  Event Organizer — End-to-End Demo")
    print("=" * 60)

    monitor    = MonitorAgent()
    dispatcher = DispatcherAgent()

    # Simulate WhatsApp messages from different groups
    messages = [
        monitor.simulate_whatsapp_message(
            "Meeting tomorrow at 3pm in Room 302 — discuss Q2 roadmap",
            "Team Updates", "Alice"),
        monitor.simulate_whatsapp_message(
            "Don't forget to submit the proposal by Friday",
            "Project Coordination", "Bob"),
        monitor.simulate_whatsapp_message(
            "Team party next Saturday at 7pm at Grand Hotel — everyone must prepare a gift",
            "Event Planning Committee", "Carol"),
        monitor.simulate_whatsapp_message(
            "Just a casual chat, nothing important here 😄",
            "Random", "Eve"),
        monitor.simulate_whatsapp_message(
            "URGENT: deadline for budget report is tomorrow at 5pm — must submit to finance ASAP",
            "Project Coordination", "Frank"),
    ]

    print("\n📡 Processing WhatsApp messages...\n")

    for msg in messages:
        summary = monitor.process_message(msg)
        if summary is None:
            print(f"  ⏭️  Skipped (empty): {msg['text'][:40]}")
            continue

        score = summary["relevance_score"]
        if not summary.get("should_forward"):
            print(f"  ⏭️  Skipped (score={score:.2f}): {msg['text'][:40]}")
            continue

        # Forward to dispatcher
        monitor.forward_to_dispatcher(summary)
        created = dispatcher.process_summary(summary)
        status = f"✓ {len(created['events'])} events, {len(created['actions'])} actions stored"
        print(f"  ✅ Forwarded (score={score:.2f}): {msg['text'][:50]}...")
        print(f"     → {status}")

    # Print summary
    print("\n" + "=" * 60)
    print(dispatcher.get_summary())
    print("=" * 60)

    # Check reminders
    reminders = dispatcher.db.get_due_reminders()
    print(f"\n⏰ Scheduled reminders: {len(reminders)}")
    for r in reminders[:5]:
        print(f"   [{r['scheduled_time'][:16]}] {r['message'][:60]}...")

    dispatcher.close()
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
