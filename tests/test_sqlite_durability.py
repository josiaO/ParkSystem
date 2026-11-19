"""A SQLite lane authority must not lose committed decisions in a power cut."""

from __future__ import annotations

import sqlite3

from app.db import _sqlite_on_connect, sqlite_synchronous_mode


def test_production_profiles_use_full_sync():
    assert sqlite_synchronous_mode("PRODUCTION") == "FULL"
    assert sqlite_synchronous_mode("production") == "FULL"
    assert sqlite_synchronous_mode("PILOT") == "FULL"


def test_development_keeps_normal_sync():
    assert sqlite_synchronous_mode("DEVELOPMENT") == "NORMAL"


def test_connection_hook_applies_the_profile(tmp_path, monkeypatch):
    from app import db as app_db

    monkeypatch.setattr(app_db, "is_sqlite", lambda *a, **k: True)
    monkeypatch.setattr(app_db.settings, "deployment_profile", "PRODUCTION")
    conn = sqlite3.connect(tmp_path / "lane.db")
    try:
        _sqlite_on_connect(conn, None)
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2      # FULL
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()
