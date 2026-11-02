#!/usr/bin/env python3
"""Run a scripted, *live* demo conversation against one agent (real Gemini calls)
and save a Markdown transcript of every tool call, tool result and reply to
transcripts/<agent>.md. Use it to generate execution evidence and as the
backbone of the video walkthrough.

    python scripts/run_demo.py lead_generation_agent
    python scripts/run_demo.py all
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REQUIRE_ORDER_CONFIRMATION", "false")  # no dialog in a headless run
try:  # read Assignment 3/.env before checking for credentials
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

BUGGY_CODE = '''def calculate_average(numbers=[]):
    total=0
    for n in numbers: total+=n
    return total/len(numbers)

def ProcessData(data):
    result = eval(data)
    try:
        return result*2
    except:
        pass
'''

DEMOS: dict[str, list[str]] = {
    "lead_generation_agent": [
        "I sell cloud cost-optimisation software. Find me leads among fintech companies in India.",
        "Study 3 companies.",
        "Yes, find 5 leads.",
    ],
    "gemini_cli_agent": [
        "Is the Gemini CLI tool working?",
        "Explain the architecture of https://github.com/google/adk-python and where tool calling is implemented.",
        "Now generate a test plan for its callbacks feature.",
    ],
    "bug_assistant_agent": [
        "Our customers say they got charged twice for their bean subscription. Is there already a ticket?",
        "Show me all open P0 and P1 tickets in a table.",
        "Create a ticket: the Espresso Pro steam wand keeps dripping water after brewing finishes.",
        "What tickets were created in the last 30 days?",
        "Search the web for best practices to make payment retries idempotent.",
    ],
    "code_review_assistant": [
        "What can you do?",
        f"Please review this code:\n```python\n{BUGGY_CODE}```",
        "Yes, please fix it.",
    ],
    "ecommerce_agent": [
        "Hi! I'm training for my first half marathon and need cushioned running shoes under $170.",
        "Tell me more about the Clifton 10.",
        "Add the Clifton 10 in size 9, White to my list.",
        "Show my shopping list and the stores near me.",
        "What delivery options does the Palo Alto store have?",
        "Place the order at Palo Alto with Express Delivery.",
        "Actually change it to Store Pickup, then show my orders.",
    ],
}


def _short(obj, n=700) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + " ...[truncated]"


async def run(name: str) -> Path:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = importlib.import_module(f"{name}.agent").root_agent
    runner = InMemoryRunner(agent=agent, app_name=name)
    session = await runner.session_service.create_session(app_name=name, user_id="alex@example.com")
    lines = [f"# Live transcript - `{name}`", "", f"Recorded {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for prompt in DEMOS[name]:
        print(f"\n>>> USER: {prompt[:120]}")
        lines += ["---", f"### User", "", prompt, ""]
        t0 = time.monotonic()
        async for ev in runner.run_async(user_id="alex@example.com", session_id=session.id,
                                         new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
            for p in (ev.content.parts if ev.content else []) or []:
                if p.function_call:
                    msg = f"**[{ev.author}] tool call** `{p.function_call.name}` {_short(dict(p.function_call.args or {}), 300)}"
                elif p.function_response:
                    msg = f"**[{ev.author}] tool result** `{p.function_response.name}` -> {_short(p.function_response.response)}"
                elif p.text and not getattr(p, "thought", False):
                    msg = f"**[{ev.author}]** {p.text}"
                else:
                    continue
                print(msg[:300])
                lines += [msg, ""]
        lines += [f"_turn took {time.monotonic() - t0:.1f}s_", ""]
    final = await runner.session_service.get_session(app_name=name, user_id="alex@example.com", session_id=session.id)
    arts = await runner.artifact_service.list_artifact_keys(app_name=name, user_id="alex@example.com",
                                                            session_id=session.id)
    lines += ["---", "### Final session state keys", "", ", ".join(sorted(final.state)), "",
              "### Artifacts", "", ", ".join(arts) or "(none)", ""]
    out = ROOT / "transcripts" / f"{name}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    await runner.close()
    print(f"\nTranscript written to {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in [*DEMOS, "all"]:
        sys.exit(f"usage: {sys.argv[0]} <{'|'.join(DEMOS)}|all>")
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"):
        sys.exit("Set GOOGLE_API_KEY (AI Studio) or GOOGLE_GENAI_USE_VERTEXAI=true in .env first.")
    for n in (DEMOS if sys.argv[1] == "all" else [sys.argv[1]]):
        asyncio.run(run(n))
