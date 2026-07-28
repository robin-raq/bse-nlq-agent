"""Package import smoke test.

Proves the restructuring produced an importable, installed package. Deliberately
does not exercise application behavior, because none is implemented yet.
"""

import importlib


def test_bse_nlq_package_imports() -> None:
    module = importlib.import_module("bse_nlq")
    assert module.__name__ == "bse_nlq"
