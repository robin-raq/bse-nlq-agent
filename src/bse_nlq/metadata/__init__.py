"""Semantic metadata sidecar: business meaning for the BSE NLQ schema.

SQLite introspection owns physical structure. This package owns model-facing
meanings, units, metrics, visibility, clarification rules, and join guidance.
"""

from bse_nlq.metadata.errors import (
    MetadataError,
    MetadataReconciliationError,
    MetadataValidationError,
)
from bse_nlq.metadata.loader import (
    load_metadata_document,
    load_semantic_metadata,
    read_packaged_metadata_text,
)
from bse_nlq.metadata.models import (
    APPLICATION_TABLES,
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
from bse_nlq.metadata.reconcile import (
    introspect_application_tables,
    introspect_foreign_keys,
    introspect_generated_columns,
    prompt_excluded_columns,
    prompt_visible_columns,
    reconcile_metadata,
)
from bse_nlq.metadata.validate import parse_metadata_json, validate_metadata_document

__all__ = [
    "APPLICATION_TABLES",
    "ClarificationId",
    "ClarificationPolicy",
    "ColumnMetadata",
    "Conventions",
    "JoinGuidance",
    "MetadataError",
    "MetadataReconciliationError",
    "MetadataValidationError",
    "MetricDefinition",
    "MetricId",
    "SemanticMetadata",
    "TableMetadata",
    "Unit",
    "UnsupportedId",
    "UnsupportedPolicy",
    "introspect_application_tables",
    "introspect_foreign_keys",
    "introspect_generated_columns",
    "load_metadata_document",
    "load_semantic_metadata",
    "parse_metadata_json",
    "prompt_excluded_columns",
    "prompt_visible_columns",
    "read_packaged_metadata_text",
    "reconcile_metadata",
    "validate_metadata_document",
]
