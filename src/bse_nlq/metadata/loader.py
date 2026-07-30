"""Load packaged semantic metadata and reconcile it with SQLite."""

from __future__ import annotations

import sqlite3
from importlib import resources

from bse_nlq.metadata.models import SemanticMetadata
from bse_nlq.metadata.reconcile import reconcile_metadata
from bse_nlq.metadata.validate import parse_metadata_json, validate_metadata_document

_METADATA_RESOURCE = "schema.json"


def read_packaged_metadata_text() -> str:
    """Read the packaged UTF-8 metadata JSON without validating it.

    Uses importlib.resources so loading works after installation, not only from
    a repository checkout. Does not touch the network or a database path.
    """
    root = resources.files("bse_nlq.metadata")
    return (root / _METADATA_RESOURCE).read_text(encoding="utf-8")


def load_metadata_document() -> SemanticMetadata:
    """Load and structurally validate the packaged metadata JSON."""
    return parse_metadata_json(read_packaged_metadata_text())


def load_semantic_metadata(connection: sqlite3.Connection) -> SemanticMetadata:
    """Load, validate, and reconcile metadata against a caller-supplied connection.

    The caller owns the connection. This function never opens a database path,
    never mutates global state, and never performs network access.
    """
    metadata = load_metadata_document()
    reconcile_metadata(metadata, connection)
    return metadata


__all__ = [
    "load_metadata_document",
    "load_semantic_metadata",
    "parse_metadata_json",
    "read_packaged_metadata_text",
    "reconcile_metadata",
    "validate_metadata_document",
]
