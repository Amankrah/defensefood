"""
SQLite-backed persistence for the agent subsystem.

Three tables:

* ``briefs``       — finished briefs, cached by ``(use_case, target_key, snapshot_hash)``.
* ``audit_log``    — every agentic turn (LLM messages, tool calls, tool results)
                     for evidence display + post-hoc replay.
* ``cost_ledger``  — per-day aggregates by (use_case, provider, model) for the
                     cost dashboard.

The schema is created with ``CREATE TABLE IF NOT EXISTS`` so :func:`init_db` is
idempotent and safe to call from the FastAPI ``lifespan`` startup hook.

Design notes:
  * No ORM. The schema is small (3 tables) and the access patterns are simple
    inserts plus a couple of selects.
  * JSON columns carry structured data; reads use ``json.loads`` so callers see
    Python dicts/lists.
  * Snapshot hashes are produced by :mod:`defensefood.agent.snapshot`; the cache
    treats them as opaque strings.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from defensefood.agent.config import get_config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    use_case        TEXT NOT NULL,
    target_key      TEXT NOT NULL,
    snapshot_hash   TEXT NOT NULL,
    brief_json      TEXT NOT NULL,
    model           TEXT NOT NULL,
    provider        TEXT NOT NULL,
    cost_usd        REAL NOT NULL,
    latency_ms      INTEGER NOT NULL,
    created_at      REAL NOT NULL,
    UNIQUE(use_case, target_key, snapshot_hash)
);

CREATE INDEX IF NOT EXISTS idx_briefs_lookup
    ON briefs(use_case, target_key, snapshot_hash);

CREATE TABLE IF NOT EXISTS audit_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id         INTEGER,
    use_case         TEXT NOT NULL,
    target_key       TEXT,
    role             TEXT NOT NULL,
    content_json     TEXT NOT NULL,
    tool_calls_json  TEXT,
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    created_at       REAL NOT NULL,
    FOREIGN KEY (brief_id) REFERENCES briefs(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_brief
    ON audit_log(brief_id);

CREATE TABLE IF NOT EXISTS cost_ledger (
    day        TEXT NOT NULL,
    use_case   TEXT NOT NULL,
    provider   TEXT NOT NULL,
    model      TEXT NOT NULL,
    tokens_in  INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    usd        REAL NOT NULL,
    PRIMARY KEY (day, use_case, provider, model)
);
"""


def _resolve_db_path(db_path: str) -> Path:
    """Resolve a relative db_path under backend/ (where pyproject lives)."""
    p = Path(db_path)
    if p.is_absolute():
        return p
    # Walk up to find the backend dir (the one containing pyproject.toml).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent / p
    # Fallback: relative to cwd (rare; tests usually run from backend/).
    return Path.cwd() / p


def init_db(db_path: Optional[str] = None) -> Path:
    """Create the schema if missing. Idempotent. Returns the resolved Path."""
    cfg = get_config()
    resolved = _resolve_db_path(db_path or cfg.db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(resolved) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    return resolved


_INITIALIZED_DBS: set[str] = set()


@contextmanager
def _connect(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    cfg = get_config()
    resolved = _resolve_db_path(db_path or cfg.db_path)
    # Lazy schema init so the cache works in TestClient contexts (where the
    # FastAPI lifespan doesn't run) and in unit tests that point at a fresh
    # temp database. init_db() is idempotent; we only need to do it once
    # per database path per process.
    key = str(resolved)
    if key not in _INITIALIZED_DBS:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn0 = sqlite3.connect(resolved)
        try:
            conn0.executescript(_SCHEMA)
            conn0.commit()
        finally:
            conn0.close()
        _INITIALIZED_DBS.add(key)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── briefs ────────────────────────────────────────────────────────────────


def get_cached_brief(
    use_case: str,
    target_key: str,
    snapshot_hash: str,
    *,
    ttl_seconds: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Return the cached brief dict (parsed JSON) or None.

    A brief is considered fresh if ``created_at + ttl_seconds >= now``. The
    default TTL is taken from :attr:`AgentConfig.brief_cache_ttl_seconds`.
    """
    cfg = get_config()
    ttl = ttl_seconds if ttl_seconds is not None else cfg.brief_cache_ttl_seconds
    cutoff = time.time() - ttl
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT brief_json, created_at, model, provider, cost_usd, latency_ms "
            "FROM briefs "
            "WHERE use_case = ? AND target_key = ? AND snapshot_hash = ? "
            "AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (use_case, target_key, snapshot_hash, cutoff),
        ).fetchone()
    if row is None:
        return None
    return {
        "brief": json.loads(row["brief_json"]),
        "cached": True,
        "created_at": row["created_at"],
        "model": row["model"],
        "provider": row["provider"],
        "cost_usd": row["cost_usd"],
        "latency_ms": row["latency_ms"],
    }


def store_brief(
    *,
    use_case: str,
    target_key: str,
    snapshot_hash: str,
    brief: dict[str, Any],
    model: str,
    provider: str,
    cost_usd: float,
    latency_ms: int,
    db_path: Optional[str] = None,
) -> int:
    """Insert (or replace, by UNIQUE constraint) a brief; return the row id."""
    payload = json.dumps(brief, ensure_ascii=False, default=str)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO briefs "
            "(use_case, target_key, snapshot_hash, brief_json, model, provider, "
            " cost_usd, latency_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                use_case,
                target_key,
                snapshot_hash,
                payload,
                model,
                provider,
                cost_usd,
                latency_ms,
                time.time(),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    return int(row["id"])


# ── audit log ─────────────────────────────────────────────────────────────


def append_audit(
    *,
    use_case: str,
    target_key: Optional[str],
    role: str,
    content: Any,
    tool_calls: Optional[list[dict[str, Any]]] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    brief_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> None:
    """Append a single turn to the audit log.

    ``role`` is one of ``"system"``, ``"user"``, ``"assistant"``, ``"tool"``,
    ``"verifier"``.
    """
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_log "
            "(brief_id, use_case, target_key, role, content_json, "
            " tool_calls_json, tokens_in, tokens_out, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                brief_id,
                use_case,
                target_key,
                role,
                json.dumps(content, ensure_ascii=False, default=str),
                json.dumps(tool_calls, ensure_ascii=False, default=str)
                if tool_calls is not None
                else None,
                tokens_in,
                tokens_out,
                time.time(),
            ),
        )


def get_audit(brief_id: int, db_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Return all audit-log rows for a brief, ordered by created_at ascending."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, role, content_json, tool_calls_json, "
            "       tokens_in, tokens_out, created_at "
            "FROM audit_log "
            "WHERE brief_id = ? "
            "ORDER BY created_at ASC, id ASC",
            (brief_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "role": r["role"],
                "content": json.loads(r["content_json"]),
                "tool_calls": json.loads(r["tool_calls_json"])
                if r["tool_calls_json"]
                else None,
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "created_at": r["created_at"],
            }
        )
    return out


# ── cost ledger ───────────────────────────────────────────────────────────


def record_cost(
    *,
    use_case: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    usd: float,
    day: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Add to today's running totals for ``(use_case, provider, model)``."""
    if day is None:
        day = date.today().isoformat()
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT tokens_in, tokens_out, usd FROM cost_ledger "
            "WHERE day = ? AND use_case = ? AND provider = ? AND model = ?",
            (day, use_case, provider, model),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO cost_ledger "
                "(day, use_case, provider, model, tokens_in, tokens_out, usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day, use_case, provider, model, tokens_in, tokens_out, usd),
            )
        else:
            conn.execute(
                "UPDATE cost_ledger "
                "SET tokens_in = tokens_in + ?, "
                "    tokens_out = tokens_out + ?, "
                "    usd = usd + ? "
                "WHERE day = ? AND use_case = ? AND provider = ? AND model = ?",
                (
                    tokens_in,
                    tokens_out,
                    usd,
                    day,
                    use_case,
                    provider,
                    model,
                ),
            )


def daily_costs(
    day: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return ledger rows for a single day (defaults to today)."""
    if day is None:
        day = date.today().isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT use_case, provider, model, tokens_in, tokens_out, usd "
            "FROM cost_ledger WHERE day = ? ORDER BY usd DESC",
            (day,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── snapshot hashing ──────────────────────────────────────────────────────


def snapshot_hash(parts: Iterable[Any]) -> str:
    """Stable SHA-256 over the given parts (each str-coerced).

    Used by the brief cache to invalidate when the corpus or scoring config
    changes. Callers typically pass:

        snapshot_hash([
            len(state.corridor_metrics),
            state.scoring_config.model_dump_json(),
            state.trade_period,
        ])
    """
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]  # 64 bits is plenty for cache keying
