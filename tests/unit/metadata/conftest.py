"""Shared fixtures for semantic metadata tests."""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data
from bse_nlq.metadata import read_packaged_metadata_text


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    try:
        apply_schema(conn)
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    load_seed_data(connection)
    return connection


@pytest.fixture
def packaged_metadata_dict() -> dict[str, Any]:
    return json.loads(read_packaged_metadata_text())


@pytest.fixture
def mutable_metadata_dict(packaged_metadata_dict: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(packaged_metadata_dict)
