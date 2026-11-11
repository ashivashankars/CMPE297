"""The harness served to the web surface. One Harness per mode keeps the conversation,
so a click continues the SAME session (the model sees the earlier turns)."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import llm  # noqa: E402

from harness import Harness, model_for, safe_region  # noqa: E402


class Part:
    name = "Harness integration · render_ui as a tool"
    web_dir = HERE / "web"
    default_prompt = "Analyze Q3 sales by region and show me a dashboard"
    pace = 0.12 if llm.backend() == "scripted" else 0

    def __init__(self):
        self.sessions = {}

    def run(self, mode, prompt):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        self.sessions[mode] = Harness(mode)
        yield from self.sessions[mode].run(prompt, model_for(mode))

    def action(self, mode, body):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        h = self.sessions.setdefault(mode, Harness(mode))
        params = body.get("params") or {}
        yield from h.ui_action(body.get("action"), params, model_for("action", {"region": safe_region(params)}))


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8006)
