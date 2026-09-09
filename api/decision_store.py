"""
decision_store.py -- where an owner's decisions about their own business are recorded.

The evidence is immutable and so is the gate's reading of it. What an owner CAN record is what
they have decided to do about a disagreement the evidence cannot settle: that they are looking
into it, or that management has chosen one competing definition as the business definition.

That record changes nothing upstream. It does not select a definition inside the engine, does
not resolve a conflict, does not move a trust level, and is never read back into a calculation.
A measure whose definitions disagree still shows every definition and still carries its posture
after management has chosen one -- because the disagreement in the records is a fact, and the
choice is a policy sitting beside it. The two must not be confused, and keeping the note here
rather than in the semantic layer is what keeps them apart.

WHERE IT IS KEPT
----------------

By default: the same SQLite file as the conversation store -- one durable local file, no
external service, which is right for a machine that keeps its disk.

A deployment whose filesystem does not survive a restart is a different case. Several hosting
platforms give a container no persistent disk at all, so a SQLite file there is not storage --
it is a cache that silently empties on the next deploy, and the owner's recorded decisions
would disappear without anything reporting that they had. So when `DATABASE_URL` names a
Postgres database, the same table is kept there instead.

Same model either way: the same five columns, the same statuses, the same one-row-per-item
contract, the same refusal to store an unknown status. Nothing about what a decision MEANS
changes with where it is written, and neither backend is read back into a calculation.
"""
import json
import os
import sqlite3
import time

from api.conversation_store import DEFAULT_DB

ENV_DATABASE_URL = "DATABASE_URL"

OPEN = "open"
UNDER_REVIEW = "under_review"
RESOLVED = "resolved"
STATUSES = (OPEN, UNDER_REVIEW, RESOLVED)

STATUS_LABELS = {
    OPEN: "Open",
    UNDER_REVIEW: "Under review",
    RESOLVED: "Resolved",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS owner_decisions (
    item_key    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    decided_by  TEXT NOT NULL DEFAULT '',
    updated_at  REAL NOT NULL
);
"""


class DecisionStore:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def all(self):
        """Every recorded decision, keyed by the queue item it belongs to."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_key, status, note, decided_by, updated_at FROM owner_decisions"
            ).fetchall()
        return {r["item_key"]: {"status": r["status"],
                                "status_label": STATUS_LABELS.get(r["status"], "Open"),
                                "note": r["note"], "decided_by": r["decided_by"],
                                "updated_at": r["updated_at"]} for r in rows}

    def record(self, item_key, status, note="", decided_by=""):
        """Record where a decision stands. Raises on an unknown status rather than storing one:
        a status the rest of the product cannot render is not a record, it is a corruption."""
        key = str(item_key or "").strip()
        if not key:
            raise ValueError("A decision must name the item it is about.")
        if status not in STATUSES:
            raise ValueError(f"Unknown status {status!r}.")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO owner_decisions (item_key, status, note, decided_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(item_key) DO UPDATE SET "
                "status=excluded.status, note=excluded.note, decided_by=excluded.decided_by, "
                "updated_at=excluded.updated_at",
                (key, status, str(note or "")[:2000], str(decided_by or "")[:200], time.time()))
            conn.commit()
        return self.all().get(key)

    def clear(self, item_key):
        with self._connect() as conn:
            conn.execute("DELETE FROM owner_decisions WHERE item_key = ?", (str(item_key),))
            conn.commit()


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS owner_decisions (
    item_key    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    decided_by  TEXT NOT NULL DEFAULT '',
    updated_at  DOUBLE PRECISION NOT NULL
);
"""


class PostgresDecisionStore:
    """The same store, on a managed database that outlives the container.

    Deliberately the same class surface as `DecisionStore` -- `all`, `record`, `clear`, with the
    same arguments, the same validation and the same return shapes -- so the service, the API and
    the frontend cannot tell which one they are talking to. The only difference is where the row
    is written.

    `psycopg` is imported when this store is constructed, never at module import, so a deployment
    that does not use Postgres does not need the driver installed.
    """

    def __init__(self, dsn):
        import psycopg                                        # noqa: F401  (deployment-only)
        self._psycopg = psycopg
        self.dsn = dsn
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_PG_SCHEMA)
            conn.commit()

    def _connect(self):
        return self._psycopg.connect(self.dsn, connect_timeout=10)

    def all(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT item_key, status, note, decided_by, updated_at "
                            "FROM owner_decisions")
                rows = cur.fetchall()
        return {r[0]: {"status": r[1],
                       "status_label": STATUS_LABELS.get(r[1], "Open"),
                       "note": r[2], "decided_by": r[3], "updated_at": r[4]} for r in rows}

    def record(self, item_key, status, note="", decided_by=""):
        key = str(item_key or "").strip()
        if not key:
            raise ValueError("A decision must name the item it is about.")
        if status not in STATUSES:
            raise ValueError(f"Unknown status {status!r}.")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO owner_decisions "
                    "(item_key, status, note, decided_by, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (item_key) DO UPDATE SET "
                    "status=EXCLUDED.status, note=EXCLUDED.note, "
                    "decided_by=EXCLUDED.decided_by, updated_at=EXCLUDED.updated_at",
                    (key, status, str(note or "")[:2000], str(decided_by or "")[:200],
                     time.time()))
            conn.commit()
        return self.all().get(key)

    def clear(self, item_key):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM owner_decisions WHERE item_key = %s", (str(item_key),))
            conn.commit()


def decision_store(db_path=DEFAULT_DB):
    """The store this deployment should use.

    Postgres when `DATABASE_URL` is set, SQLite otherwise. It FAILS rather than falling back: a
    deployment that asked for a durable database and got a file in a container would lose the
    owner's decisions on the next deploy and report nothing, which is the failure this choice
    exists to prevent.
    """
    dsn = (os.environ.get(ENV_DATABASE_URL) or "").strip()
    if not dsn:
        return DecisionStore(db_path)
    return PostgresDecisionStore(dsn)
