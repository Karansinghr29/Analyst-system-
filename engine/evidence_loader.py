"""
evidence_loader.py -- the engine's evidence-access module.

Deliberately thin: reuses scripts/validation/common.py, which is already the proven,
manifest-driven loader used to produce all 80 checks in validation_summary.csv. Re-implementing
manifest resolution here would risk drift between the engine and the already-validated
reconstruction logic; importing it instead guarantees the engine reads evidence exactly the
way every prior deliverable in this project already reads it.

Adds only what the engine needs beyond common.py: a couple of dtype-safety helpers that several
calculators require (coa_accounts.code as string, not int64 -- see business_logic.md's own
account-code LIKE-pattern discussion) and a single evidence-availability check used by the
Trust Gate / calculators to return "Not determinable from exported evidence." instead of
raising when a required table/view was never exported (e.g. market schema, DQ.032).
"""
import os
import sys
from contextlib import contextmanager
from functools import lru_cache

_VALIDATION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts", "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

from common import (  # noqa: E402
    BASE, MANIFEST_PATH, DUPLICATE_OF, TRUNCATED,
    manifest, _resolve_row, describe, snapshot,
    to_bool, money,
)
from common import load as _uncached_load  # noqa: E402
from common import load_table as _uncached_load_table  # noqa: E402
from common import load_view as _uncached_load_view  # noqa: E402

# A live source may overlay CSV reads ONLY inside RevalidationHarness (temporary) or after
# bind_source has accepted it (serving). Default is the export CSVs.
_SOURCE_STACK = []


def _active_source():
    return _SOURCE_STACK[-1] if _SOURCE_STACK else None


def _clear_evidence_caches():
    _cached_load.cache_clear()
    _cached_load_table.cache_clear()
    _cached_load_view.cache_clear()
    _cached_coa_str.cache_clear()
    try:
        from engine.calculators import ledger as _ledger
        _ledger._excl_cached.cache_clear()
        _ledger._incl_cached.cache_clear()
    except Exception:
        pass
    try:
        from engine import validator as _validator
        _validator._ledger_totals.cache_clear()
    except Exception:
        pass


@contextmanager
def using_source(source):
    """Harness-only overlay. Does not mark the source trusted for serving."""
    _SOURCE_STACK.append(source)
    _clear_evidence_caches()
    try:
        yield source
    finally:
        _SOURCE_STACK.pop()
        _clear_evidence_caches()


def bind_trusted_source(source):
    """Serving-path bind. Caller must already have passed bind_source()."""
    _SOURCE_STACK.clear()
    if source is not None:
        _SOURCE_STACK.append(source)
    _clear_evidence_caches()


def unbind_source():
    _SOURCE_STACK.clear()
    _clear_evidence_caches()


@lru_cache(maxsize=256)
def _cached_load(ref, warn):
    return _uncached_load(ref, warn=warn)


def load(ref, warn=True, **read_csv_kwargs):
    """Cached wrapper around common.load(). A trusted/harness live overlay, when present,
    replaces CSV reads for base tables and views only. Diagnostics and metadata stay on
    the trusted export — they are not live relations."""
    src = _active_source()
    if src is not None and getattr(src, "kind", None) == "live" and hasattr(src, "load_dataframe"):
        try:
            row = _resolve_row(ref)
        except KeyError:
            row = None
        if row is not None and row.get("class") in ("base_table", "view"):
            return src.load_dataframe(ref)
    if read_csv_kwargs:
        return _uncached_load(ref, warn=warn, **read_csv_kwargs)
    return _cached_load(ref, warn).copy()


@lru_cache(maxsize=256)
def _cached_load_table(name):
    return _uncached_load_table(name)


def load_table(name, **kw):
    src = _active_source()
    if src is not None and getattr(src, "kind", None) == "live" and hasattr(src, "load_dataframe"):
        return src.load_dataframe(name)
    if kw:
        return _uncached_load_table(name, **kw)
    return _cached_load_table(name).copy()


@lru_cache(maxsize=256)
def _cached_load_view(name):
    return _uncached_load_view(name)


def load_view(name, **kw):
    src = _active_source()
    if src is not None and getattr(src, "kind", None) == "live" and hasattr(src, "load_dataframe"):
        return src.load_dataframe(name)
    if kw:
        return _uncached_load_view(name, **kw)
    return _cached_load_view(name).copy()


class EvidenceNotAvailable(Exception):
    """Raised when a caller asks for a table/view that was never exported (empty source table,
    or genuinely absent, e.g. market schema -- DQ.032/DQ.029). Calculators must catch this and
    return NOT_DETERMINABLE, never fabricate a substitute value."""


def is_available(ref):
    try:
        _resolve_row(ref)
        return True
    except KeyError:
        return False


@lru_cache(maxsize=1)
def _cached_coa_str():
    coa = _uncached_load_table("coa_accounts")
    coa["code"] = coa["code"].astype(str)
    return coa


def coa_accounts_str_code():
    """coa_accounts.code loaded with code forced to string -- required for any account_code
    LIKE-pattern logic (v_pnl_by_category's 9 buckets, the electricity '515%' pattern, etc.).
    Without this, pandas infers int64 and .str accessor calls silently fail (the exact bug
    caught and fixed while building scripts/validation/validate_expenses.py)."""
    return _cached_coa_str().copy()


def require(ref):
    """Like load(), but raises EvidenceNotAvailable (not KeyError) for the engine's own
    control flow -- calculators catch this specifically to emit NOT_DETERMINABLE."""
    try:
        return load(ref)
    except KeyError as e:
        raise EvidenceNotAvailable(str(e)) from e
