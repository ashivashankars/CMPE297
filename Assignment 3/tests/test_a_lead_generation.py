"""Offline end-to-end test of the lead generation agent: two user turns drive
the full state machine (intent -> pattern discovery with parallel fan-out ->
lead generation with parallel fan-out -> report artifact)."""
import asyncio
import json

from fake_llm import ScriptedLlm, request_text, run_agent

import lead_generation_agent.agent as A
from lead_generation_agent.sub_agents import pipelines as P

COMPANIES = {"companies": [
    {"company_name": "AlphaPay", "website": "https://alphapay.example", "why_selected": "Series C"},
    {"company_name": "BetaLend", "website": "https://betalend.example", "why_selected": "Acquired"},
]}
PATTERNS = {"summary": "API-first lenders win", "patterns": [
    {"name": "Series B within 3 years", "description": "fast raise", "signal_type": "funding",
     "evidence_companies": ["AlphaPay", "BetaLend"], "weight": 0.8}]}
LEADS = {"leads": [
    {"company_name": "GammaCredit", "rationale": "hiring ML engineers"},
    {"company_name": "DeltaWallet", "rationale": "seed round"}]}


def fanout_researcher(req):
    return "Verified company with funding and hiring signals. Source: https://news.example/x"


def fanout_formatter(req):
    text = request_text(req).split("RESEARCH NOTES")[0]
    for name in ("AlphaPay", "BetaLend", "GammaCredit", "DeltaWallet"):
        if name in text:
            break
    if "PROSPECT" in text or name in ("GammaCredit", "DeltaWallet"):
        return json.dumps({"company_name": name, "is_valid": True, "fit_score": 80 if name == "GammaCredit" else 60,
                           "matched_patterns": ["Series B within 3 years"], "summary": "good fit",
                           "sources": ["https://news.example/x"]})
    return json.dumps({"company_name": name, "is_valid": True, "summary": "real",
                       "funding_signals": ["Series C 2025"], "sources": ["https://news.example/x"]})


def install_fakes():
    P.intent_extractor.model = ScriptedLlm([json.dumps(
        {"intent": "find_patterns", "country": "India", "industry": "Fintech", "k": 2})])
    P.company_finder.model = ScriptedLlm(["AlphaPay ... BetaLend ..."])
    P.company_formatter.model = ScriptedLlm([json.dumps(COMPANIES)])
    P.pattern_synthesizer.model = ScriptedLlm([json.dumps(PATTERNS)])
    P.lead_finder.model = ScriptedLlm(["GammaCredit ... DeltaWallet ..."])
    P.lead_formatter.model = ScriptedLlm([json.dumps(LEADS)])
    P.report_writer.model = ScriptedLlm(["# Lead Generation Report - Fintech, India\n| 1 | GammaCredit | 80 |"])
    for fan in (P.company_research_fanout, P.lead_assessment_fanout):
        fan.researcher_model = ScriptedLlm(responder=fanout_researcher)
        fan.formatter_model = ScriptedLlm(responder=fanout_formatter)


def test_full_research_flow():
    install_fakes()
    A.root_agent.model = ScriptedLlm([
        # turn 1
        ("call", "IntentExtractor", {"request": "Find fintech leads in India, study 2 companies"}),
        ("call", "PatternDiscoveryPipeline", {"request": "Discover success patterns for Fintech in India"}),
        "Here are the patterns... Shall I search for new leads?",
        # turn 2
        ("call", "set_research_parameters", {"m": 2}),
        ("call", "LeadGenerationPipeline", {"request": "Find 2 leads"}),
        "Report saved as lead_report.md",
    ])

    async def go():
        from google.adk.runners import InMemoryRunner
        from google.genai import types
        runner = InMemoryRunner(agent=A.root_agent, app_name="leadgen")
        s = await runner.session_service.create_session(app_name="leadgen", user_id="u")
        async def say(text):
            import time
            from fake_llm import _write_trace
            evs, t0 = [], time.monotonic()
            async for _ev in runner.run_async(user_id="u", session_id=s.id,
                                            new_message=types.Content(role="user", parts=[types.Part(text=text)])):
                evs.append(_ev)
            sess = await runner.session_service.get_session(app_name="leadgen", user_id="u", session_id=s.id)
            _write_trace("leadgen", text, evs, sess, time.monotonic() - t0)
            return sess

        s1 = await say("Find fintech leads in India, study 2 companies")
        assert s1.state["country"] == "India" and s1.state["k"] == 2
        assert s1.state["stage"] == "patterns_ready"
        assert len(s1.state["company_research"]) == 2
        assert s1.state["discovered_patterns"]["patterns"][0]["weight"] == 0.8

        s2 = await say("Yes, find 2 leads")
        assert s2.state["m"] == 2
        assert {r["company_name"] for r in s2.state["lead_research"]} == {"GammaCredit", "DeltaWallet"}
        assert s2.state["stage"] == "leads_ready"
        art = await runner.artifact_service.load_artifact(
            app_name="leadgen", user_id="u", session_id=s.id, filename="lead_report.md")
        assert art is not None and b"GammaCredit" in art.inline_data.data
        await runner.close()

    asyncio.run(go())


def test_parameters_are_clamped():
    from lead_generation_agent.tools import set_research_parameters

    class Ctx:  # minimal ToolContext stand-in
        state = {}
    out = set_research_parameters(Ctx(), k=50, m=0)
    assert out["updated"] == {"k": 10, "m": 1}
