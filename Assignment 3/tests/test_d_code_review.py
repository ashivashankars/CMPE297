"""Offline tests for (d): deterministic tools + a two-turn run through the review
pipeline and the iterative fix loop (2 attempts, second one escalates)."""
import asyncio
import json

from fake_llm import ScriptedLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

import code_review_assistant.agent as A
from code_review_assistant import tools
from code_review_assistant.sub_agents import fix_pipeline as F
from code_review_assistant.sub_agents import review_pipeline as R

BAD = "def Avg(nums=[]):\n  return sum(nums)/len(nums)\n"
PARTIAL_FIX = "```python\ndef avg(nums):\n  return sum(nums)/len(nums)\n```"
GOOD_FIX = ('```python\ndef avg(nums: list[float]) -> float:\n    """Mean of nums (0.0 if empty)."""\n'
            '    if not nums:\n        return 0.0\n    return sum(nums) / len(nums)\n```')


def test_tools_detect_problems():
    s = tools.structure_of(BAD)
    assert s["risk_flags"]["mutable_default_args"] == ["Avg"]
    st = tools.style_of(BAD)
    assert st["score"] < 100 and "N802" in st["issue_breakdown"]
    assert tools.style_of(tools.extract_code(GOOD_FIX))["score"] == 100


def test_syntax_error_is_reported():
    class Ctx:
        state = {}
    out = asyncio.run(tools.analyze_code_structure("def f(:\n  pass", Ctx()))
    assert out["status"] == "syntax_error" and out["line"] == 1


def test_review_then_fix_flow():
    R.test_runner.code_executor = None          # sandbox executor needs real Gemini
    F.fix_test_runner.code_executor = None
    A.root_agent.model = ScriptedLlm([
        ("call", "transfer_to_agent", {"agent_name": "CodeReviewPipeline"}),
        ("call", "transfer_to_agent", {"agent_name": "CodeFixPipeline"}),
    ])
    R.code_analyzer.model = ScriptedLlm([("call", "analyze_code_structure", {"code": BAD}), "1 function, risk: mutable default"])
    R.style_checker.model = ScriptedLlm([("call", "check_code_style", {"code": ""}), "style ok-ish"])
    R.test_runner.model = ScriptedLlm([json.dumps({"verdict": {"status": "BUGGY"}, "critical_issues": [{"description": "ZeroDivisionError on []"}]})])
    R.feedback_synthesizer.model = ScriptedLlm([
        ("call", "search_past_feedback", {}),
        ("call", "save_review_report", {"feedback_markdown": "## Summary\nDivision by zero."}),
        "## Summary\nDivision by zero.\n\n**I can fix these issues for you. Would you like me to?**",
    ])
    F.code_fixer.model = ScriptedLlm([PARTIAL_FIX, GOOD_FIX])
    F.fix_test_runner.model = ScriptedLlm(['{"verdict": {"status": "BUGGY"}}', '{"verdict": {"status": "WORKING"}}'])
    F.fix_validator.model = ScriptedLlm([
        ("call", "validate_fixed_style", {}), ("call", "compile_fix_report", {}), "PARTIAL - empty list still crashes",
        ("call", "validate_fixed_style", {}), ("call", "compile_fix_report", {}), ("call", "exit_fix_loop", {}), "SUCCESSFUL",
    ])
    F.fix_synthesizer.model = ScriptedLlm([("call", "save_fix_report", {"summary_markdown": "SUCCESSFUL"}), "SUCCESSFUL"])

    async def go():
        runner = InMemoryRunner(agent=A.root_agent, app_name="cr")
        s = await runner.session_service.create_session(app_name="cr", user_id="dev1")
        async def say(t):
            import time
            from fake_llm import _write_trace
            evs, t0 = [], time.monotonic()
            async for _ev in runner.run_async(user_id="dev1", session_id=s.id,
                                            new_message=types.Content(role="user", parts=[types.Part(text=t)])):
                evs.append(_ev)
            sess = await runner.session_service.get_session(app_name="cr", user_id="dev1", session_id=s.id)
            _write_trace("cr", t, evs, sess, time.monotonic() - t0)
            return sess.state

        st = await say(f"Please review:\n```python\n{BAD}```")
        assert st["code_to_review"] == BAD and st["style_score"] < 100
        assert st["user:submission_count"] == 1 and st["user:review_history"][0]["test_verdict"] == "BUGGY"

        st = await say("yes, fix it")
        assert st["fix_status"] == "SUCCESSFUL"
        assert st["fix_report"]["style_score"]["after"] == 100 and st["fix_report"]["tests"]["after"] == "WORKING"
        assert len(F.code_fixer.model.requests) == 2      # loop ran twice, then escalated
        keys = await runner.artifact_service.list_artifact_keys(app_name="cr", user_id="dev1", session_id=s.id)
        assert {"review_001.md", "fixed_code.py", "fix_report.md"} <= set(keys)
        await runner.close()

    asyncio.run(go())
