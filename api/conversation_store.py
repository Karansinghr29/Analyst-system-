"""
conversation_store.py -- Phase 9 (W2). Durable conversation persistence.

A conversation carries SAFETY state, not just history. Specifically:

  * an open clarification         -- the system is awaiting an answer
  * a recorded definition selection -- the owner explicitly chose one competing definition

If either is lost across a restart, the system does not merely forget context; it becomes
UNSAFE. A reloaded conversation that forgot it was awaiting an answer would read the user's next
message as a fresh question -- and a reply meant as "the ledger one" would be interpreted as a
new question about ledgers. Worse, a forgotten clarification means the pending ambiguity silently
disappears, which is exactly the silent resolution the trust policy forbids.

So persistence round-trips the clarification lifecycle and the selection record, and the Phase 9
validator checks that it does.

SQLite, single file, no external service. Trust posture is deliberately NOT persisted: it is
re-read from the gate on every turn, because a cached trust level is a correctness failure rather
than a stale number.
"""
import json
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field

# Vercel serves the deployment from a read-only filesystem; only the temp directory is writable
# there. Anywhere else (local, Docker/Render) the file stays beside the package, unchanged.
if os.environ.get("VERCEL"):
    DEFAULT_DB = os.path.join(tempfile.gettempdir(), "conversations.db")
else:
    DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "conversations.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    subject         TEXT NOT NULL,
    role_id         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn_index      INTEGER NOT NULL,
    question        TEXT NOT NULL,
    answer_text     TEXT,
    status          TEXT,
    trust_level     TEXT,
    metric_ids      TEXT,
    owner_intent    TEXT,
    request_json    TEXT,
    created_at      REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);
CREATE TABLE IF NOT EXISTS clarifications (
    conversation_id TEXT PRIMARY KEY,
    payload         TEXT NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS definition_selections (
    conversation_id TEXT NOT NULL,
    concept         TEXT NOT NULL,
    payload         TEXT NOT NULL,
    updated_at      REAL NOT NULL,
    PRIMARY KEY (conversation_id, concept)
);
CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, turn_index);
"""


@dataclass
class StoredTurn:
    turn_index: int
    question: str
    answer_text: str = ""
    status: str = ""
    trust_level: str = ""
    metric_ids: tuple = ()
    owner_intent: str = ""
    request: object = None          # LLMPlanRequest, or None for a turn never interpreted
    created_at: float = 0.0


# -- structured-request serialisation -----------------------------------------------------------
#
# Only the fields `ConversationContext.resolve()` actually inherits are persisted. Storing the
# whole object would drag `raw` -- the model's unvalidated text -- into durable state, and
# nothing downstream needs it to resolve a follow-up.

_REQUEST_FIELDS = ("intent", "concept", "metric_ids", "dimensions", "filters", "time_range",
                   "comparison", "requested_output", "explanation_requested",
                   "recommendation_requested")


def _encode_request(request):
    if request is None:
        return None
    out = {}
    for name in _REQUEST_FIELDS:
        value = getattr(request, name, None)
        if isinstance(value, tuple):
            value = list(value)
        out[name] = value
    return json.dumps(out)


def _decode_request(blob):
    if not blob:
        return None
    from engine.structured_output import LLMPlanRequest
    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    kwargs = {}
    for name in _REQUEST_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if name in ("intent", "metric_ids", "dimensions"):
            value = tuple(value or ())
        elif name == "filters":
            value = dict(value or {})
        kwargs[name] = value
    return LLMPlanRequest(**kwargs)


def _column(row, name):
    """Read a column that may be absent in a database created before it existed."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


class ConversationStore:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """Add columns introduced after a database was first created.

        `CREATE TABLE IF NOT EXISTS` does not alter an existing table, so an installation that
        already holds conversations would otherwise keep the old shape and fail on the new
        column. Additive only: no column is dropped and no row is rewritten.
        """
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(turns)")}
        if "request_json" not in have:
            self._conn.execute("ALTER TABLE turns ADD COLUMN request_json TEXT")

    def close(self):
        self._conn.close()

    # -- conversations ------------------------------------------------------------------------

    def create(self, conversation_id, subject, role_id):
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO conversations "
            "(conversation_id, subject, role_id, created_at, updated_at) VALUES (?,?,?,?,?)",
            (conversation_id, subject, role_id, now, now))
        self._conn.commit()
        return conversation_id

    def exists(self, conversation_id):
        row = self._conn.execute(
            "SELECT 1 FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
        return row is not None

    def get(self, conversation_id):
        row = self._conn.execute(
            "SELECT * FROM conversations WHERE conversation_id=?",
            (conversation_id,)).fetchone()
        if row is None:
            return None
        return {
            "conversation_id": row["conversation_id"], "subject": row["subject"],
            "role_id": row["role_id"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "turns": [t.__dict__ for t in self.turns(conversation_id)],
            "awaiting_clarification": self.load_clarification(conversation_id) is not None,
            "definition_selections": list(self.load_selections(conversation_id)),
        }

    # -- turns ----------------------------------------------------------------------------------

    def append_turn(self, conversation_id, question, answer_text="", status="",
                    trust_level="", metric_ids=(), owner_intent="", request=None):
        """Record one turn.

        `request` is the STRUCTURED INTERPRETATION of the question -- concept, metric ids,
        period, intent. It is persisted so a later "Why?" can inherit what the owner was asking
        about. It is not an answer and carries no figure and no trust posture, so restoring it
        cannot re-serve a stale number; the follow-up is re-executed from scratch against the
        gate like any other question.
        """
        now = time.time()
        idx = self._conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 AS n FROM turns WHERE conversation_id=?",
            (conversation_id,)).fetchone()["n"]
        self._conn.execute(
            "INSERT INTO turns (conversation_id, turn_index, question, answer_text, status, "
            "trust_level, metric_ids, owner_intent, request_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (conversation_id, idx, question, answer_text, status, trust_level,
             json.dumps(list(metric_ids)), owner_intent, _encode_request(request), now))
        self._conn.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?",
                           (now, conversation_id))
        self._conn.commit()
        return idx

    def turns(self, conversation_id):
        rows = self._conn.execute(
            "SELECT * FROM turns WHERE conversation_id=? ORDER BY turn_index",
            (conversation_id,)).fetchall()
        return tuple(StoredTurn(
            turn_index=r["turn_index"], question=r["question"],
            answer_text=r["answer_text"] or "", status=r["status"] or "",
            trust_level=r["trust_level"] or "",
            metric_ids=tuple(json.loads(r["metric_ids"] or "[]")),
            owner_intent=r["owner_intent"] or "",
            request=_decode_request(_column(r, "request_json")),
            created_at=r["created_at"]) for r in rows)

    # -- clarification lifecycle (the safety-critical part) -------------------------------------

    def save_clarification(self, conversation_id, pending):
        """Persist an OPEN clarification. Losing this across a restart would make the system
        read the user's answer as a fresh question, and would silently drop a pending ambiguity."""
        payload = json.dumps({
            "trigger": pending.trigger, "question": pending.question,
            "options": list(pending.options),
            "option_metric_ids": list(pending.option_metric_ids),
            "asked_at_turn": pending.asked_at_turn, "state": pending.state,
            "resolution": pending.resolution,
            "resolved_metric_id": pending.resolved_metric_id,
            # The question that triggered the clarification. Without it a selection reply
            # arriving on a later HTTP request has only the word "1" to work from, so "why did
            # collections fall?" came back as a plain collections total -- the definition
            # chosen, the question forgotten.
            "original_question": pending.original_question,
        })
        self._conn.execute(
            "INSERT OR REPLACE INTO clarifications (conversation_id, payload, updated_at) "
            "VALUES (?,?,?)", (conversation_id, payload, time.time()))
        self._conn.commit()

    def load_clarification(self, conversation_id):
        row = self._conn.execute(
            "SELECT payload FROM clarifications WHERE conversation_id=?",
            (conversation_id,)).fetchone()
        if row is None:
            return None
        from engine.conversation_state import PendingClarification
        d = json.loads(row["payload"])
        return PendingClarification(
            trigger=d["trigger"], question=d["question"], options=tuple(d["options"]),
            option_metric_ids=tuple(d["option_metric_ids"]),
            asked_at_turn=d["asked_at_turn"], state=d["state"],
            resolution=d.get("resolution", ""),
            resolved_metric_id=d.get("resolved_metric_id", ""),
            original_question=d.get("original_question", ""))

    def clear_clarification(self, conversation_id):
        self._conn.execute("DELETE FROM clarifications WHERE conversation_id=?",
                           (conversation_id,))
        self._conn.commit()

    # -- explicit definition selections ------------------------------------------------------------

    def save_selection(self, conversation_id, selection):
        payload = json.dumps({
            "concept": selection.concept, "metric_id": selection.metric_id,
            "definition_label": selection.definition_label,
            "selected_at_turn": selection.selected_at_turn,
            "user_text": selection.user_text,
            "alternatives_shown": list(selection.alternatives_shown),
        })
        self._conn.execute(
            "INSERT OR REPLACE INTO definition_selections "
            "(conversation_id, concept, payload, updated_at) VALUES (?,?,?,?)",
            (conversation_id, selection.concept, payload, time.time()))
        self._conn.commit()

    def load_selections(self, conversation_id):
        from engine.conversation_state import DefinitionSelection
        rows = self._conn.execute(
            "SELECT payload FROM definition_selections WHERE conversation_id=?",
            (conversation_id,)).fetchall()
        out = []
        for r in rows:
            d = json.loads(r["payload"])
            out.append(DefinitionSelection(
                concept=d["concept"], metric_id=d["metric_id"],
                definition_label=d["definition_label"],
                selected_at_turn=d["selected_at_turn"], user_text=d["user_text"],
                alternatives_shown=tuple(d["alternatives_shown"])))
        return tuple(out)

    # -- restore into a live context ------------------------------------------------------------------

    def restore_into(self, conversation_id, context):
        """Rehydrate an `engine.conversation_context.ConversationContext`.

        Restores the safety state -- the open clarification and any recorded definition
        selections. Turn history is restored as questions only: a persisted answer is a rendering
        of a past computation, and re-serving it could serve a stale trust posture. Anything the
        engine needs is recomputed.
        """
        from engine.conversation_context import Turn

        pending = self.load_clarification(conversation_id)
        if pending is not None:
            context.pending_clarification = pending
        for sel in self.load_selections(conversation_id):
            context.definition_selections[sel.concept] = sel

        # Turn history, so a follow-up has something to refer back to. Each restored turn
        # carries the QUESTION and its structured interpretation and nothing else: `answer` and
        # `plan` stay None, so no past figure and no past trust posture can be re-served. A
        # follow-up that inherits a concept is re-executed against the gate from scratch.
        for stored in self.turns(conversation_id):
            context.record(Turn(
                question=stored.question,
                request=stored.request,
                plan=None,
                answer=None,
                trust_level="",
                metric_ids=tuple(stored.metric_ids),
            ))
            if stored.owner_intent:
                context.last_owner_intent = stored.owner_intent
        return context

    def persist_from(self, conversation_id, context):
        """Write a live context's safety state back."""
        if context.pending_clarification is not None:
            self.save_clarification(conversation_id, context.pending_clarification)
        else:
            self.clear_clarification(conversation_id)
        for sel in context.definition_selections.values():
            self.save_selection(conversation_id, sel)
