"""Loading, immutability, validation, and packaging tests for semantic metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import zipfile
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from bse_nlq.metadata import (
    MetadataValidationError,
    MetricId,
    Unit,
    load_metadata_document,
    load_semantic_metadata,
    parse_metadata_json,
    read_packaged_metadata_text,
    validate_metadata_document,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_packaged_metadata_is_utf8_json_object() -> None:
    text = read_packaged_metadata_text()
    assert isinstance(text, str)
    payload = json.loads(text)
    assert isinstance(payload, dict)
    assert payload["version"] == 1


def test_returned_metadata_mappings_are_mapping_proxy() -> None:
    metadata = load_metadata_document()
    assert isinstance(metadata.tables, MappingProxyType)
    assert isinstance(metadata.metrics, MappingProxyType)
    assert isinstance(metadata.clarifications, MappingProxyType)
    assert isinstance(metadata.unsupported, MappingProxyType)
    assert isinstance(metadata.tables["venues"].columns, MappingProxyType)
    assert isinstance(metadata.join_guidance, tuple)


def test_nested_mappings_reject_mutation() -> None:
    metadata = load_metadata_document()
    with pytest.raises(TypeError):
        metadata.tables["venues"] = metadata.tables["venues"]  # type: ignore[index]
    with pytest.raises(AttributeError):
        metadata.tables.clear()  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        metadata.metrics[MetricId.TICKETS_NET] = metadata.metrics[MetricId.TICKETS_NET]  # type: ignore[index]
    with pytest.raises(AttributeError):
        metadata.metrics.clear()  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        metadata.tables["venues"].columns["capacity"] = metadata.column(  # type: ignore[index]
            "venues", "capacity"
        )
    with pytest.raises(AttributeError):
        metadata.clarifications.clear()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        metadata.unsupported.clear()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        metadata.tables["venues"].columns["capacity"].roles.add("mutated")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        metadata.conventions.notes.append("x")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        metadata.join_guidance.append(metadata.join_guidance[0])  # type: ignore[attr-defined]


def test_ordinary_read_access_and_iteration_still_work() -> None:
    metadata = load_metadata_document()
    assert "venues" in metadata.tables
    assert list(metadata.tables) == list(metadata.tables.keys())
    assert len(metadata.metrics) == 9
    assert metadata.column("orders", "order_ref").in_prompt is False


def test_two_loads_are_independently_safe() -> None:
    first = load_metadata_document()
    second = load_metadata_document()
    assert first.tables is not second.tables
    assert first.metrics is not second.metrics
    assert first.tables["venues"].columns is not second.tables["venues"].columns


def test_mutating_source_document_after_validation_does_not_affect_metadata(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    metadata = validate_metadata_document(mutable_metadata_dict)
    mutable_metadata_dict["tables"]["venues"]["description"] = "MUTATED"
    mutable_metadata_dict["metrics"].clear()
    assert metadata.tables["venues"].description != "MUTATED"
    assert MetricId.GROSS_TICKET_REVENUE in metadata.metrics


def test_load_semantic_metadata_reconciles_seeded_database(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert metadata.column("orders", "order_ref").in_prompt is False
    assert metadata.metric(MetricId.GROSS_TICKET_REVENUE).unit is Unit.CENTS


def test_malformed_json_fails_closed() -> None:
    with pytest.raises(MetadataValidationError, match="malformed JSON"):
        parse_metadata_json("{not-json")


def test_duplicate_json_metric_key_rejected() -> None:
    text = read_packaged_metadata_text()
    # Insert a second tickets_sold key after the first object entry.
    needle = '"tickets_sold"'
    first = text.index(needle)
    # Find the end of the first tickets_sold object value by locating the
    # following sibling key separator after its closing brace block.
    insert_at = text.index('"tickets_net"', first)
    duplicate_block = (
        '"tickets_sold": {'
        '"description": "duplicate",'
        '"expression": "x",'
        '"filters": ["completed_orders_only"],'
        '"notes": ["dup"],'
        '"roles": ["ticket_count"],'
        '"unit": "count"'
        "}, "
    )
    poisoned = text[:insert_at] + duplicate_block + text[insert_at:]
    with pytest.raises(MetadataValidationError, match="duplicate JSON object key"):
        parse_metadata_json(poisoned)


def test_missing_required_metric_rejected(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    del mutable_metadata_dict["metrics"]["tickets_net"]
    with pytest.raises(MetadataValidationError, match="missing required metrics"):
        validate_metadata_document(mutable_metadata_dict)


def test_missing_required_field_fails(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    del mutable_metadata_dict["metrics"]
    with pytest.raises(MetadataValidationError, match="missing required field"):
        validate_metadata_document(mutable_metadata_dict)


def test_unknown_top_level_key_rejected(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["runtime_provider"] = "openai"
    with pytest.raises(MetadataValidationError, match="unknown keys"):
        validate_metadata_document(mutable_metadata_dict)


def test_unknown_metric_id_rejected(mutable_metadata_dict: dict[str, Any]) -> None:
    mutable_metadata_dict["metrics"]["invented_metric"] = {
        "description": "x",
        "expression": "y",
        "unit": "cents",
        "filters": [],
        "notes": [],
        "roles": [],
    }
    with pytest.raises(MetadataValidationError, match="unknown metric id"):
        validate_metadata_document(mutable_metadata_dict)


def test_invalid_unit_rejected(mutable_metadata_dict: dict[str, Any]) -> None:
    mutable_metadata_dict["tables"]["venues"]["columns"]["capacity"]["unit"] = "widgets"
    with pytest.raises(MetadataValidationError, match="invalid unit"):
        validate_metadata_document(mutable_metadata_dict)


def test_structural_override_keys_rejected(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["tables"]["venues"]["columns"]["capacity"]["primary_key"] = (
        True
    )
    with pytest.raises(MetadataValidationError, match="schema-owned keys"):
        validate_metadata_document(mutable_metadata_dict)


def test_order_ref_must_be_prompt_excluded(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["tables"]["orders"]["columns"]["order_ref"]["in_prompt"] = (
        True
    )
    with pytest.raises(MetadataValidationError, match="order_ref"):
        validate_metadata_document(mutable_metadata_dict)


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("venues", "venue_id"),
        ("events", "venue_id"),
        ("events", "event_date"),
        ("order_items", "line_gross_cents"),
        ("venues", "capacity"),
    ],
)
def test_non_order_ref_cannot_be_prompt_excluded(
    mutable_metadata_dict: dict[str, Any],
    table: str,
    column: str,
) -> None:
    mutable_metadata_dict["tables"][table]["columns"][column]["in_prompt"] = False
    with pytest.raises(MetadataValidationError, match="contradictory visibility"):
        validate_metadata_document(mutable_metadata_dict)


def test_clarification_silent_default_forbidden(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["clarifications"]["bare_revenue"][
        "silent_default_forbidden"
    ] = False
    with pytest.raises(MetadataValidationError, match="forbid silent defaults"):
        validate_metadata_document(mutable_metadata_dict)


def test_extra_table_rejected(mutable_metadata_dict: dict[str, Any]) -> None:
    mutable_metadata_dict["tables"]["tickets"] = {
        "description": "invented",
        "columns": {
            "ticket_id": {
                "description": "x",
                "in_prompt": True,
            }
        },
        "notes": [],
        "roles": [],
    }
    with pytest.raises(MetadataValidationError, match="unknown tables"):
        validate_metadata_document(mutable_metadata_dict)


def test_schema_json_ships_in_and_loads_from_installed_wheel(
    tmp_path: Path,
) -> None:
    """Prove package-data inclusion without relying on editable installs."""
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    build = subprocess.run(
        ["uv", "build", "--wheel", "-o", str(wheel_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "bse_nlq/metadata/schema.json" in names

    venv_dir = tmp_path / "venv"
    create = subprocess.run(
        ["uv", "venv", str(venv_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert create.returncode == 0, create.stderr
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stderr

    outside = tmp_path / "outside"
    outside.mkdir()
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from bse_nlq.metadata import load_metadata_document, "
                "read_packaged_metadata_text;"
                "text = read_packaged_metadata_text();"
                "meta = load_metadata_document();"
                "assert text.lstrip().startswith('{');"
                "assert meta.version == 1;"
                "assert set(meta.tables) == {"
                "'venues','events','ticket_tiers','orders',"
                "'order_items','refunds'};"
                "print('WHEEL_LOAD_OK', sorted(meta.tables))"
            ),
        ],
        cwd=outside,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": "",
            "PYTHONNOUSERSITE": "1",
        },
    )
    assert probe.returncode == 0, probe.stderr + probe.stdout
    assert "WHEEL_LOAD_OK" in probe.stdout
