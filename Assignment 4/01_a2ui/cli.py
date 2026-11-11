"""Terminal run of the A2UI codelab: `python cli.py [--mode M] [--action] [--full]`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import a2ui  # noqa: E402
from agent import PART  # noqa: E402
from common import cli  # noqa: E402


def label(msg):
    kind = a2ui.kind_of(msg)
    return f"{kind}({msg[kind]['surfaceId']})"


def trees(messages):
    client = a2ui.Client()
    for m in messages:
        client.apply(m)
    return [s.tree() for s in client.surfaces.values()]


if __name__ == "__main__":
    cli.main(PART, label, trees,
             action_body=lambda mode: a2ui.action_message("drill_region", "sales", "drill_west", {"region": "West"}))
