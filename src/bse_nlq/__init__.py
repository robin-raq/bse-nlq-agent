"""Natural language query agent for the Brooklyn Sports and Entertainment exercise.

Translates a plain-English question into SQL with a foundation model, validates
that SQL as untrusted input, executes it read-only against SQLite, and returns a
concise answer alongside the SQL that ran.

No application behavior is implemented yet. See ARCHITECTURE.md for the approved
design and docs/planning/decisions.md for the decisions it rests on.
"""
