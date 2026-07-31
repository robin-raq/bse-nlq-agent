"""Public API import for the read-only runtime database factory.

This file begins as the phase red-state ImportError evidence before
``bse_nlq.db.runtime`` exists.
"""

from __future__ import annotations


def test_open_readonly_database_is_importable() -> None:
    from bse_nlq.db.errors import DatabaseRuntimeError
    from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database

    assert callable(open_readonly_database)
    assert ReadOnlyDatabase is not None
    assert issubclass(DatabaseRuntimeError, Exception)
