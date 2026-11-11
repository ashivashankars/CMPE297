"""One function every codelab uses to "ask the model": stream_text(system, user, fixture).

Two backends, chosen by environment variables:

  live      ANTHROPIC_API_KEY  -> Anthropic Messages API (model: GENUI_MODEL, default claude-sonnet-5-5)
            OPENAI_API_KEY or API_KEY (+ optional OPENAI_BASE_URL) -> any OpenAI-compatible endpoint
  scripted  no key, or GENUI_LLM=scripted -> replay the fixture file for this step

The scripted backend is what the tests and recorded videos use: the output is
exactly what a model would send, streamed in small chunks with a short delay
so you can watch progressive rendering. Everything downstream (parsing,
validation, rendering, actions) is the same code path in both backends.

Fixture files may contain two macros to keep long HTML readable:
  {{raw:name}}   the text of common/fixtures/name
  {{json:name}}  the same text as a JSON string literal (quotes and escapes)
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path

COMMON_FIXTURES = Path(__file__).parent / "fixtures"
CHUNK = int(os.environ.get("GENUI_CHUNK", "48"))           # characters per scripted chunk
DELAY = float(os.environ.get("GENUI_DELAY", "0.012"))      # seconds between scripted chunks


def backend():
    if os.environ.get("GENUI_LLM") == "scripted":
        return "scripted"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY"):
        return "openai"
    return "scripted"


def expand(text):
    def sub(m):
        kind, name = m.group(1), m.group(2)
        body = (COMMON_FIXTURES / name).read_text(encoding="utf-8")
        return json.dumps(body) if kind == "json" else body
    return re.sub(r"\{\{(raw|json):([\w.\-]+)\}\}", sub, text)


def load_fixture(path):
    return expand(Path(path).read_text(encoding="utf-8"))


def stream_text(system, user, fixture, *, delay=None):
    """Yield the model's reply as text chunks."""
    kind = backend()
    if kind == "anthropic":
        yield from _anthropic(system, user)
    elif kind == "openai":
        yield from _openai(system, user)
    else:
        text = load_fixture(fixture)
        d = DELAY if delay is None else delay
        for i in range(0, len(text), CHUNK):
            if d:
                time.sleep(d)
            yield text[i:i + CHUNK]


def complete(system, user, fixture, **kw):
    return "".join(stream_text(system, user, fixture, **kw))


# ---------------------------------------------------------------- live backends

def _sse_lines(req):
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    yield json.loads(data)


def _anthropic(system, user):
    body = {
        "model": os.environ.get("GENUI_MODEL", "claude-sonnet-5-5"),
        "max_tokens": 8000,
        "system": system,
        "stream": True,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"},
    )
    for event in _sse_lines(req):
        if event.get("type") == "content_block_delta" and event["delta"].get("type") == "text_delta":
            yield event["delta"]["text"]


def _openai(system, user):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY") or os.environ["API_KEY"]
    body = {"model": os.environ.get("GENUI_MODEL", "gpt-4.1-mini"), "stream": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "authorization": f"Bearer {key}"})
    for event in _sse_lines(req):
        delta = (event.get("choices") or [{}])[0].get("delta", {}).get("content")
        if delta:
            yield delta


def strip_fences(text):
    """Models like ```json fences; formats don't. Remove one surrounding fence if present."""
    m = re.match(r"^\s*```[\w-]*\n(.*?)\n```\s*$", text, re.S)
    return m.group(1) if m else text
