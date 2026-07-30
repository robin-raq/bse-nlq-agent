"""First-proof red test: the semantic metadata API must exist as a package import.

This test is intentionally written before the implementation. It fails with
ImportError / ModuleNotFoundError until the metadata loading API is created.
"""

from bse_nlq.metadata import load_semantic_metadata


def test_load_semantic_metadata_is_importable() -> None:
    assert callable(load_semantic_metadata)
