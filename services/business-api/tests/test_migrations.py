from __future__ import annotations

import os
import sqlite3
import subprocess
import sys


def test_initial_migration_creates_booking_and_payment_tables(tmp_path):
    database_path = tmp_path / "migrated.sqlite3"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "bookings",
        "booking_status_events",
        "payments",
        "payment_status_events",
        "alembic_version",
    }.issubset(tables)
