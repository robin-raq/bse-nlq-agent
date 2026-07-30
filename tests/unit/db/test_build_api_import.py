"""Public API import for the persistent database builder.

This file began as the phase red-state ImportError evidence before
``bse_nlq.db.build`` existed.
"""

from __future__ import annotations


def test_build_database_is_importable() -> None:
    from bse_nlq.db.build import DatabaseBuildResult, build_database
    from bse_nlq.db.errors import DatabaseBuildError

    assert callable(build_database)
    assert DatabaseBuildResult is not None
    assert issubclass(DatabaseBuildError, Exception)
