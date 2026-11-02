"""Offline tests for (e): a full shopping journey against the real store MCP
servers (stdio), identity enforcement against a spoofed email, the audit log,
and the human-in-the-loop confirmation on checkout."""
import asyncio
import json

import pytest
from fake_llm import ScriptedLlm, run_agent
from google.adk.agents import LlmAgent

from ecommerce_agent import agent as A
from ecommerce_agent import config, guards, prompts


def make_agent(tmp_path, monkeypatch, confirm: bool, turns):
    monkeypatch.setattr(config, "STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setattr(config, "REQUIRE_ORDER_CONFIRMATION", confirm)
    model = ScriptedLlm(turns)
    return LlmAgent(name="Finn", model=model, instruction=prompts.INSTRUCTION, tools=A.build_tools(),
                    before_agent_callback=guards.init_session, before_tool_callback=guards.enforce_identity,
                    after_tool_callback=guards.audit_tool_call), model


def tool_results(model):
    out = {}
    for req in model.requests[1:]:
        for p in req.contents[-1].parts or []:
            if p.function_response:
                r = p.function_response.response
                if isinstance(r, dict) and r.get("structuredContent"):
                    r = r["structuredContent"]
                elif isinstance(r, dict) and r.get("content"):
                    r = json.loads(r["content"][0]["text"])
                out.setdefault(p.function_response.name, []).append(r)
    return out


def test_shopping_journey(tmp_path, monkeypatch):
    ag, model = make_agent(tmp_path, monkeypatch, confirm=False, turns=[
        ("call", "search_products", {"query": "cushioned running shoes", "max_price": 160}),
        ("call", "add_to_shopping_list", {"user_email": "sam@example.com",   # spoof attempt
                                          "product_name": "Clifton 10", "size": "9", "color": "White"}),
        ("call", "show_shopping_list", {"user_email": "whoever"}),
        ("call", "find_nearby_stores", {"user_email": "x"}),
        ("call", "list_delivery_methods", {"store_name": "Palo Alto"}),
        ("call", "place_order", {"user_email": "x", "store_name": "Palo Alto", "delivery_method": "Express"}),
        ("call", "update_order_delivery_method", {"user_email": "x", "order_id": 1, "delivery_method": "Store Pickup"}),
        ("call", "check_order_status", {"user_email": "x"}),
        "Your order #1 is placed for pickup.",
    ])
    events, s, _ = asyncio.run(run_agent(ag, "I need running shoes", app_name="shop"))
    r = tool_results(model)
    assert r["search_products"][0]["products"][0]["name"] in ("Pegasus 41", "Clifton 10", "Glycerin 22")
    # identity enforced: item landed in the demo user's (Alex) list, not Sam's
    assert r["show_shopping_list"][0]["user"] == "Alex Rivera"
    assert r["show_shopping_list"][0]["subtotal"] == 149.99
    assert r["find_nearby_stores"][0]["stores"][0]["name"] == "GenAI Sports Palo Alto"
    placed = r["place_order"][0]
    assert placed["status"] == "placed" and placed["total_amount"] == pytest.approx(164.98)
    assert r["update_order_delivery_method"][0]["total_amount"] == pytest.approx(149.99)
    assert r["check_order_status"][0]["orders"][0]["delivery_method"] == "Store Pickup"
    assert s.state["user:email"] == "alex@example.com"
    assert [e["tool"] for e in s.state["audit_log"]][:2] == ["add_to_shopping_list", "place_order"]
    assert all("user_email" not in e["args"] for e in s.state["audit_log"])


def test_checkout_requires_human_confirmation(tmp_path, monkeypatch):
    ag, model = make_agent(tmp_path, monkeypatch, confirm=True, turns=[
        ("call", "place_order", {"user_email": "x", "store_name": "Palo Alto", "delivery_method": "Express"}),
        "Please confirm the order.",
    ])
    events, s, _ = asyncio.run(run_agent(ag, "buy it", app_name="shop"))
    calls = [p.function_call.name for e in events if e.content for p in e.content.parts or [] if p.function_call]
    assert "adk_request_confirmation" in calls          # adk web shows an approve/reject dialog
    assert "audit_log" not in s.state                    # nothing was executed


def test_stock_and_ownership_rules(tmp_path, monkeypatch):
    import importlib
    import sys
    monkeypatch.setenv("STORE_DB", str(tmp_path / "rules.db"))
    sys.path.insert(0, "ecommerce_agent/mcp_server")
    srv = importlib.reload(importlib.import_module("store_server"))
    srv.add_to_shopping_list("alex@example.com", "Clifton 10", "9", "White", 10)   # only 4 in Palo Alto
    out = srv.place_order("alex@example.com", "Palo Alto", "Standard")
    assert out["status"] == "error" and "Insufficient stock" in out["error"]
    assert srv.show_shopping_list("alex@example.com")["items"]                       # rolled back, list kept
    srv.remove_from_shopping_list("alex@example.com", "Clifton 10")
    srv.add_to_shopping_list("alex@example.com", "Clifton 10", "9", "White", 1)
    oid = srv.place_order("alex@example.com", "Palo Alto", "Standard")["order_id"]
    assert srv.cancel_order("sam@example.com", oid)["status"] == "error"            # not Sam's order
    assert srv.cancel_order("alex@example.com", oid)["status"] == "cancelled"
    assert srv.cancel_order("alex@example.com", oid)["status"] == "error"           # already cancelled
