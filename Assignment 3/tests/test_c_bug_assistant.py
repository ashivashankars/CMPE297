"""Offline tests for (c). The scripted model drives the *real* ticket MCP server
(spawned over stdio by ADK's McpToolset) against a throw-away SQLite DB."""
import asyncio
import sys

import pytest
from fake_llm import ScriptedLlm, run_agent

sys.path.insert(0, "bug_assistant_agent/mcp_server")
import ticket_db  # noqa: E402


@pytest.fixture()
def agent(tmp_path, monkeypatch):
    from bug_assistant_agent import config
    monkeypatch.setattr(config, "TICKETS_DB", str(tmp_path / "t.db"))
    from bug_assistant_agent import tools
    from google.adk.agents import LlmAgent
    from bug_assistant_agent import prompts
    return LlmAgent(name="BugBuddy", model="gemini-2.5-flash", instruction=prompts.INSTRUCTION,
                    tools=[tools.get_current_date, tools.ticket_mcp_toolset()]), tmp_path


def test_similarity_finds_the_right_ticket(tmp_path):
    conn = ticket_db.connect(str(tmp_path / "x.db"))
    top = ticket_db.similarity_search(conn, "app crashes when I schedule brewing over midnight", 3)
    assert "midnight" in top[0]["title"] and top[0]["distance"] < 0.6
    assert top[0]["distance"] <= top[1]["distance"]


def test_mcp_triage_flow(agent):
    ag, tmp = agent
    ag.model = ScriptedLlm([
        ("call", "search_tickets", {"query": "users charged twice for subscription renewal"}),
        ("call", "create_new_ticket", {"title": "Espresso Pro steam wand leaks",
                                       "description": "Steam wand drips water after brewing.",
                                       "priority": "P2 - Medium"}),
        ("call", "update_ticket_priority", {"ticket_id": 15, "priority": "P9"}),   # invalid -> error
        ("call", "update_ticket_status", {"ticket_id": 15, "status": "In Progress"}),
        ("call", "get_tickets_by_date_range", {"start_date": "2026-10-01", "end_date": "2099-01-01"}),
        "Done: ticket 15 created and moved to In Progress.",
    ])
    events, s, _ = asyncio.run(run_agent(ag, "triage please"))
    responses = {}
    for req in ag.model.requests[1:]:
        fr = req.contents[-1].parts[0].function_response
        responses.setdefault(fr.name, []).append(fr.response)

    def payload(r):  # MCP results come back as structured content or JSON text
        import json
        if "structuredContent" in r and r["structuredContent"]:
            return r["structuredContent"]
        return json.loads(r["content"][0]["text"])

    dup = payload(responses["search_tickets"][0])["results"][0]
    assert "charges customers twice" in dup["title"]
    created = payload(responses["create_new_ticket"][0])
    assert created["status"] == "created" and created["ticket_id"] == 15
    assert payload(responses["update_ticket_priority"][0])["status"] == "error"
    assert payload(responses["update_ticket_status"][0])["status"] == "updated"
    recent = payload(responses["get_tickets_by_date_range"][0])["results"]
    assert any(t["ticket_id"] == 15 and t["status"] == "In Progress" for t in recent)
    assert events[-1].content.parts[0].text.startswith("Done")
