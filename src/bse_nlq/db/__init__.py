"""Database layer: schema, seeding, persistent build, and future read-only access.

Persistent artifact construction lives in ``bse_nlq.db.build``. Read-only
runtime connection factories and query execution remain separate later phases.
"""

from bse_nlq.db.build import DatabaseBuildResult, build_database
from bse_nlq.db.errors import DatabaseBuildError
from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data

__all__ = [
    "DatabaseBuildError",
    "DatabaseBuildResult",
    "apply_schema",
    "build_database",
    "load_seed_data",
]
