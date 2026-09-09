"""
live_connector.py -- Phase 11/13. Read-only transports for a live database.

Two transports, both GET/SELECT-only by construction:

  * SupabaseRestTransport -- HTTP GET against PostgREST. No write method exists.
    Phase 13: complete Range/Content-Range pagination; fail closed on truncation
    or unknown totals; evidence-manifest allowlist only.
  * PostgresReadOnlyTransport -- psycopg connection with default_transaction_read_only.

Neither is constructed at import. Credentials are read only when a transport is
explicitly built. A missing credential yields UNAVAILABLE, not a fabricated pass.
Service-role keys are refused.
"""
from __future__ import annotations

import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from api.data_source import DataSourceError, ROOT

ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_SUPABASE_KEY = "SUPABASE_READONLY_KEY"   # preferred
ENV_SUPABASE_ANON = "SUPABASE_ANON_KEY"      # accepted; still GET-only in this process
ENV_DATABASE_URL = "DATABASE_URL"
ENV_SUPABASE_DB = "SUPABASE_DB_URL"
ENV_SERVICE_ROLE = "SUPABASE_SERVICE_ROLE_KEY"

PAGE_SIZE = 1000

_WRITE_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|COPY|CALL|"
    r"EXECUTE|MERGE|VACUUM|REINDEX|CLUSTER|COMMENT|SECURITY)\b",
    re.IGNORECASE,
)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ALLOWED = None


def relation_from_logical(logical_name: str) -> tuple[str, str]:
    """public.journal_entries -> ('public', 'journal_entries')."""
    name = (logical_name or "").strip()
    if "." in name:
        schema, table = name.split(".", 1)
    else:
        schema, table = "public", name
    if not _IDENT.match(schema) or not _IDENT.match(table):
        raise DataSourceError("Refusing a non-identifier relation name.")
    return schema, table


def allowed_relations():
    """public base tables and views from the evidence manifest. Not an open catalog."""
    global _ALLOWED
    if _ALLOWED is not None:
        return _ALLOWED
    path = os.path.join(ROOT, "evidence", "file_manifest.csv")
    names = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("class") not in ("base_table", "view"):
                continue
            logical = (r.get("logical_name") or "").strip()
            if not logical:
                continue
            schema, table = relation_from_logical(logical if "." in logical else "public." + logical)
            if schema != "public":
                continue
            names.add(f"{schema}.{table}")
    _ALLOWED = frozenset(names)
    return _ALLOWED


def assert_relation_allowed(logical_name: str):
    schema, table = relation_from_logical(logical_name)
    if schema != "public":
        raise DataSourceError("Refusing a non-public live relation.")
    key = f"{schema}.{table}"
    if key not in allowed_relations():
        raise DataSourceError("Relation is not in the evidence allowlist.")
    return schema, table


def parse_content_range(header: str):
    """Return (start, end, total). Unknown totals and missing headers fail closed."""
    if not header or not str(header).strip():
        raise DataSourceError("Pagination failed: missing Content-Range.")
    h = str(header).strip()
    if " " in h and not h.startswith("*") and not (h[0].isdigit() or h[0] == "*"):
        h = h.split(" ", 1)[-1]
    if "/" not in h:
        raise DataSourceError("Pagination failed: malformed Content-Range.")
    span, total_s = h.rsplit("/", 1)
    if total_s == "*":
        raise DataSourceError("Pagination failed: unknown total.")
    try:
        total = int(total_s)
    except ValueError as e:
        raise DataSourceError("Pagination failed: malformed Content-Range total.") from e
    if total < 0:
        raise DataSourceError("Pagination failed: negative total.")
    if span == "*":
        return None, None, total
    if "-" not in span:
        raise DataSourceError("Pagination failed: malformed Content-Range span.")
    a, b = span.split("-", 1)
    try:
        return int(a), int(b), total
    except ValueError as e:
        raise DataSourceError("Pagination failed: malformed Content-Range span.") from e


class ReadOnlyTransport:
    kind = "abstract"

    def available(self) -> bool:
        return False

    def fetch_table(self, logical_name: str, *, limit: int | None = None) -> list[dict]:
        raise NotImplementedError

    def row_count(self, logical_name: str) -> int:
        raise NotImplementedError

    def columns(self, logical_name: str) -> tuple:
        raise NotImplementedError


def _refuse_service_role(key: str):
    svc = os.environ.get(ENV_SERVICE_ROLE) or ""
    if key and svc and key == svc:
        raise DataSourceError("Service-role keys are refused by the live connector.")


class SupabaseRestTransport(ReadOnlyTransport):
    """PostgREST GET. There is no post/patch/delete on this class."""

    kind = "supabase_rest"

    def __init__(self, url: str = None, key: str = None, opener=None, page_size: int = None):
        self.url = (url or os.environ.get(ENV_SUPABASE_URL) or "").rstrip("/")
        self.key = key or os.environ.get(ENV_SUPABASE_KEY) or os.environ.get(ENV_SUPABASE_ANON) or ""
        _refuse_service_role(self.key)
        self._opener = opener
        self.page_size = int(page_size or PAGE_SIZE)
        if self.page_size <= 0:
            raise DataSourceError("Invalid page size.")

    def available(self):
        return bool(self.url and self.key)

    def _headers(self, schema, extra=None):
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Accept-Profile": schema,
            "Range-Unit": "items",
        }
        if extra:
            headers.update(extra)
        return headers

    def _get(self, table: str, query: str, extra_headers=None, schema="public"):
        if not self.available():
            raise DataSourceError("Supabase REST transport has no URL or key.")
        target = f"{self.url}/rest/v1/{urllib.parse.quote(table)}?{query}"
        req = urllib.request.Request(
            target, headers=self._headers(schema, extra_headers), method="GET")
        try:
            opener = self._opener
            if opener is not None:
                resp = opener.open(req, timeout=30)
                body = resp.read()
                rows = json.loads(body.decode("utf-8") or "[]")
                return resp, rows
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return resp, json.loads(body.decode("utf-8") or "[]")
        except urllib.error.HTTPError as e:
            raise DataSourceError(f"Supabase REST refused GET {table}: HTTP {e.code}") from e
        except urllib.error.URLError:
            raise DataSourceError("Supabase REST unreachable.") from None
        except DataSourceError:
            raise
        except Exception:
            raise DataSourceError("Supabase REST request failed.") from None

    def _probe(self, schema, table):
        extra = {"Prefer": "count=exact", "Range": "0-0"}
        resp, rows = self._get(table, "select=*", extra_headers=extra, schema=schema)
        cr = resp.headers.get("Content-Range") or resp.headers.get("content-range") or ""
        _, _, total = parse_content_range(cr)
        if not isinstance(rows, list):
            raise DataSourceError("Supabase REST returned a non-list payload.")
        cols = tuple(rows[0].keys()) if rows else ()
        return total, cols

    def row_count(self, logical_name):
        schema, table = assert_relation_allowed(logical_name)
        total, _ = self._probe(schema, table)
        return total

    def columns(self, logical_name):
        schema, table = assert_relation_allowed(logical_name)
        total, cols = self._probe(schema, table)
        if cols:
            return cols
        if total == 0:
            return ()
        raise DataSourceError("Live relation has rows but no columns (schema drift).")

    def fetch_table(self, logical_name, *, limit=None):
        schema, table = assert_relation_allowed(logical_name)
        total, cols = self._probe(schema, table)
        if limit is not None:
            total = min(total, int(limit))
        if total == 0:
            return []
        if not cols:
            raise DataSourceError("Pagination failed: cannot order an unprobed relation.")
        order_col = "id" if "id" in cols else cols[0]
        if not _IDENT.match(str(order_col)):
            raise DataSourceError("Pagination failed: cannot determine a safe order column.")
        gathered = []
        start = 0
        while start < total:
            end = min(start + self.page_size - 1, total - 1)
            extra = {
                "Prefer": "count=exact",
                "Range": f"{start}-{end}",
            }
            q = f"select=*&order={urllib.parse.quote(str(order_col))}.asc"
            resp, rows = self._get(table, q, extra_headers=extra, schema=schema)
            if not isinstance(rows, list):
                raise DataSourceError("Supabase REST returned a non-list payload.")
            cr = resp.headers.get("Content-Range") or resp.headers.get("content-range") or ""
            _, _, page_total = parse_content_range(cr)
            if page_total < total and limit is None:
                raise DataSourceError("Pagination failed: Content-Range total changed between pages.")
            expected = end - start + 1
            if len(rows) != expected:
                raise DataSourceError("Pagination failed: truncated or partial page.")
            gathered.extend(rows)
            start = end + 1
        if limit is None and len(gathered) != total:
            raise DataSourceError(
                f"Pagination failed: fetched {len(gathered)} rows != reported total {total}.")
        if limit is not None:
            gathered = gathered[: int(limit)]
        return gathered


class PostgresReadOnlyTransport(ReadOnlyTransport):
    """Optional psycopg transport. Write SQL is refused before it reaches the server."""

    kind = "postgres_readonly"

    def __init__(self, dsn: str = None):
        self.dsn = dsn or os.environ.get(ENV_DATABASE_URL) or os.environ.get(ENV_SUPABASE_DB) or ""
        self._conn = None

    def available(self):
        return bool(self.dsn)

    def _connect(self):
        if self._conn is not None:
            return self._conn
        try:
            import psycopg
        except ImportError:
            try:
                import psycopg2 as psycopg  # noqa: F401
            except ImportError as e:
                raise DataSourceError(
                    "No psycopg driver installed. Use Supabase REST or install psycopg."
                ) from e
        try:
            import psycopg
            self._conn = psycopg.connect(self.dsn, autocommit=True)
            with self._conn.cursor() as cur:
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            return self._conn
        except ImportError:
            import psycopg2
            self._conn = psycopg2.connect(self.dsn)
            self._conn.set_session(readonly=True, autocommit=True)
            return self._conn
        except Exception:
            raise DataSourceError("Postgres read-only connection failed.") from None

    def _execute(self, sql, params=None):
        if _WRITE_SQL.search(sql):
            raise DataSourceError("Write/DDL SQL is refused by the read-only connector.")
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in (cur.description or ())]
        rows = cur.fetchall() if cur.description else []
        cur.close()
        return cols, rows

    def fetch_table(self, logical_name, *, limit=None):
        schema, table = assert_relation_allowed(logical_name)
        sql = f'SELECT * FROM "{schema}"."{table}" ORDER BY 1'
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        cols, rows = self._execute(sql)
        return [dict(zip(cols, row)) for row in rows]

    def row_count(self, logical_name):
        schema, table = assert_relation_allowed(logical_name)
        _, rows = self._execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        return int(rows[0][0]) if rows else 0

    def columns(self, logical_name):
        schema, table = assert_relation_allowed(logical_name)
        _, rows = self._execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (schema, table))
        return tuple(r[0] for r in rows)


def transport_from_env() -> ReadOnlyTransport | None:
    """Pick a transport if credentials exist. Does not connect at import."""
    rest = SupabaseRestTransport()
    if rest.available():
        return rest
    pg = PostgresReadOnlyTransport()
    if pg.available():
        return pg
    return None
