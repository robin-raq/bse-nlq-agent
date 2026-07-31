"""Database layer: schema, seeding, persistent build, and read-only runtime open.

Persistent artifact construction lives in ``bse_nlq.db.build``. Read-only
runtime opening lives in ``bse_nlq.db.runtime``. SQL policy, authorizer,
progress limits, and query execution remain separate later phases.
"""

from bse_nlq.db.build import DatabaseBuildResult, build_database
from bse_nlq.db.errors import DatabaseBuildError, DatabaseRuntimeError
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data

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
