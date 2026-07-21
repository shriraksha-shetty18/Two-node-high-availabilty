"""
db.py

Persists desired cluster state: every workload the Manager knows about,
which node it landed on, and which container ID represents it there.
This survives Manager restarts — on startup it can reconcile against
reality instead of forgetting everything.
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "manager_state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS workloads (
    name TEXT PRIMARY KEY,
    spec_json TEXT NOT NULL,
    node_id TEXT,
    container_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | stopped | failed
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db(path: str = DB_PATH):
    with _connect(path) as conn:
        conn.execute(SCHEMA)


@contextmanager
def _connect(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_workload(name: str, spec: dict, node_id: str = None, container_id: str = None,
                     status: str = "pending", path: str = DB_PATH):
    now = _now()
    with _connect(path) as conn:
        existing = conn.execute("SELECT name FROM workloads WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE workloads SET spec_json=?, node_id=?, container_id=?, status=?, updated_at=?
                   WHERE name=?""",
                (json.dumps(spec), node_id, container_id, status, now, name),
            )
        else:
            conn.execute(
                """INSERT INTO workloads (name, spec_json, node_id, container_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, json.dumps(spec), node_id, container_id, status, now, now),
            )


def get_workload(name: str, path: str = DB_PATH) -> dict | None:
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM workloads WHERE name = ?", (name,)).fetchone()
        return _row_to_dict(row) if row else None


def list_workloads(node_id: str = None, status: str = None, path: str = DB_PATH) -> list[dict]:
    query = "SELECT * FROM workloads WHERE 1=1"
    params = []
    if node_id:
        query += " AND node_id = ?"
        params.append(node_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def delete_workload(name: str, path: str = DB_PATH):
    with _connect(path) as conn:
        conn.execute("DELETE FROM workloads WHERE name = ?", (name,))


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["spec"] = json.loads(d.pop("spec_json"))
    return d
