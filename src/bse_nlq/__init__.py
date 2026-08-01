"""Natural language query agent for the Brooklyn Sports and Entertainment exercise.

Translates a plain-English question into SQL with a foundation model, validates
that SQL as untrusted input, executes it read-only against SQLite, and returns a
concise answer alongside the SQL that ran.

Implemented so far: physical schema, deterministic seed, semantic metadata,
ModelDecision validation, deterministic prompt construction, the persistent
database builder, the read-only runtime open, and the SQL-policy parsing
foundation (``validate_sql`` / immutable ``ValidatedSql`` with normalize and
fingerprint). Full static authorization (tables, columns, stars, functions,
dates, forbidden constructs), provider adapters, execution, and the CLI remain
pending. See ARCHITECTURE.md for the approved design and
docs/planning/decisions.md for the decisions it rests on.
"""
