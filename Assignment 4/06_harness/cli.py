"""The TERMINAL surface of the harness: `python cli.py [--mode M] [--action]`.
Same harness, same events as the web page; render_ui draws with the terminal renderer."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import PART  # noqa: E402
from common import cli  # noqa: E402


def label(e):
    return f"{e['event']} {e.get('name', '')}{' ✗' if e.get('ok') is False else ''}".strip()


def trees(events):
    for e in events:
        if e["event"] == "tool_result" and not e["ok"]:
            print(f"  note: the model received this error and retried → {e['content']}")
    return [e["tree"] for e in events if e["event"] == "render"]


if __name__ == "__main__":
    cli.main(PART, label, trees, action_body=lambda mode: {"action": "drill_region", "params": {"region": "West"}})
