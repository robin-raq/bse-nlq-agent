"""Independent seed-literal fingerprints derived from docs/planning/seed-manifest.md.

These SHA-256 digests pin the production tuples in ``seed_data`` without
comparing the loaded database to the same module that loads it. They do not
parse Markdown at runtime.

Regeneration (intentional manifest change only)::

    uv run python - <<'PY'
    import hashlib, json
    from bse_nlq.db import seed_data as sd
    def fp(rows):
        payload = json.dumps(
            [list(r) for r in rows], separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    for name, rows in [
        ("VENUES", sd.VENUES),
        ("EVENTS", sd.EVENTS),
        ("TICKET_TIERS", sd.TICKET_TIERS),
        ("ORDERS", sd.ORDERS),
        ("ORDER_ITEMS", sd.ORDER_ITEMS),
        ("REFUNDS", sd.REFUNDS),
    ]:
        print(name, fp(rows))
    PY

Then replace the constants below after reviewing the manifest diff.
"""

from __future__ import annotations

import hashlib
import json

from bse_nlq.db import seed_data

# Digests of JSON-normalized tuple rows from docs/planning/seed-manifest.md
# (transcribed into seed_data.py). See module docstring for regeneration.
_EXPECTED_FINGERPRINTS: dict[str, str] = {
    "VENUES": "0503890a9d46516a612a4cbb74c69b3cb732bfc94c16863a11a0ac8f3500ef8b",
    "EVENTS": "1c5ede76da5914c87f9d10c7afd41899f8b142b406a8d004ae40f2941ea3c198",
    "TICKET_TIERS": "ee782fefe309eccfe206ab2485c40a653a073db2376af050947352d4e88d5e1b",
    "ORDERS": "ed843b36fb6269f70f2e02a5d742e9f95de8cbae43dc58104710227ddeb3e952",
    "ORDER_ITEMS": "1a4ab396f0352cce5288afa74f26d8a63e4d5023193de02d77bc4139ca3483e1",
    "REFUNDS": "1cf92aed61f28b3fbb396b9ef952ab4fd4b0195c577930fe0c8ac8f3c3fe47b6",
}


def _fingerprint(rows: tuple[tuple[object, ...], ...]) -> str:
    payload = json.dumps(
        [list(row) for row in rows],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_seed_literal_fingerprints_match_manifest_contract() -> None:
    actual = {
        "VENUES": _fingerprint(seed_data.VENUES),
        "EVENTS": _fingerprint(seed_data.EVENTS),
        "TICKET_TIERS": _fingerprint(seed_data.TICKET_TIERS),
        "ORDERS": _fingerprint(seed_data.ORDERS),
        "ORDER_ITEMS": _fingerprint(seed_data.ORDER_ITEMS),
        "REFUNDS": _fingerprint(seed_data.REFUNDS),
    }
    assert actual == _EXPECTED_FINGERPRINTS
