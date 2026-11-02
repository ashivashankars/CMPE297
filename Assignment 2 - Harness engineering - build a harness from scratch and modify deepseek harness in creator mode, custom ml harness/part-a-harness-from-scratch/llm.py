"""
llm.py - the ONLY place that talks to a model.

Every step of the harness imports `chat()` from here, so swapping providers
is a one-file change.

Real mode  : OpenRouter's OpenAI-compatible /chat/completions endpoint.
             export OPENROUTER_API_KEY=sk-or-...
             export HARNESS_MODEL=google/gemini-2.5-flash   (optional; any OpenRouter model id)
             On the OpenRouter dashboard you can attach your own Gemini key
             ("BYOK") so the requests are billed to your student Gemini Pro plan.

Mock mode  : export HARNESS_MOCK=path/to/script.json
             A scripted "model" replays a fixed list of replies (text and
             tool calls). The TOOLS still really run - only the model's
             decisions are pre-written. Used to record the demo videos
             offline and in CI. Never used when OPENROUTER_API_KEY is set
             and HARNESS_MOCK is unset.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("HARNESS_MODEL", "google/gemini-2.5-flash")


class Usage:
    """Running token counter so later steps can enforce a budget."""
    prompt_tokens = 0
    completion_tokens = 0

    @classmethod
    def add(cls, usage: dict | None) -> None:
        if usage:
            cls.prompt_tokens += usage.get("prompt_tokens", 0)
            cls.completion_tokens += usage.get("completion_tokens", 0)

    @classmethod
    def total(cls) -> int:
        return cls.prompt_tokens + cls.completion_tokens


# ---------------------------------------------------------------- real model
def _openrouter(messages: list[dict], tools: list[dict] | None, model: str) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (or HARNESS_MOCK=<script.json> for offline demo).")
    body = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "CMPE297 harness from scratch",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    Usage.add(data.get("usage"))
    return data["choices"][0]["message"]  # {"role","content","tool_calls"?}


# ---------------------------------------------------------------- mock model
class _Script:
    """Replays replies from a JSON file: a list of
         {"text": "..."}                          -> plain assistant answer
         {"tool": "name", "args": {...}}          -> one tool call
         {"tools": [{"tool":..,"args":..}, ...]}  -> parallel tool calls
       "{{last}}" inside text is replaced by the most recent tool result,
       so the scripted answer can quote what really happened."""

    def __init__(self, path: str):
        with open(path) as f:
            self.steps = json.load(f)
        self.i = 0

    def next(self, messages: list[dict]) -> dict:
        if self.i >= len(self.steps):
            return {"role": "assistant", "content": "(script finished)"}
        step = self.steps[self.i]
        self.i += 1
        Usage.add({"prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 4,
                   "completion_tokens": 20})
        if "text" in step:
            last = next((m["content"] for m in reversed(messages) if m["role"] == "tool"), "")
            last = re.sub(r"^exit=\d+\n", "", last)        # hide the exit-code header
            return {"role": "assistant", "content": step["text"].replace("{{last}}", last.strip())}
        calls = step.get("tools") or [step]
        return {
            "role": "assistant",
            "content": step.get("say"),
            "tool_calls": [
                {"id": f"call_{self.i}_{k}", "type": "function",
                 "function": {"name": c["tool"], "arguments": json.dumps(c.get("args", {}))}}
                for k, c in enumerate(calls)
            ],
        }


_script: _Script | None = None


def chat(messages: list[dict], tools: list[dict] | None = None, model: str = DEFAULT_MODEL) -> dict:
    """Send the conversation, get back ONE assistant message (maybe with tool_calls)."""
    global _script
    mock = os.environ.get("HARNESS_MOCK")
    if mock:
        if _script is None:
            _script = _Script(mock)
        return _script.next(messages)
    return _openrouter(messages, tools, model)


def model_name() -> str:
    return f"mock-script:{os.path.basename(os.environ['HARNESS_MOCK'])}" if os.environ.get("HARNESS_MOCK") else DEFAULT_MODEL
