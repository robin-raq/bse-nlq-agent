"""Errors raised while loading or reconciling semantic metadata."""


class MetadataError(Exception):
    """Base class for semantic-metadata failures."""


class MetadataValidationError(MetadataError):
    """The packaged metadata document is malformed or incomplete."""


class MetadataReconciliationError(MetadataError):
    """Metadata references do not match SQLite introspection."""
