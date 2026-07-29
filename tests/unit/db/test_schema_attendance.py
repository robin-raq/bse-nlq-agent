"""Attendance-coherence tests: attendance is present exactly when status is
'completed', enforced by the table-level CHECK on events.
"""

import sqlite3

import pytest

GOOD_TIMESTAMP = "2026-01-01T10:00:00"


def _insert(
    connection: sqlite3.Connection, status: str, attendance: int | None
) -> None:
    connection.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', ?, ?, 500, ?)",
        (status, GOOD_TIMESTAMP, attendance),
    )


def test_completed_with_valid_attendance_succeeds(
    seeded_venue: sqlite3.Connection,
) -> None:
    _insert(seeded_venue, "completed", 250)


def test_completed_with_null_attendance_fails(seeded_venue: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert(seeded_venue, "completed", None)


def test_scheduled_with_attendance_fails(seeded_venue: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert(seeded_venue, "scheduled", 250)


def test_cancelled_with_attendance_fails(seeded_venue: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert(seeded_venue, "cancelled", 250)


def test_scheduled_with_null_attendance_succeeds(
    seeded_venue: sqlite3.Connection,
) -> None:
    _insert(seeded_venue, "scheduled", None)


def test_cancelled_with_null_attendance_succeeds(
    seeded_venue: sqlite3.Connection,
) -> None:
    _insert(seeded_venue, "cancelled", None)
