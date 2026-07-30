"""Semantic-content contract tests for the metadata sidecar."""

from __future__ import annotations

import sqlite3

from bse_nlq.metadata import (
    ClarificationId,
    MetricId,
    Unit,
    UnsupportedId,
    load_semantic_metadata,
)


def test_paid_price_versus_face_value(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    face = metadata.column("ticket_tiers", "face_value_cents")
    paid = metadata.column("order_items", "unit_price_cents")
    assert "never_revenue" in face.roles
    assert "list_price_only" in face.roles
    assert any("Never used in any revenue metric" in note for note in face.notes)
    assert "revenue_input" in paid.roles
    assert "actual_paid_price" in paid.roles
    assert "The only price input to revenue" in paid.description


def test_gross_versus_net_revenue(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    gross = metadata.metric(MetricId.GROSS_TICKET_REVENUE)
    net = metadata.metric(MetricId.NET_TICKET_REVENUE)
    refunded = metadata.metric(MetricId.REFUNDED_TICKET_REVENUE)
    assert gross.unit is Unit.CENTS
    assert net.unit is Unit.CENTS
    assert refunded.unit is Unit.CENTS
    assert "completed_orders_only" in gross.filters
    assert "completed_orders_only" in net.filters
    assert "refunds_preaggregated_by_order_item_id" in net.filters
    assert "gross_ticket_revenue - refunded_ticket_revenue" in net.expression


def test_completed_order_filters(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    for metric_id in (
        MetricId.GROSS_TICKET_REVENUE,
        MetricId.REFUNDED_TICKET_REVENUE,
        MetricId.NET_TICKET_REVENUE,
        MetricId.TICKETS_SOLD,
        MetricId.TICKETS_NET,
        MetricId.AVERAGE_TICKET_PRICE,
    ):
        assert "completed_orders_only" in metadata.metric(metric_id).filters
    assert "completed" in metadata.column("orders", "status").notes[0].lower() or (
        "Only completed orders" in metadata.tables["orders"].notes[0]
    )


def test_refund_preaggregation_and_independence(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert "requires_preaggregation" in metadata.tables["refunds"].roles
    refunded_rev = metadata.metric(MetricId.REFUNDED_TICKET_REVENUE)
    tickets_net = metadata.metric(MetricId.TICKETS_NET)
    assert "requires_refund_preaggregation" in refunded_rev.roles
    assert "independent_of_refunded_qty" in refunded_rev.roles
    assert "independent_of_refund_amount" in tickets_net.roles
    qty = metadata.column("refunds", "refunded_qty")
    amount = metadata.column("refunds", "refund_amount_cents")
    assert "independent_of_refund_amount" in qty.roles
    assert "independent_of_refunded_qty" in amount.roles


def test_tickets_sold_versus_tickets_net(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    sold = metadata.metric(MetricId.TICKETS_SOLD)
    net = metadata.metric(MetricId.TICKETS_NET)
    assert sold.unit is Unit.COUNT
    assert net.unit is Unit.COUNT
    assert sold.metric_id is not net.metric_id
    assert "tickets_sold -" in net.expression


def test_venue_capacity_versus_event_capacity(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    venue_cap = metadata.column("venues", "capacity")
    event_cap = metadata.column("events", "capacity")
    assert venue_cap.unit is Unit.PEOPLE
    assert event_cap.unit is Unit.PEOPLE
    assert "not_sold_out_denominator" in venue_cap.roles
    assert "sold_out_denominator" in event_cap.roles
    assert "physical maximum" in venue_cap.description.lower()
    assert "released capacity" in event_cap.description.lower()


def test_attendance_versus_tickets_sold(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    attendance = metadata.column("events", "attendance")
    assert "turnstile" in attendance.roles
    assert "not_tickets_sold" in attendance.roles
    assert attendance.unit is Unit.PEOPLE


def test_event_date_versus_purchased_at(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    event_date = metadata.column("events", "event_date")
    purchased_at = metadata.column("orders", "purchased_at")
    assert "not_purchased_at" in event_date.roles
    assert "not_event_date" in purchased_at.roles
    assert metadata.conventions.default_as_of == "2026-03-15"
    assert metadata.conventions.timezone == "America/New_York"
    assert metadata.conventions.timestamps_have_offset is False
    assert metadata.conventions.date_ranges == "half-open"


def test_event_scoped_tier_names(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    tier_name = metadata.column("ticket_tiers", "tier_name")
    assert "event_scoped_name" in tier_name.roles
    assert any("scoped to event_id" in note.lower() for note in tier_name.notes)


def test_no_individual_tickets_table(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert "tickets" not in metadata.tables
    assert "no_individual_ticket_identity" in metadata.tables["ticket_tiers"].roles
    assert "no_individual_ticket_identity" in metadata.tables["order_items"].roles


def test_upcoming_inclusive_date_behavior(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert metadata.conventions.upcoming_inclusive_of_as_of is True
    assert metadata.conventions.upcoming_requires_scheduled is True
    assert any("upcoming means" in note.lower() for note in metadata.conventions.notes)


def test_four_clarification_policies(seeded_connection: sqlite3.Connection) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert set(metadata.clarifications) == set(ClarificationId)
    bare = metadata.clarifications[ClarificationId.BARE_REVENUE]
    assert bare.silent_default_forbidden is True
    assert "gross_ticket_revenue" in bare.options
    assert "net_ticket_revenue" in bare.options
    best = metadata.clarifications[ClarificationId.BEST_EVENT]
    assert "metric" in best.requires
    assert "period_when_absent" in best.requires
    sales = metadata.clarifications[ClarificationId.HOW_ARE_SALES_DOING]
    assert "metric" in sales.requires
    assert "period" in sales.requires
    assert "comparison_or_baseline_when_trend" in sales.requires
    sold_out = metadata.clarifications[ClarificationId.SOLD_OUT]
    assert "ever_sold_out" in sold_out.options
    assert "currently_sold_out" in sold_out.options


def test_relative_time_of_day_unsupported(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    policy = metadata.unsupported[UnsupportedId.RELATIVE_TIME_OF_DAY]
    assert policy.invent_default_forbidden is True
    joined = " ".join(policy.examples).lower()
    assert "tonight" in joined
    assert "right now" in joined
    assert "6 pm" in joined


def test_units_for_every_exposed_numeric_column(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    expected = {
        ("venues", "capacity"): Unit.PEOPLE,
        ("events", "capacity"): Unit.PEOPLE,
        ("events", "attendance"): Unit.PEOPLE,
        ("ticket_tiers", "face_value_cents"): Unit.CENTS,
        ("order_items", "quantity"): Unit.COUNT,
        ("order_items", "unit_price_cents"): Unit.CENTS,
        ("order_items", "line_gross_cents"): Unit.CENTS,
        ("refunds", "refunded_qty"): Unit.COUNT,
        ("refunds", "refund_amount_cents"): Unit.CENTS,
    }
    for (table, column), unit in expected.items():
        assert metadata.column(table, column).unit is unit


def test_metric_units_and_average_ticket_price_contract(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    avg = metadata.metric(MetricId.AVERAGE_TICKET_PRICE)
    assert avg.unit is Unit.CENTS_PER_ITEM
    assert "never_avg_unit_price" in avg.roles
    assert "never_face_value" in avg.roles
    rate = metadata.metric(MetricId.ATTENDANCE_RATE)
    assert rate.unit is Unit.DIMENSIONLESS
    assert "completed_events_only" in rate.filters
    ever = metadata.metric(MetricId.EVER_SOLD_OUT)
    current = metadata.metric(MetricId.CURRENTLY_SOLD_OUT)
    assert "tickets_sold >=" in ever.expression
    assert "tickets_net >=" in current.expression


def test_line_gross_not_multiplied_again(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    line = metadata.column("order_items", "line_gross_cents")
    assert "do not multiply by quantity again" in line.description.lower()
    assert "generated_line_gross" in line.roles
