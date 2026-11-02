"""Scripted, offline stand-in for Gemini so the agent wiring can be tested
end-to-end (tools, MCP servers, callbacks, state, sub-agents) without an API key.

Each ScriptedLlm returns its queued turns in order. A turn is either
  - a string            -> plain model text
  - ("call", name, args) -> a function call the agent must execute
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import AsyncGenerator, Iterable

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types


def request_text(llm_request) -> str:
    """System instruction + all message text of a request (for responders)."""
    parts = [str(llm_request.config.system_instruction or "")] if llm_request.config else []
    for c in llm_request.contents or []:
        for p in c.parts or []:
            if p.text:
                parts.append(p.text)
    return "\n".join(parts)


class ScriptedLlm(BaseLlm):
    model: str = "gemini-scripted-fake"
    turns: list = []
    requests: list = []
    responder: object = None

    def __init__(self, turns: Iterable = (), responder=None, **kw):
        """turns: queued replies; responder: fn(llm_request) -> turn (for
        concurrent agents where call order is not deterministic)."""
        super().__init__(model="gemini-scripted-fake", **kw)
        self.turns = list(turns)
        self.requests = []
        self.responder = responder

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["gemini-scripted-fake"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        if self.responder is not None:
            turn = self.responder(llm_request)
        elif not self.turns:
            turn = "(script exhausted)"
        else:
            turn = self.turns.pop(0)
        if isinstance(turn, tuple) and turn[0] == "call":
            _, name, args = turn
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text=str(turn))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))

    def last_function_responses(self) -> list[dict]:
        """Function responses the agent sent back on the most recent request."""
        out = []
        for content in self.requests[-1].contents if self.requests else []:
            for p in content.parts or []:
                if p.function_response:
                    out.append({"name": p.function_response.name,
                                "response": p.function_response.response})
        return out


async def run_agent(agent, message: str, state: dict | None = None, app_name="test"):
    """Run one user turn through an in-memory Runner; return (events, session)."""
    from google.adk.runners import InMemoryRunner

    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name, user_id="u1", state=state or {}
    )
    events = []
    t0 = time.monotonic()
    async for ev in runner.run_async(
        user_id="u1", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        events.append(ev)
    session = await runner.session_service.get_session(
        app_name=app_name, user_id="u1", session_id=session.id
    )
    await runner.close()
    _write_trace(app_name, message, events, session, time.monotonic() - t0)
    return events, session, runner


def _short(obj, n=400) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + " ...[truncated]"


def _write_trace(app_name, message, events, session, seconds) -> None:
    """When TRACE_DIR is set, append a readable execution trace of this run
    (agent hops, tool calls, tool results, replies, final state) to
    $TRACE_DIR/<test name>.md. Used to produce transcripts/offline/."""
    out_dir = os.environ.get("TRACE_DIR")
    if not out_dir:
        return
    test = os.environ.get("PYTEST_CURRENT_TEST", app_name).split(" ")[0]
    file_stem, _, func = test.partition("::")
    path = Path(out_dir) / f"{Path(file_stem).stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"## `{func or app_name}`", "", f"**User:** {_short(message, 600)}", "", "```text"]
    for ev in events:
        for p in (ev.content.parts if ev.content else []) or []:
            if p.function_call:
                lines.append(f"[{ev.author}] CALL   {p.function_call.name}({_short(dict(p.function_call.args or {}), 250)})")
            elif p.function_response:
                lines.append(f"[{ev.author}] RESULT {p.function_response.name} -> {_short(p.function_response.response)}")
            elif p.text:
                lines.append(f"[{ev.author}] TEXT   {_short(p.text, 300)}")
        delta = ev.actions.state_delta if ev.actions else None
        if delta:
            lines.append(f"[{ev.author}] STATE  += {', '.join(sorted(delta))}")
        if ev.actions and ev.actions.escalate:
            lines.append(f"[{ev.author}] ESCALATE (loop exit)")
        if ev.actions and ev.actions.transfer_to_agent:
            lines.append(f"[{ev.author}] TRANSFER -> {ev.actions.transfer_to_agent}")
    lines += ["```", "", f"Final state keys: `{', '.join(sorted(session.state))}`  ",
              f"Events: {len(events)} · wall time {seconds:.2f}s", "", ""]
    header = "" if path.exists() else (
        f"# Offline execution trace - {Path(file_stem).stem}\n\n"
        "Generated by `TRACE_DIR=transcripts/offline pytest`. Gemini is replaced by a scripted "
        "fake model; tools, MCP servers, databases, callbacks, sub-agents, loops and state are real.\n\n")
    with path.open("a") as f:
        f.write(header + "\n".join(lines))
