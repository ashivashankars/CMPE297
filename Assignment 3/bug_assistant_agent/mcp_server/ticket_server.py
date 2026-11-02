"""QuantumRoast bug-ticket MCP server (stdio transport).

Exposes the ticket database as MCP tools. ADK connects to it through
McpToolset + StdioConnectionParams, but any MCP client (Claude Desktop, Gemini
CLI, MCP Inspector) can use it too:

    npx @modelcontextprotocol/inspector python bug_assistant_agent/mcp_server/ticket_server.py
"""
from __future__ import annotations

import functools
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ticket_db as db  # noqa: E402

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations  # noqa: E402

DB_PATH = os.getenv("TICKETS_DB", str(Path(__file__).resolve().parents[1] / "data" / "tickets.db"))
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

mcp = FastMCP("quantumroast-tickets")
conn = db.connect(DB_PATH)
_LOCK = threading.Lock()


def locked(fn):
    """Serialise DB access: the MCP runtime may call sync tools from worker threads."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return wrapper


def _err(msg: str) -> dict:
    return {"status": "error", "error": msg}


@mcp.tool(annotations=READ)
@locked
def search_tickets(query: str, limit: int = 3) -> dict:
    """Semantic-style search for tickets similar to a bug description. Each result has
    a `distance` (0 = identical, 1 = unrelated); distance <= 0.6 suggests a likely
    duplicate or closely related ticket."""
    return {"results": db.similarity_search(conn, query, limit)}


@mcp.tool(annotations=READ)
@locked
def get_ticket_by_id(ticket_id: int) -> dict:
    """Retrieve full details of one ticket by its numeric ID."""
    r = db.rows(conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)))
    return {"ticket": r[0]} if r else _err(f"Ticket {ticket_id} not found")


@mcp.tool(annotations=READ)
@locked
def get_tickets_by_assignee(assignee: str) -> dict:
    """List tickets whose assignee email contains the given text."""
    return {"results": db.rows(conn.execute(
        "SELECT * FROM tickets WHERE assignee LIKE ? ORDER BY priority", (f"%{assignee}%",)))}


@mcp.tool(annotations=READ)
@locked
def get_tickets_by_status(status: str) -> dict:
    """List tickets with a status: 'Open', 'In Progress', 'Resolved' or 'Closed'."""
    return {"results": db.rows(conn.execute(
        "SELECT * FROM tickets WHERE status LIKE ? ORDER BY priority", (f"%{status}%",)))}


@mcp.tool(annotations=READ)
@locked
def get_tickets_by_priority(priority: str) -> dict:
    """List tickets with a priority such as 'P0', 'P1 - High', 'P2', 'P3 - Low'."""
    return {"results": db.rows(conn.execute(
        "SELECT * FROM tickets WHERE priority LIKE ? ORDER BY creation_time DESC", (f"%{priority}%",)))}


@mcp.tool(annotations=READ)
@locked
def get_tickets_by_date_range(start_date: str, end_date: str, date_field: str = "creation_time") -> dict:
    """List tickets created or updated between two dates (inclusive, YYYY-MM-DD).
    date_field is 'creation_time' or 'updated_time'."""
    if date_field not in ("creation_time", "updated_time"):
        return _err("date_field must be 'creation_time' or 'updated_time'")
    return {"results": db.rows(conn.execute(
        f"SELECT * FROM tickets WHERE date({date_field}) BETWEEN date(?) AND date(?) ORDER BY {date_field}",
        (start_date, end_date)))}


@mcp.tool(annotations=WRITE)
@locked
def create_new_ticket(title: str, description: str, assignee: str = "",
                      priority: str = "P3 - Low", status: str = "Open") -> dict:
    """Create a new bug ticket. Priority: 'P0 - Critical', 'P1 - High', 'P2 - Medium',
    'P3 - Low'. Returns the new ticket_id plus any existing tickets that look like
    duplicates so the user can review them."""
    if priority not in db.PRIORITIES:
        return _err(f"priority must be one of {db.PRIORITIES}")
    if status not in db.STATUSES:
        return _err(f"status must be one of {db.STATUSES}")
    if not title.strip() or not description.strip() or title.strip() == description.strip():
        return _err("title and description are required and must differ")
    now = db._now()
    cur = conn.execute(
        "INSERT INTO tickets (title, description, assignee, priority, status, creation_time, updated_time)"
        " VALUES (?,?,?,?,?,?,?)", (title.strip(), description.strip(), assignee, priority, status, now, now))
    conn.commit()
    dupes = [t for t in db.similarity_search(conn, f"{title} {description}", 4)
             if t["ticket_id"] != cur.lastrowid and t["distance"] <= 0.6]
    return {"status": "created", "ticket_id": cur.lastrowid, "possible_duplicates": dupes}


def _update(field: str, value: str, ticket_id: int) -> dict:
    cur = conn.execute(f"UPDATE tickets SET {field} = ?, updated_time = ? WHERE ticket_id = ?",
                       (value, db._now(), ticket_id))
    conn.commit()
    if cur.rowcount == 0:
        return _err(f"Ticket {ticket_id} not found")
    return {"status": "updated", "ticket_id": ticket_id, "field": field, "new_value": value}


@mcp.tool(annotations=WRITE)
@locked
def update_ticket_status(ticket_id: int, status: str) -> dict:
    """Set a ticket's status to 'Open', 'In Progress', 'Resolved' or 'Closed'."""
    if status not in db.STATUSES:
        return _err(f"status must be one of {db.STATUSES}")
    return _update("status", status, ticket_id)


@mcp.tool(annotations=WRITE)
@locked
def update_ticket_priority(ticket_id: int, priority: str) -> dict:
    """Set a ticket's priority: 'P0 - Critical', 'P1 - High', 'P2 - Medium' or 'P3 - Low'."""
    if priority not in db.PRIORITIES:
        return _err(f"priority must be one of {db.PRIORITIES}")
    return _update("priority", priority, ticket_id)


if __name__ == "__main__":
    mcp.run()  # stdio
