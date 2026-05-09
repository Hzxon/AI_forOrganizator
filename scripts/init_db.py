#!/usr/bin/env python3
"""Database initialization script for the Event Organizer system.

Creates the SQLite database and required tables based on configuration
loaded from config/settings.yaml.
"""

import os
import sqlite3
import sys

import yaml


def load_config():
    """Load configuration from config/settings.yaml relative to the project root."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    config_path = os.path.join(project_root, "config", "settings.yaml")

    if not os.path.exists(config_path):
        print(f"Warning: Config file not found at {config_path}, using defaults.")
        return {}

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_db_path(config):
    """Resolve the database path from config or use the default."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Allow config to override the database path
    db_config = config.get("database", {})
    db_relative_path = db_config.get("path", "storage/events.db")

    db_path = os.path.join(project_root, db_relative_path)
    db_dir = os.path.dirname(db_path)

    os.makedirs(db_dir, exist_ok=True)
    return db_path


def create_tables(conn):
    """Create all required tables if they don't exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT,
            event_time TEXT,
            location TEXT,
            source_group TEXT,
            source_sender TEXT,
            source_message TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming'
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_items (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            deadline TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            source_event_id TEXT,
            source_group TEXT,
            source_sender TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            event_id TEXT,
            action_id TEXT,
            scheduled_time TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            FOREIGN KEY (event_id) REFERENCES events(id),
            FOREIGN KEY (action_id) REFERENCES action_items(id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_log (
            id TEXT PRIMARY KEY,
            group_name TEXT,
            sender TEXT,
            message_text TEXT NOT NULL,
            extracted_summary TEXT,
            relevance_score REAL,
            processed_at TEXT NOT NULL
        );
    """)

    conn.commit()


def get_table_counts(conn):
    """Return a dict mapping table names to their row counts."""
    cursor = conn.cursor()
    tables = ["events", "action_items", "reminders", "message_log"]
    counts = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        counts[table] = cursor.fetchone()[0]
    return counts


def main():
    """Initialize the database and report results."""
    config = load_config()
    db_path = get_db_path(config)

    print(f"Initializing database at: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        create_tables(conn)
        counts = get_table_counts(conn)

        print("Database initialized successfully!")
        print(f"Database location: {db_path}")
        print("Table counts:")
        for table, count in counts.items():
            print(f"  - {table}: {count} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
