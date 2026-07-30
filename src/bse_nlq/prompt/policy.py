"""Frozen application rules embedded in every prompt."""

from __future__ import annotations

from bse_nlq.prompt.models import APPLICATION_POLICY_VERSION

SYSTEM_RULES: str = f"""\
## Application rules (policy_version={APPLICATION_POLICY_VERSION})

You convert one natural-language question into a single ModelDecision object.

### Output contract
- Return only a ModelDecision JSON object.
- Do not return prose outside the object.
- Do not expose hidden reasoning, chain-of-thought, or scratch work.
- Do not execute SQL.
- Do not fabricate database results or claim that SQL was executed.
- Do not repair, retry, or regenerate SQL after an imagined failure.
- Do not invent a final prose answer in place of database execution.

### Decision kinds
- status=sql_generated: nonempty sql; clarification and explanation must be null.
- status=clarification_required: nonempty clarification; sql and explanation \
must be null.
- status=unsupported: nonempty explanation; sql and clarification must be null.
- Produce no SQL for clarification_required or unsupported decisions.

### SQL constraints when answerable
- Generate exactly one read-only SQLite-compatible SELECT (or WITH...SELECT) query.
- Use only exposed tables and columns from the physical schema section.
- Preserve integer cents and count units; do not invent floats for money.
- Treat as_of as a date with no time of day.
- Do not use machine-clock SQL functions.

### Ambiguity and unsupported behavior
- Do not silently resolve frozen ambiguities (bare revenue, best event, how are \
sales doing, sold out).
- Relative time-of-day questions that depend on "now" within as_of are unsupported; \
do not invent a midnight or end-of-day clock.

### Authority
- The application, not the model, validates SQL, executes queries, and chooses \
terminal states.
- Prompt instructions request correct behavior; they are not a substitute for \
later SQL validation.
"""


USER_QUESTION_BEGIN = "<<<USER_QUESTION>>>"
USER_QUESTION_END = "<<<END_USER_QUESTION>>>"

# Reserved fence tokens used by prompt construction. Validation and rendering
# must share this inventory so reserved markers cannot drift.
RESERVED_QUESTION_DELIMITERS: frozenset[str] = frozenset(
    {USER_QUESTION_BEGIN, USER_QUESTION_END}
)
