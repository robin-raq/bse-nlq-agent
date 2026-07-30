"""Parse and structurally validate the semantic metadata document."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from bse_nlq.metadata.errors import MetadataValidationError
from bse_nlq.metadata.freeze import freeze_mapping
from bse_nlq.metadata.models import (
    ALLOWED_COLUMN_KEYS,
    ALLOWED_TABLE_KEYS,
    ALLOWED_TOP_LEVEL_KEYS,
    APPLICATION_TABLES,
    FORBIDDEN_STRUCTURAL_KEYS,
    REQUIRED_NUMERIC_UNITS,
    REQUIRED_SEMANTIC_COLUMNS,
    ClarificationId,
    ClarificationPolicy,
    ColumnMetadata,
    Conventions,
    JoinGuidance,
    MetricDefinition,
    MetricId,
    SemanticMetadata,
    TableMetadata,
    Unit,
    UnsupportedId,
    UnsupportedPolicy,
)


def parse_metadata_json(text: str) -> SemanticMetadata:
    """Parse UTF-8 JSON text into validated immutable metadata.

    Duplicate object keys at any nesting level are rejected before normal
    ``dict`` construction can silently keep only the last value.
    """
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise MetadataValidationError(f"malformed JSON: {exc}") from exc
    except MetadataValidationError:
        raise
    return validate_metadata_document(payload)


def validate_metadata_document(payload: object) -> SemanticMetadata:
    """Validate a decoded metadata document and return typed objects."""
    if not isinstance(payload, dict):
        raise MetadataValidationError("metadata document must be a JSON object")

    _reject_unknown_keys(payload, ALLOWED_TOP_LEVEL_KEYS, "top-level")
    version = _require_int(payload, "version")
    if version != 1:
        raise MetadataValidationError(f"unsupported metadata version: {version}")

    conventions = _parse_conventions(_require_mapping(payload, "conventions"))
    metrics = _parse_metrics(_require_mapping(payload, "metrics"))
    clarifications = _parse_clarifications(_require_mapping(payload, "clarifications"))
    unsupported = _parse_unsupported(_require_mapping(payload, "unsupported"))
    tables = _parse_tables(_require_mapping(payload, "tables"))
    join_guidance = _parse_join_guidance(_require_list(payload, "join_guidance"))

    return SemanticMetadata(
        version=version,
        conventions=conventions,
        metrics=freeze_mapping(metrics),
        clarifications=freeze_mapping(clarifications),
        unsupported=freeze_mapping(unsupported),
        tables=freeze_mapping(tables),
        join_guidance=join_guidance,
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise MetadataValidationError(f"duplicate JSON object key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _parse_conventions(raw: Mapping[str, Any]) -> Conventions:
    allowed = frozenset(
        {
            "timezone",
            "timestamp_format",
            "timestamps_have_offset",
            "default_as_of",
            "date_ranges",
            "upcoming_inclusive_of_as_of",
            "upcoming_requires_scheduled",
            "rounding_rule",
            "unit_rules",
            "notes",
        }
    )
    _reject_unknown_keys(raw, allowed, "conventions")
    return Conventions(
        timezone=_require_str(raw, "timezone"),
        timestamp_format=_require_str(raw, "timestamp_format"),
        timestamps_have_offset=_require_bool(raw, "timestamps_have_offset"),
        default_as_of=_require_str(raw, "default_as_of"),
        date_ranges=_require_str(raw, "date_ranges"),
        upcoming_inclusive_of_as_of=_require_bool(raw, "upcoming_inclusive_of_as_of"),
        upcoming_requires_scheduled=_require_bool(raw, "upcoming_requires_scheduled"),
        rounding_rule=_require_str(raw, "rounding_rule"),
        unit_rules=tuple(_require_str_list(raw, "unit_rules")),
        notes=tuple(_optional_str_list(raw, "notes")),
    )


def _parse_metrics(raw: Mapping[str, Any]) -> dict[MetricId, MetricDefinition]:
    expected = set(MetricId)
    seen: dict[MetricId, MetricDefinition] = {}
    for key, value in raw.items():
        try:
            metric_id = MetricId(key)
        except ValueError as exc:
            raise MetadataValidationError(f"unknown metric id: {key!r}") from exc
        if not isinstance(value, dict):
            raise MetadataValidationError(f"metric {key!r} must be an object")
        allowed = frozenset(
            {"description", "expression", "unit", "filters", "notes", "roles"}
        )
        _reject_unknown_keys(value, allowed, f"metrics.{key}")
        unit = _parse_unit(_require_str(value, "unit"), f"metrics.{key}.unit")
        seen[metric_id] = MetricDefinition(
            metric_id=metric_id,
            description=_require_str(value, "description"),
            expression=_require_str(value, "expression"),
            unit=unit,
            filters=frozenset(_optional_str_list(value, "filters")),
            notes=tuple(_optional_str_list(value, "notes")),
            roles=frozenset(_optional_str_list(value, "roles")),
        )
    missing = expected - set(seen)
    if missing:
        raise MetadataValidationError(
            "missing required metrics: " + ", ".join(sorted(m.value for m in missing))
        )
    return seen


def _parse_clarifications(
    raw: Mapping[str, Any],
) -> dict[ClarificationId, ClarificationPolicy]:
    expected = set(ClarificationId)
    seen: dict[ClarificationId, ClarificationPolicy] = {}
    for key, value in raw.items():
        try:
            clarification_id = ClarificationId(key)
        except ValueError as exc:
            raise MetadataValidationError(f"unknown clarification id: {key!r}") from exc
        if not isinstance(value, dict):
            raise MetadataValidationError(f"clarification {key!r} must be an object")
        allowed = frozenset(
            {
                "description",
                "options",
                "requires",
                "silent_default_forbidden",
            }
        )
        _reject_unknown_keys(value, allowed, f"clarifications.{key}")
        silent = _require_bool(value, "silent_default_forbidden")
        if not silent:
            raise MetadataValidationError(
                f"clarification {key!r} must forbid silent defaults"
            )
        seen[clarification_id] = ClarificationPolicy(
            clarification_id=clarification_id,
            description=_require_str(value, "description"),
            options=tuple(_require_str_list(value, "options")),
            requires=tuple(_optional_str_list(value, "requires")),
            silent_default_forbidden=silent,
        )
    missing = expected - set(seen)
    if missing:
        raise MetadataValidationError(
            "missing required clarifications: "
            + ", ".join(sorted(m.value for m in missing))
        )
    return seen


def _parse_unsupported(
    raw: Mapping[str, Any],
) -> dict[UnsupportedId, UnsupportedPolicy]:
    expected = set(UnsupportedId)
    seen: dict[UnsupportedId, UnsupportedPolicy] = {}
    for key, value in raw.items():
        try:
            unsupported_id = UnsupportedId(key)
        except ValueError as exc:
            raise MetadataValidationError(f"unknown unsupported id: {key!r}") from exc
        if not isinstance(value, dict):
            raise MetadataValidationError(f"unsupported {key!r} must be an object")
        allowed = frozenset({"description", "examples", "invent_default_forbidden"})
        _reject_unknown_keys(value, allowed, f"unsupported.{key}")
        invent = _require_bool(value, "invent_default_forbidden")
        if not invent:
            raise MetadataValidationError(
                f"unsupported {key!r} must forbid invented time-of-day defaults"
            )
        seen[unsupported_id] = UnsupportedPolicy(
            unsupported_id=unsupported_id,
            description=_require_str(value, "description"),
            examples=tuple(_require_str_list(value, "examples")),
            invent_default_forbidden=invent,
        )
    missing = expected - set(seen)
    if missing:
        raise MetadataValidationError(
            "missing required unsupported policies: "
            + ", ".join(sorted(m.value for m in missing))
        )
    return seen


def _parse_tables(raw: Mapping[str, Any]) -> dict[str, TableMetadata]:
    expected = set(APPLICATION_TABLES)
    if set(raw) != expected:
        extra = set(raw) - expected
        missing = expected - set(raw)
        parts: list[str] = []
        if missing:
            parts.append("missing tables: " + ", ".join(sorted(missing)))
        if extra:
            parts.append("unknown tables: " + ", ".join(sorted(extra)))
        raise MetadataValidationError("; ".join(parts))

    tables: dict[str, TableMetadata] = {}
    for table_name in APPLICATION_TABLES:
        value = raw[table_name]
        if not isinstance(value, dict):
            raise MetadataValidationError(f"table {table_name!r} must be an object")
        _reject_unknown_keys(value, ALLOWED_TABLE_KEYS, f"tables.{table_name}")
        columns_raw = _require_mapping(value, "columns")
        columns = _parse_columns(table_name, columns_raw)
        tables[table_name] = TableMetadata(
            name=table_name,
            description=_require_str(value, "description"),
            columns=freeze_mapping(columns),
            notes=tuple(_optional_str_list(value, "notes")),
            roles=frozenset(_optional_str_list(value, "roles")),
        )
    return tables


def _parse_columns(
    table_name: str, raw: Mapping[str, Any]
) -> dict[str, ColumnMetadata]:
    if not raw:
        raise MetadataValidationError(f"table {table_name!r} has no columns")

    required = REQUIRED_SEMANTIC_COLUMNS[table_name]
    missing_required = required - set(raw)
    if missing_required:
        raise MetadataValidationError(
            f"table {table_name!r} missing required semantic columns: "
            + ", ".join(sorted(missing_required))
        )

    columns: dict[str, ColumnMetadata] = {}
    for column_name, value in raw.items():
        if not isinstance(column_name, str) or not column_name:
            raise MetadataValidationError(
                f"invalid column name under table {table_name!r}"
            )
        if not isinstance(value, dict):
            raise MetadataValidationError(
                f"column {table_name}.{column_name} must be an object"
            )
        structural = FORBIDDEN_STRUCTURAL_KEYS & set(value)
        if structural:
            raise MetadataValidationError(
                f"column {table_name}.{column_name} claims schema-owned keys: "
                + ", ".join(sorted(structural))
            )
        _reject_unknown_keys(
            value, ALLOWED_COLUMN_KEYS, f"tables.{table_name}.columns.{column_name}"
        )
        in_prompt = _require_bool(value, "in_prompt")
        unit = None
        if "unit" in value and value["unit"] is not None:
            unit = _parse_unit(
                _require_str(value, "unit"),
                f"tables.{table_name}.columns.{column_name}.unit",
            )
        expected_units = REQUIRED_NUMERIC_UNITS.get(table_name, {})
        if column_name in expected_units:
            if unit is None:
                raise MetadataValidationError(
                    f"column {table_name}.{column_name} requires unit "
                    f"{expected_units[column_name].value}"
                )
            if unit != expected_units[column_name]:
                raise MetadataValidationError(
                    f"column {table_name}.{column_name} unit must be "
                    f"{expected_units[column_name].value}, got {unit.value}"
                )
        if not in_prompt and column_name != "order_ref":
            raise MetadataValidationError(
                f"column {table_name}.{column_name} has contradictory visibility: "
                "only orders.order_ref may set in_prompt=false"
            )
        if column_name == "order_ref" and in_prompt:
            raise MetadataValidationError(
                "orders.order_ref must be excluded from ordinary prompt context"
            )
        columns[column_name] = ColumnMetadata(
            name=column_name,
            description=_require_str(value, "description"),
            in_prompt=in_prompt,
            unit=unit,
            synonyms=tuple(_optional_str_list(value, "synonyms")),
            roles=frozenset(_optional_str_list(value, "roles")),
            notes=tuple(_optional_str_list(value, "notes")),
            excluded_use=tuple(_optional_str_list(value, "excluded_use")),
            allowed_analytical_use=tuple(
                _optional_str_list(value, "allowed_analytical_use")
            ),
        )
    return columns


def _parse_join_guidance(raw: Sequence[Any]) -> tuple[JoinGuidance, ...]:
    guidance: list[JoinGuidance] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise MetadataValidationError(f"join_guidance[{index}] must be an object")
        allowed = frozenset(
            {"from_table", "from_column", "to_table", "to_column", "note"}
        )
        _reject_unknown_keys(item, allowed, f"join_guidance[{index}]")
        entry = JoinGuidance(
            from_table=_require_str(item, "from_table"),
            from_column=_require_str(item, "from_column"),
            to_table=_require_str(item, "to_table"),
            to_column=_require_str(item, "to_column"),
            note=_require_str(item, "note"),
        )
        key = (
            entry.from_table,
            entry.from_column,
            entry.to_table,
            entry.to_column,
        )
        if key in seen:
            raise MetadataValidationError(
                "duplicate join_guidance entry for "
                f"{entry.from_table}.{entry.from_column} -> "
                f"{entry.to_table}.{entry.to_column}"
            )
        seen.add(key)
        guidance.append(entry)
    return tuple(guidance)


def _parse_unit(raw: str, path: str) -> Unit:
    try:
        return Unit(raw)
    except ValueError as exc:
        raise MetadataValidationError(f"invalid unit at {path}: {raw!r}") from exc


def _reject_unknown_keys(
    raw: Mapping[str, Any], allowed: frozenset[str], path: str
) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise MetadataValidationError(
            f"unknown keys under {path}: " + ", ".join(sorted(map(str, unknown)))
        )


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, dict):
        raise MetadataValidationError(f"{key} must be an object")
    return cast(Mapping[str, Any], value)


def _require_list(raw: Mapping[str, Any], key: str) -> list[Any]:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, list):
        raise MetadataValidationError(f"{key} must be an array")
    return value


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise MetadataValidationError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise MetadataValidationError(f"{key} must be an integer")
    return value


def _require_bool(raw: Mapping[str, Any], key: str) -> bool:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, bool):
        raise MetadataValidationError(f"{key} must be a boolean")
    return value


def _require_str_list(raw: Mapping[str, Any], key: str) -> list[str]:
    if key not in raw:
        raise MetadataValidationError(f"missing required field: {key}")
    value = raw[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise MetadataValidationError(f"{key} must be an array of non-empty strings")
    return cast(list[str], value)


def _optional_str_list(raw: Mapping[str, Any], key: str) -> list[str]:
    if key not in raw:
        return []
    value = raw[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise MetadataValidationError(f"{key} must be an array of non-empty strings")
    return cast(list[str], value)
