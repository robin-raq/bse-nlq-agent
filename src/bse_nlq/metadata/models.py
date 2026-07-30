"""Immutable typed models for the semantic metadata sidecar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Unit(StrEnum):
    """Closed unit classification for exposed numeric fields and metrics."""

    CENTS = "cents"
    COUNT = "count"
    PEOPLE = "people"
    CENTS_PER_ITEM = "cents_per_item"
    DIMENSIONLESS = "dimensionless"
    BASIS_POINTS = "basis_points"


class MetricId(StrEnum):
    """Stable identifiers for model-facing metric contracts."""

    GROSS_TICKET_REVENUE = "gross_ticket_revenue"
    REFUNDED_TICKET_REVENUE = "refunded_ticket_revenue"
    NET_TICKET_REVENUE = "net_ticket_revenue"
    TICKETS_SOLD = "tickets_sold"
    TICKETS_NET = "tickets_net"
    AVERAGE_TICKET_PRICE = "average_ticket_price"
    ATTENDANCE_RATE = "attendance_rate"
    EVER_SOLD_OUT = "ever_sold_out"
    CURRENTLY_SOLD_OUT = "currently_sold_out"


class ClarificationId(StrEnum):
    """Frozen clarification policies that must not default silently."""

    BARE_REVENUE = "bare_revenue"
    BEST_EVENT = "best_event"
    HOW_ARE_SALES_DOING = "how_are_sales_doing"
    SOLD_OUT = "sold_out"


class UnsupportedId(StrEnum):
    """Frozen unsupported question shapes."""

    RELATIVE_TIME_OF_DAY = "relative_time_of_day"


APPLICATION_TABLES: tuple[str, ...] = (
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
)

# Columns that schema-design.md marks Meta?=yes — required semantic coverage.
REQUIRED_SEMANTIC_COLUMNS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "venues": frozenset({"name", "district", "capacity"}),
        "events": frozenset(
            {
                "name",
                "category",
                "status",
                "start_local",
                "event_date",
                "capacity",
                "attendance",
            }
        ),
        "ticket_tiers": frozenset({"tier_name", "face_value_cents"}),
        "orders": frozenset({"order_ref", "channel", "status", "purchased_at"}),
        "order_items": frozenset({"quantity", "unit_price_cents", "line_gross_cents"}),
        "refunds": frozenset(
            {"refunded_qty", "refund_amount_cents", "refunded_at", "reason"}
        ),
    }
)

# Numeric columns that must carry an explicit unit.
REQUIRED_NUMERIC_UNITS: Mapping[str, Mapping[str, Unit]] = MappingProxyType(
    {
        "venues": MappingProxyType({"capacity": Unit.PEOPLE}),
        "events": MappingProxyType(
            {
                "capacity": Unit.PEOPLE,
                "attendance": Unit.PEOPLE,
            }
        ),
        "ticket_tiers": MappingProxyType({"face_value_cents": Unit.CENTS}),
        "order_items": MappingProxyType(
            {
                "quantity": Unit.COUNT,
                "unit_price_cents": Unit.CENTS,
                "line_gross_cents": Unit.CENTS,
            }
        ),
        "refunds": MappingProxyType(
            {
                "refunded_qty": Unit.COUNT,
                "refund_amount_cents": Unit.CENTS,
            }
        ),
    }
)

# Schema-owned structural keys that metadata must not claim authority over.
FORBIDDEN_STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "datatype",
        "data_type",
        "sqlite_type",
        "primary_key",
        "pk",
        "foreign_key",
        "fk",
        "nullable",
        "not_null",
        "nullability",
        "generated",
        "generated_column",
        "hidden",
    }
)

ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "conventions",
        "metrics",
        "clarifications",
        "unsupported",
        "tables",
        "join_guidance",
    }
)

ALLOWED_COLUMN_KEYS: frozenset[str] = frozenset(
    {
        "description",
        "in_prompt",
        "unit",
        "synonyms",
        "roles",
        "notes",
        "excluded_use",
        "allowed_analytical_use",
    }
)

ALLOWED_TABLE_KEYS: frozenset[str] = frozenset(
    {
        "description",
        "columns",
        "notes",
        "roles",
    }
)


@dataclass(frozen=True, slots=True)
class ColumnMetadata:
    """Semantic facts for one physical column."""

    name: str
    description: str
    in_prompt: bool
    unit: Unit | None = None
    synonyms: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()
    excluded_use: tuple[str, ...] = ()
    allowed_analytical_use: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """Semantic facts for one application table."""

    name: str
    description: str
    columns: Mapping[str, ColumnMetadata]
    notes: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Model-facing metric contract."""

    metric_id: MetricId
    description: str
    expression: str
    unit: Unit
    filters: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ClarificationPolicy:
    """A question shape that must reach clarification_required."""

    clarification_id: ClarificationId
    description: str
    options: tuple[str, ...]
    requires: tuple[str, ...] = ()
    silent_default_forbidden: bool = True


@dataclass(frozen=True, slots=True)
class UnsupportedPolicy:
    """A question shape that must reach unsupported_question."""

    unsupported_id: UnsupportedId
    description: str
    examples: tuple[str, ...]
    invent_default_forbidden: bool = True


@dataclass(frozen=True, slots=True)
class JoinGuidance:
    """Semantic join note validated against an introspected foreign key."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    note: str


@dataclass(frozen=True, slots=True)
class Conventions:
    """Cross-cutting date, timezone, unit, and rounding conventions."""

    timezone: str
    timestamp_format: str
    timestamps_have_offset: bool
    default_as_of: str
    date_ranges: str
    upcoming_inclusive_of_as_of: bool
    upcoming_requires_scheduled: bool
    rounding_rule: str
    unit_rules: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticMetadata:
    """Validated, immutable semantic metadata for the six application tables."""

    version: int
    conventions: Conventions
    metrics: Mapping[MetricId, MetricDefinition]
    clarifications: Mapping[ClarificationId, ClarificationPolicy]
    unsupported: Mapping[UnsupportedId, UnsupportedPolicy]
    tables: Mapping[str, TableMetadata]
    join_guidance: tuple[JoinGuidance, ...]

    def table(self, name: str) -> TableMetadata:
        return self.tables[name]

    def column(self, table: str, column: str) -> ColumnMetadata:
        return self.tables[table].columns[column]

    def metric(self, metric_id: MetricId | str) -> MetricDefinition:
        key = MetricId(metric_id) if not isinstance(metric_id, MetricId) else metric_id
        return self.metrics[key]
