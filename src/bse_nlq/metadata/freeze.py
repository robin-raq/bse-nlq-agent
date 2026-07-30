"""Freeze nested mappings returned by the public metadata API."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


def freeze_mapping[K, V](mapping: Mapping[K, V]) -> MappingProxyType[K, V]:
    """Return a read-only view that rejects item assignment and clear()."""
    return MappingProxyType(dict(mapping))
