#!/usr/bin/env python3
"""Test extraction — run MonitorAgent on sample messages and inspect results."""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.monitor import MonitorAgent

TEST_MESSAGES = [
    {
        "text": "Meeting tomorrow at 3pm in Room 302",
        "group": "Team Updates",
        "sender": "Alice",
    },
    {
        "text": "Don't forget to submit the proposal by Friday",
        "group": "Project Coordination",
        "sender": "Bob",
    },
    {
        "text": "Team party next Saturday at 7pm at Grand Hotel — everyone must prepare a gift",
        "group": "Event Planning Committee",
        "sender": "Carol",
    },
    {
        "text": "We need to prepare slides for the presentation on May 20th at 2pm in Conference Room A",
        "group": "Team Updates",
        "sender": "Dave",
    },
    {
        "text": "Just a casual chat, nothing important here 😄",
        "group": "Random",
        "sender": "Eve",
    },
    {
        "text": "URGENT: deadline for budget report is tomorrow at 5pm — must submit to finance ASAP",
        "group": "Project Coordination",
        "sender": "Frank",
    },
]


def run_test(text: str, group: str = "Test", sender: str = "Tester"):
    """Run extraction on a single message and pretty-print results."""
    agent = MonitorAgent()
    msg   = agent.simulate_whatsapp_message(text, group, sender)
    result = agent.process_message(msg)

    if result is None:
        print("  → No result (empty message)")
        return

    print(f"\n{'─' * 60}")
    print(f"  Message : {text}")
    print(f"  Group   : {group}  |  Sender: {sender}")
    print(f"  Score   : {result['relevance_score']:.2f}  |  Forward: {result['should_forward']}")
    print(f"{'─' * 60}")

    if result["events"]:
        print("  📅 Events:")
        for ev in result["events"]:
            print(f"     Title    : {ev['title']}")
            print(f"     Date     : {ev.get('date', '—')}")
            print(f"     Time     : {ev.get('time', '—')}")
            print(f"     Location : {ev.get('location', '—')}")
            print(f"     Confidence: {ev.get('confidence', 0):.2f}")
    else:
        print("  📅 No events extracted")

    if result["actions"]:
        print("  ✅ Actions:")
        for act in result["actions"]:
            print(f"     Description: {act['description']}")
            print(f"     Deadline   : {act.get('deadline', '—')}")
            print(f"     Priority   : {act.get('priority', '—')}")
            print(f"     Confidence : {act.get('confidence', 0):.2f}")
    else:
        print("  ✅ No actions extracted")

    print(f"\n  Summary:\n{result['summary']}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test Monitor Agent extraction")
    parser.add_argument("message", nargs="?", help="Custom message to test")
    parser.add_argument("--group", default="Test", help="Group name")
    parser.add_argument("--sender", default="Tester", help="Sender name")
    parser.add_argument("--suite", action="store_true", help="Run full test suite")
    args = parser.parse_args()

    if args.message:
        run_test(args.message, args.group, args.sender)
    elif args.suite or not sys.argv[1:]:
        print("=" * 60)
        print("  Event Organizer — Extraction Test Suite")
        print("=" * 60)
        for t in TEST_MESSAGES:
            run_test(t["text"], t.get("group", "Test"), t.get("sender", "Tester"))

        print("=" * 60)
        print(f"  Tested {len(TEST_MESSAGES)} messages")
        print("=" * 60)
    else:
        run_test(" ".join(sys.argv[1:]))


if __name__ == "__main__":
    main()
