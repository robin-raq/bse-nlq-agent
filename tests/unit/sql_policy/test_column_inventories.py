"""U2 Slice 4A: canonical physical and prompt-visible column inventories."""

from __future__ import annotations

import pytest
from policy_test_helpers import EMPTY_COLUMNS, EMPTY_VISIBLE

from bse_nlq.metadata.models import APPLICATION_TABLES, REQUIRED_SEMANTIC_COLUMNS
from bse_nlq.sql_policy import (
    SqlRejectedError,
    SqlRejectionReason,
    validate_sql,
)
from bse_nlq.sql_policy.column_inventory import (
    CanonicalColumnInventory,
    canonicalize_column_inventories,
)
from bse_nlq.sql_policy.scope_policy import fold_sqlite_identifier

PHYSICAL_TABLES: frozenset[str] = frozenset(APPLICATION_TABLES)

# Full physical inventory matching the committed schema (PK columns included).
REAL_PHYSICAL_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("venues", "venue_id"),
        ("venues", "name"),
        ("venues", "district"),
        ("venues", "capacity"),
        ("events", "event_id"),
        ("events", "venue_id"),
        ("events", "name"),
        ("events", "category"),
        ("events", "status"),
        ("events", "start_local"),
        ("events", "event_date"),
        ("events", "capacity"),
        ("events", "attendance"),
        ("ticket_tiers", "tier_id"),
        ("ticket_tiers", "event_id"),
        ("ticket_tiers", "tier_name"),
        ("ticket_tiers", "face_value_cents"),
        ("orders", "order_id"),
        ("orders", "order_ref"),
        ("orders", "channel"),
        ("orders", "status"),
        ("orders", "purchased_at"),
        ("order_items", "order_item_id"),
        ("order_items", "order_id"),
        ("order_items", "tier_id"),
        ("order_items", "quantity"),
        ("order_items", "unit_price_cents"),
        ("order_items", "line_gross_cents"),
        ("refunds", "refund_id"),
        ("refunds", "order_item_id"),
        ("refunds", "refunded_qty"),
        ("refunds", "refund_amount_cents"),
        ("refunds", "refunded_at"),
        ("refunds", "reason"),
    }
)

REAL_VISIBLE_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    pair for pair in REAL_PHYSICAL_COLUMNS if pair != ("orders", "order_ref")
)


def _canonicalize(
    *,
    tables: frozenset[str] = PHYSICAL_TABLES,
    physical: frozenset[tuple[str, str]] = REAL_PHYSICAL_COLUMNS,
    visible: frozenset[tuple[str, str]] = REAL_VISIBLE_COLUMNS,
) -> CanonicalColumnInventory:
    return canonicalize_column_inventories(
        physical_tables=tables,
        physical_columns=physical,
        prompt_visible_columns=visible,
    )


# --- Red 1: physical-column inventory shape ---


def test_physical_columns_must_be_frozenset() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns={("events", "id")},  # type: ignore[arg-type]
            prompt_visible_columns=frozenset(),
        )


def test_physical_columns_require_two_element_tuples() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events",)}),  # type: ignore[arg-type]
            prompt_visible_columns=frozenset(),
        )
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id", "extra")}),  # type: ignore[arg-type]
            prompt_visible_columns=frozenset(),
        )


def test_physical_columns_require_string_components() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", 1)}),  # type: ignore[arg-type]
            prompt_visible_columns=frozenset(),
        )


@pytest.mark.parametrize(
    "pair",
    [
        ("", "id"),
        ("events", ""),
        (" events", "id"),
        ("events ", "id"),
        ("events", " id"),
        ("events", "id "),
    ],
)
def test_physical_columns_reject_empty_or_padded_names(
    pair: tuple[str, str],
) -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({pair}),
            prompt_visible_columns=frozenset(),
        )


def test_empty_physical_columns_inventory_allowed() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset(),
        prompt_visible_columns=frozenset(),
    )
    assert inventory.physical_columns == frozenset()
    assert inventory.prompt_visible_columns == frozenset()


def test_physical_table_may_have_zero_listed_columns() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events", "orders"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=frozenset({("events", "id")}),
    )
    assert ("orders", "id") not in inventory.physical_columns
    assert ("events", "id") in inventory.physical_columns


def test_caller_owned_physical_frozenset_unchanged() -> None:
    physical = frozenset({("EVENTS", "ID")})
    visible = frozenset({("events", "id")})
    tables = frozenset({"events"})
    canonicalize_column_inventories(
        physical_tables=tables,
        physical_columns=physical,
        prompt_visible_columns=visible,
    )
    assert physical == frozenset({("EVENTS", "ID")})
    assert visible == frozenset({("events", "id")})
    assert tables == frozenset({"events"})


# --- Red 2: table canonicalization ---


def test_lowercase_table_component_canonicalized() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=frozenset({("events", "id")}),
    )
    assert inventory.physical_columns == frozenset({("events", "id")})


def test_uppercase_table_component_uses_physical_tables_spelling() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("EVENTS", "id")}),
        prompt_visible_columns=frozenset({("EVENTS", "id")}),
    )
    assert inventory.physical_columns == frozenset({("events", "id")})
    assert inventory.prompt_visible_columns == frozenset({("events", "id")})


def test_canonical_column_spelling_comes_from_physical_inventory() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "Event_ID")}),
        prompt_visible_columns=frozenset({("EVENTS", "event_id")}),
    )
    assert inventory.physical_columns == frozenset({("events", "Event_ID")})
    assert inventory.prompt_visible_columns == frozenset({("events", "Event_ID")})


def test_column_identity_uses_ascii_fold() -> None:
    assert fold_sqlite_identifier("Event_ID") == "event_id"
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "Event_ID")}),
        prompt_visible_columns=frozenset({("events", "EVENT_ID")}),
    )
    assert inventory.prompt_visible_columns == frozenset({("events", "Event_ID")})


def test_unknown_physical_table_in_physical_columns_rejected() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("orders", "id")}),
            prompt_visible_columns=frozenset(),
        )


# --- Red 3: physical-column collisions ---


def test_ascii_case_collision_in_physical_columns_rejected() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset(
                {
                    ("events", "id"),
                    ("EVENTS", "ID"),
                }
            ),
            prompt_visible_columns=frozenset(),
        )


def test_strasse_and_strasse_non_ascii_remain_distinct() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset(
            {
                ("events", "straße"),
                ("events", "strasse"),
            }
        ),
        prompt_visible_columns=frozenset(
            {
                ("events", "straße"),
                ("events", "strasse"),
            }
        ),
    )
    assert inventory.physical_columns == frozenset(
        {
            ("events", "straße"),
            ("events", "strasse"),
        }
    )


def test_strasse_case_variants_collide_under_ascii_fold() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset(
                {
                    ("events", "Straße"),
                    ("events", "straße"),
                }
            ),
            prompt_visible_columns=frozenset(),
        )


def test_cafe_and_cafe_accent_remain_distinct() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset(
            {
                ("events", "café"),
                ("events", "CAFÉ"),
            }
        ),
        prompt_visible_columns=frozenset(
            {
                ("events", "café"),
                ("events", "CAFÉ"),
            }
        ),
    )
    # ASCII fold does not equate é/É; both identities remain.
    assert len(inventory.physical_columns) == 2


def test_fold_helper_preserves_required_ascii_behavior() -> None:
    assert fold_sqlite_identifier("events") == fold_sqlite_identifier("EVENTS")
    assert fold_sqlite_identifier("Straße") == fold_sqlite_identifier("straße")
    assert fold_sqlite_identifier("straße") != fold_sqlite_identifier("strasse")
    assert fold_sqlite_identifier("café") != fold_sqlite_identifier("CAFÉ")
    assert fold_sqlite_identifier("Σ") != fold_sqlite_identifier("σ")
    assert fold_sqlite_identifier("İ") != fold_sqlite_identifier("i")


# --- Red 4: prompt-visible subset ---


def test_visible_exact_physical_column_accepted() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=frozenset({("events", "id")}),
    )
    assert inventory.prompt_visible_columns == frozenset({("events", "id")})


def test_visible_ascii_case_variant_canonicalized() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=frozenset({("EVENTS", "ID")}),
    )
    assert inventory.prompt_visible_columns == frozenset({("events", "id")})


def test_unknown_visible_table_rejected() -> None:
    with pytest.raises(TypeError, match="prompt_visible_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id")}),
            prompt_visible_columns=frozenset({("orders", "id")}),
        )


def test_unknown_visible_column_rejected() -> None:
    with pytest.raises(TypeError, match="prompt_visible_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id")}),
            prompt_visible_columns=frozenset({("events", "missing")}),
        )


def test_visible_column_not_in_physical_rejected() -> None:
    with pytest.raises(TypeError, match="prompt_visible_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id")}),
            prompt_visible_columns=frozenset({("events", "name")}),
        )


def test_empty_visible_inventory_allowed() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=frozenset(),
    )
    assert inventory.prompt_visible_columns == frozenset()
    assert inventory.physical_columns == frozenset({("events", "id")})


def test_visible_ascii_case_collision_rejected() -> None:
    with pytest.raises(TypeError, match="prompt_visible_columns"):
        canonicalize_column_inventories(
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id"), ("events", "name")}),
            prompt_visible_columns=frozenset(
                {
                    ("events", "id"),
                    ("EVENTS", "ID"),
                }
            ),
        )


def test_caller_owned_visible_frozenset_unchanged() -> None:
    visible = frozenset({("EVENTS", "ID")})
    canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("events", "id")}),
        prompt_visible_columns=visible,
    )
    assert visible == frozenset({("EVENTS", "ID")})


def test_real_schema_counts_34_physical_33_visible() -> None:
    inventory = _canonicalize()
    assert len(inventory.physical_columns) == 34
    assert len(inventory.prompt_visible_columns) == 33
    assert inventory.physical_columns == (
        inventory.prompt_visible_columns | frozenset({("orders", "order_ref")})
    )


def test_orders_order_ref_physical_but_not_prompt_visible() -> None:
    inventory = _canonicalize()
    assert ("orders", "order_ref") in inventory.physical_columns
    assert ("orders", "order_ref") not in inventory.prompt_visible_columns


def test_generated_columns_physical_and_visible() -> None:
    inventory = _canonicalize()
    assert ("events", "event_date") in inventory.physical_columns
    assert ("events", "event_date") in inventory.prompt_visible_columns
    assert ("order_items", "line_gross_cents") in inventory.physical_columns
    assert ("order_items", "line_gross_cents") in inventory.prompt_visible_columns


def test_real_schema_covers_required_semantic_columns() -> None:
    inventory = _canonicalize()
    for table, columns in REQUIRED_SEMANTIC_COLUMNS.items():
        for column in columns:
            assert (table, column) in inventory.physical_columns
            if (table, column) == ("orders", "order_ref"):
                assert (table, column) not in inventory.prompt_visible_columns
            else:
                assert (table, column) in inventory.prompt_visible_columns


def test_inventory_mapping_is_immutable() -> None:
    inventory = _canonicalize(
        tables=frozenset({"events"}),
        physical=frozenset({("events", "id")}),
        visible=frozenset({("events", "id")}),
    )
    with pytest.raises((TypeError, AttributeError)):
        inventory.physical_by_identity[("events", "id")] = ("events", "x")  # type: ignore[index]
    with pytest.raises(AttributeError):
        inventory.visible_identities.add(("events", "x"))  # type: ignore[attr-defined]


# --- Red 10 (partial): public validate_sql inventory activation ---


def test_validate_sql_rejects_unknown_physical_table_in_columns() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        validate_sql(
            "SELECT 1",
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("orders", "id")}),
            prompt_visible_columns=frozenset(),
        )


def test_inventory_type_error_precedes_empty_sql_rejection() -> None:
    with pytest.raises(TypeError, match="physical_columns"):
        validate_sql(
            "",
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("bad",)}),  # type: ignore[arg-type]
            prompt_visible_columns=frozenset(),
        )


def test_validate_sql_rejects_visible_not_subset() -> None:
    with pytest.raises(TypeError, match="prompt_visible_columns"):
        validate_sql(
            "SELECT 1",
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id")}),
            prompt_visible_columns=frozenset({("events", "name")}),
        )


def test_validate_sql_rejects_unqualified_excluded_column() -> None:
    # Slice 4C binds unqualified columns; order_ref exists physically but is
    # excluded from the prompt-visible inventory, so it is now rejected
    # instead of silently passing through with an empty referenced_columns.
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            "SELECT order_ref FROM orders",
            physical_tables=PHYSICAL_TABLES,
            physical_columns=REAL_PHYSICAL_COLUMNS,
            prompt_visible_columns=REAL_VISIBLE_COLUMNS,
        )
    assert exc_info.value.reason is SqlRejectionReason.EXCLUDED_COLUMN


def test_validate_sql_rejects_unknown_unqualified_column() -> None:
    # Slice 4C binds unqualified columns against the local scope; an unknown
    # name is now rejected instead of silently passing through.
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            "SELECT nonexistent_column FROM events",
            physical_tables=PHYSICAL_TABLES,
            physical_columns=REAL_PHYSICAL_COLUMNS,
            prompt_visible_columns=REAL_VISIBLE_COLUMNS,
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_COLUMN


def test_validate_sql_does_not_expose_inventory_on_result() -> None:
    result = validate_sql(
        "SELECT 1 FROM events",
        physical_tables=PHYSICAL_TABLES,
        physical_columns=REAL_PHYSICAL_COLUMNS,
        prompt_visible_columns=REAL_VISIBLE_COLUMNS,
    )
    assert not hasattr(result, "physical_columns")
    assert not hasattr(result, "prompt_visible_columns")
    assert not hasattr(result, "output_schemas")


# --- False-authority ---


def test_unicode_casefold_not_used_for_collision() -> None:
    # Surviving if casefold() were used: straße and strasse would collide.
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset(
            {
                ("events", "straße"),
                ("events", "strasse"),
            }
        ),
        prompt_visible_columns=frozenset(),
    )
    assert len(inventory.physical_columns) == 2


def test_sql_spelling_is_not_canonical_identity() -> None:
    inventory = canonicalize_column_inventories(
        physical_tables=frozenset({"events"}),
        physical_columns=frozenset({("EVENTS", "ID")}),
        prompt_visible_columns=frozenset({("Events", "Id")}),
    )
    assert inventory.physical_columns == frozenset({("events", "ID")})
    assert inventory.prompt_visible_columns == frozenset({("events", "ID")})


def test_existing_empty_inventory_helpers_still_work() -> None:
    result = validate_sql(
        "SELECT 1",
        physical_tables=frozenset(),
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
    assert result.referenced_tables == frozenset()
    assert result.referenced_columns == frozenset()
