"""Prompt content inventory and leak checks."""

from __future__ import annotations

from bse_nlq.metadata.models import APPLICATION_TABLES, ClarificationId, MetricId
from bse_nlq.prompt.models import BuiltPrompt


def _full_text(prompt: BuiltPrompt) -> str:
    return prompt.canonical_text()


def test_schema_section_lists_tables_and_five_fks(built_prompt: BuiltPrompt) -> None:
    from bse_nlq.prompt.schema_render import render_physical_schema

    # Count headings in the physical schema renderer, not substring matches
    # against #### table headings in the semantic section.
    # Use the built prompt's connection indirectly via section content markers.
    system = built_prompt.system_instructions
    assert "## Physical schema" in system
    for table in APPLICATION_TABLES:
        assert f"\n### {table}\n" in system or system.startswith(f"### {table}\n")
        # Exactly one physical-schema H3 for the table (semantic uses H4).
        assert (
            system.count(f"\n### {table}\n")
            + (1 if system.startswith(f"### {table}\n") else 0)
            == 1
        )
    assert "events.venue_id -> venues.venue_id" in system
    assert "ticket_tiers.event_id -> events.event_id" in system
    assert "order_items.order_id -> orders.order_id" in system
    assert "order_items.tier_id -> ticket_tiers.tier_id" in system
    assert "refunds.order_item_id -> order_items.order_item_id" in system
    assert "order_ref" not in system
    assert "order_ref" not in _full_text(built_prompt)
    # Keep renderer import referenced for clarity of inventory source.
    assert callable(render_physical_schema)


def test_metrics_clarifications_and_relative_time_present(
    built_prompt: BuiltPrompt,
) -> None:
    system = built_prompt.system_instructions
    for metric in MetricId:
        assert metric.value in system
    for clarification in ClarificationId:
        assert clarification.value in system
    assert "relative_time_of_day" in system
    assert "default_as_of" in system
    assert "2026-03-15" in built_prompt.user_content


def test_no_seed_literals_or_anchor_labels(built_prompt: BuiltPrompt) -> None:
    text = _full_text(built_prompt)
    forbidden = [
        "Kings Harbor Arena",
        "Tidewater Amphitheater",
        "Harbor Kings vs Northshore Tide",
        "ORD-00001",
        "A1 —",
        "A13",
        "A14",
        "7,270,000",
        "7270000",
        "6,460,000",
        "810,000",
    ]
    for item in forbidden:
        assert item not in text, item


def test_no_secrets_providers_or_paths(built_prompt: BuiltPrompt) -> None:
    text = _full_text(built_prompt)
    assert "OPENAI" not in text
    assert "GROQ" not in text
    assert "openai" not in text.lower()
    assert "groq" not in text.lower()
    assert "api_key" not in text.lower()
    assert "/home/" not in text
    assert "\\\\" not in text
    assert "gpt-" not in text.lower()
