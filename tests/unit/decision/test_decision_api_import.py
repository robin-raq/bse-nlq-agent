"""First-proof red test: the ModelDecision validation API must be importable.

This test is intentionally written before the implementation. It fails with
ImportError / ModuleNotFoundError until the decision package exists.
"""

from bse_nlq.decision import parse_model_decision_json


def test_parse_model_decision_json_is_importable() -> None:
    assert callable(parse_model_decision_json)
