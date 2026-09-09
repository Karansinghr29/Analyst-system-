"""
observability.py -- Phase 11. Correlation ids, structured audit (no business values), counters.
"""
from __future__ import annotations

import json
import sys
import threading
import uuid
from collections import Counter


class Observability:
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        self._lock = threading.Lock()
        self.counters = Counter()

    def new_request_id(self, incoming: str = "") -> str:
        raw = (incoming or "").strip()
        if raw and len(raw) <= 128 and raw.isprintable() and all(c not in raw for c in "\r\n"):
            return raw
        return str(uuid.uuid4())

    def inc(self, name, n=1):
        with self._lock:
            self.counters[name] += n

    def snapshot(self):
        with self._lock:
            return dict(self.counters)

    def audit(self, **fields):
        """JSON line. Callers must not pass question text, values, tokens, or SQL."""
        line = json.dumps(fields, default=str, separators=(",", ":"))
        with self._lock:
            print(line, file=self.stream)

    def note_trust(self, level: str):
        if level:
            self.inc(f"trust.{level}")

    def note_llm_fallback(self):
        self.inc("llm.fallback_to_deterministic")

    def note_quarantine(self):
        self.inc("source.quarantine")


OBS = Observability()
