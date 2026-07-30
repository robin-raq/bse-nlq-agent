"""Semantic metadata rendering for prompts."""

from __future__ import annotations

from bse_nlq.metadata.models import ClarificationId, MetricId, UnsupportedId
from bse_nlq.prompt.semantic_render import render_semantic_context


def test_renders_nine_metrics_and_four_clarifications(metadata) -> None:
    text = render_semantic_context(metadata)
    for metric in MetricId:
        assert metric.value in text
    for clarification in ClarificationId:
        assert clarification.value in text
    assert UnsupportedId.RELATIVE_TIME_OF_DAY.value in text


def test_renders_required_business_distinctions(metadata) -> None:
    text = render_semantic_context(metadata)
    assert "face_value_cents" in text
    assert "unit_price_cents" in text
    assert "gross_ticket_revenue" in text
    assert "net_ticket_revenue" in text
    assert "completed_orders_only" in text or "completed orders" in text.lower()
    assert "pre-aggregated" in text.lower() or "preaggregated" in text.lower()
    assert "tickets_sold" in text
    assert "tickets_net" in text
    assert "venues.capacity" in text or "physical maximum" in text.lower()
    assert "events.capacity" in text or "released capacity" in text.lower()
    assert "attendance" in text
    assert "event_date" in text
    assert "purchased_at" in text
    assert "tier_name" in text
    assert "default_as_of" in text
    assert "half-open" in text or "half_open" in text or "half-open" in text
    assert "basis" in text.lower()
    assert "relative_time_of_day" in text


def test_excludes_order_ref_and_seed_answers(metadata) -> None:
    text = render_semantic_context(metadata)
    assert "order_ref" not in text
    assert "A1" not in text
    assert "7,270,000" not in text
    assert "7270000" not in text
