"""SQLite ticket store + lightweight TF-IDF similarity search.

Local stand-in for the reference's Cloud SQL Postgres + pgvector setup so the
whole MCP stack runs on a laptop. The production equivalent (MCP Toolbox for
Databases over Postgres with vector search) lives in deployment/toolbox/.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

PRIORITIES = ("P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low")
STATUSES = ("Open", "In Progress", "Resolved", "Closed")
SEED = Path(__file__).with_name("seed_tickets.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    assignee      TEXT DEFAULT '',
    priority      TEXT NOT NULL DEFAULT 'P3 - Low',
    status        TEXT NOT NULL DEFAULT 'Open',
    creation_time TEXT NOT NULL,
    updated_time  TEXT NOT NULL
);
"""

_STOP = set("a an the and or of to in on for with is are was be it this that when after "
            "from by as at not does do i we you my our its".split())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # MCP servers run sync tools on worker threads; callers serialise access with a lock.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
        for t in json.loads(SEED.read_text()):
            conn.execute(
                "INSERT INTO tickets (title, description, assignee, priority, status, creation_time, updated_time)"
                " VALUES (?,?,?,?,?,?,?)",
                (t["title"], t["description"], t["assignee"], t["priority"], t["status"],
                 t["creation_time"], t["creation_time"]),
            )
        conn.commit()
    return conn


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1]


def similarity_search(conn: sqlite3.Connection, query: str, limit: int = 3) -> list[dict]:
    """Cosine similarity over TF-IDF vectors of title+description. Returns tickets
    with `distance` = 1 - cosine (0 = identical), mirroring pgvector's <=>."""
    tickets = rows(conn.execute("SELECT * FROM tickets"))
    docs = [Counter(_tokens(t["title"] + " " + t["title"] + " " + t["description"])) for t in tickets]
    n = len(docs)
    df = Counter(w for d in docs for w in d)
    idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}

    def vec(counter):
        return {w: c * idf.get(w, math.log(1 + n) + 1) for w, c in counter.items()}

    def cos(a, b):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    q = vec(Counter(_tokens(query)))
    scored = []
    for t, d in zip(tickets, docs):
        t["distance"] = round(1 - cos(q, vec(d)), 3)
        scored.append(t)
    return sorted(scored, key=lambda t: t["distance"])[: max(1, min(limit, 10))]
