"""Terminal run of the OpenUI Lang codelab: `python cli.py [--mode M] [--action] [--full]`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import openui  # noqa: E402
from agent import PART  # noqa: E402
from common import cli  # noqa: E402

_program = {"text": ""}


def label(m):
    if "delta" in m:
        return f"text delta ({len(m['delta'])} chars)"
    if m.get("done"):
        return f"done: {m['bytes']}B vs JSON {m['jsonTreeBytes']}B"
    return "append (app patch)" if "append" in m else "message"


def trees(messages):
    program = "".join(m.get("delta", "") for m in messages)
    program += "".join("\n" + m["append"] for m in messages if "append" in m)
    _program["text"] = program
    print("\n  program as streamed:\n" + "\n".join("    " + (l if len(l) < 140 else l[:120] + f"… ({len(l)} chars)")
                                                 for l in program.strip().splitlines()))
    return [openui.resolve(openui.parse(program))]


def action_body(mode):
    prog = "".join(m.get("delta", "") for m in PART.run(mode, PART.default_prompt) if "delta" in m)
    return {"action": "drill_region", "params": {"region": "West"}, "program": prog}


if __name__ == "__main__":
    cli.main(PART, label, trees, action_body=action_body)
