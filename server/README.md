# Server

The HTTP API and the background worker. The server keeps a cache and index of
each collection, syncs it with the owner's Google Sheet, generates printable
labels and draws captions on photos. The spreadsheet stays the source of truth.

Planned stack: Python, FastAPI, Pydantic, SQLAlchemy with Alembic migrations,
PostgreSQL (SQLite for a minimal install).

Not started yet.
