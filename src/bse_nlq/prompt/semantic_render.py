"""Render business meaning from validated semantic metadata."""

from __future__ import annotations

from bse_nlq.metadata.models import (
    APPLICATION_TABLES,
    ClarificationId,
    MetricId,
    SemanticMetadata,
    UnsupportedId,
)


def render_semantic_context(metadata: SemanticMetadata) -> str:
    """Render model-facing semantics without seed literals or out-of-scope fields.

    Includes metrics, clarification policies, unsupported relative-time policy,
    conventions, join guidance, and prompt-visible column meanings.
    """
    lines: list[str] = ["## Semantic metadata", ""]

    lines.append("### Conventions")
    conventions = metadata.conventions
    lines.append(f"- timezone: {conventions.timezone}")
    lines.append(f"- timestamp_format: {conventions.timestamp_format}")
    lines.append(
        f"- timestamps_have_offset: {str(conventions.timestamps_have_offset).lower()}"
    )
    lines.append(f"- default_as_of: {conventions.default_as_of}")
    lines.append(f"- date_ranges: {conventions.date_ranges}")
    lines.append(
        "- upcoming_inclusive_of_as_of: "
        f"{str(conventions.upcoming_inclusive_of_as_of).lower()}"
    )
    lines.append(
        "- upcoming_requires_scheduled: "
        f"{str(conventions.upcoming_requires_scheduled).lower()}"
    )
    lines.append(f"- rounding_rule: {conventions.rounding_rule}")
    lines.append("- unit_rules:")
    for rule in conventions.unit_rules:
        lines.append(f"  - {rule}")
    if conventions.notes:
        lines.append("- notes:")
        for note in conventions.notes:
            lines.append(f"  - {note}")
    lines.append("")

    lines.append("### Metrics")
    for metric_id in sorted(MetricId, key=lambda item: item.value):
        metric = metadata.metrics[metric_id]
        lines.append(f"- {metric.metric_id.value}:")
        lines.append(f"  - description: {metric.description}")
        lines.append(f"  - expression: {metric.expression}")
        lines.append(f"  - unit: {metric.unit.value}")
        if metric.filters:
            lines.append("  - filters: " + ", ".join(sorted(metric.filters)))
        if metric.notes:
            for note in metric.notes:
                lines.append(f"  - note: {note}")
    lines.append("")

    lines.append("### Clarification policies")
    lines.append(
        "These question shapes must return status clarification_required "
        "with nonempty clarification and null sql. Silent defaults are forbidden."
    )
    for clarification_id in sorted(ClarificationId, key=lambda item: item.value):
        policy = metadata.clarifications[clarification_id]
        lines.append(f"- {policy.clarification_id.value}:")
        lines.append(f"  - description: {policy.description}")
        if policy.options:
            lines.append("  - options: " + ", ".join(policy.options))
        if policy.requires:
            lines.append("  - requires: " + ", ".join(policy.requires))
        lines.append(
            "  - silent_default_forbidden: "
            f"{str(policy.silent_default_forbidden).lower()}"
        )
    lines.append("")

    lines.append("### Unsupported policies")
    lines.append(
        "These question shapes must return status unsupported with nonempty "
        "explanation and null sql. Do not invent a clock or time-of-day default."
    )
    for unsupported_id in sorted(UnsupportedId, key=lambda item: item.value):
        unsupported_policy = metadata.unsupported[unsupported_id]
        lines.append(f"- {unsupported_policy.unsupported_id.value}:")
        lines.append(f"  - description: {unsupported_policy.description}")
        if unsupported_policy.examples:
            lines.append("  - examples:")
            for example in unsupported_policy.examples:
                lines.append(f"    - {example}")
        lines.append(
            "  - invent_default_forbidden: "
            f"{str(unsupported_policy.invent_default_forbidden).lower()}"
        )
    lines.append("")

    lines.append("### Join guidance")
    for join in sorted(
        metadata.join_guidance,
        key=lambda item: (
            item.from_table,
            item.from_column,
            item.to_table,
            item.to_column,
        ),
    ):
        lines.append(
            f"- {join.from_table}.{join.from_column} -> "
            f"{join.to_table}.{join.to_column}: {join.note}"
        )
    lines.append("")

    lines.append("### Tables and columns")
    for table_name in APPLICATION_TABLES:
        table = metadata.tables[table_name]
        lines.append(f"#### {table_name}")
        lines.append(f"- description: {table.description}")
        for note in table.notes:
            if "order_ref" in note:
                continue
            lines.append(f"- note: {note}")
        for column_name in sorted(table.columns):
            column = table.columns[column_name]
            if not column.in_prompt:
                continue
            lines.append(f"- {column_name}: {column.description}")
            if column.unit is not None:
                lines.append(f"  - unit: {column.unit.value}")
            if column.synonyms:
                lines.append("  - synonyms: " + ", ".join(column.synonyms))
            for note in column.notes:
                if "order_ref" in note:
                    continue
                lines.append(f"  - note: {note}")
            for item in column.excluded_use:
                lines.append(f"  - excluded_use: {item}")
            for item in column.allowed_analytical_use:
                lines.append(f"  - allowed_analytical_use: {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
