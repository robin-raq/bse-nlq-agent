"""Database layer: schema, seeding, persistent build, and read-only runtime open.

Persistent artifact construction lives in ``bse_nlq.db.build``. Read-only
runtime opening lives in ``bse_nlq.db.runtime``. SQL policy lives in
``bse_nlq.sql_policy``; authorizer, progress limits, and query execution live
in ``bse_nlq.db.execution``.

Heavy submodules are re-exported lazily so ``python -m bse_nlq.db.build`` does
not pre-import ``bse_nlq.db.build`` via ``runtime`` (avoids runpy's
RuntimeWarning).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bse_nlq.db.errors import DatabaseBuildError, DatabaseRuntimeError
from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data

if TYPE_CHECKING:
    from bse_nlq.db.build import DatabaseBuildResult, build_database
    from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database

__all__ = [
    "DatabaseBuildError",
    "DatabaseBuildResult",
    "DatabaseRuntimeError",
    "ReadOnlyDatabase",
    "apply_schema",
    "build_database",
    "load_seed_data",
    "open_readonly_database",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DatabaseBuildResult": ("bse_nlq.db.build", "DatabaseBuildResult"),
    "build_database": ("bse_nlq.db.build", "build_database"),
    "ReadOnlyDatabase": ("bse_nlq.db.runtime", "ReadOnlyDatabase"),
    "open_readonly_database": ("bse_nlq.db.runtime", "open_readonly_database"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        from importlib import import_module

        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
