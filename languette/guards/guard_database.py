"""guard-database: DROP, TRUNCATE and other DDL.

These ride in a quoted argument or a file, so they need a SQL-level scan beyond
the shell scanner. A stub: not registered in run.py and not wired in hooks.json,
so it judges nothing yet.
"""

NAME = "guard-database"
