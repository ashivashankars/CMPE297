"""Terminal run of the json-render codelab: `python cli.py [--mode M] [--action] [--full]`.
Same spec, second renderer: the terminal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jsonrender as jr  # noqa: E402
from agent import PART  # noqa: E402
from common import cli  # noqa: E402
from common.json_patch import apply_op  # noqa: E402


def label(op):
    return f"{op['op']} {op['path']}"[:28]


def trees(ops):
    spec = {"root": None, "elements": {}, "state": {}}
    for op in ops:
        apply_op(spec, op)
    return [jr.to_tree(spec)]


if __name__ == "__main__":
    cli.main(PART, label, trees, action_body=lambda mode: {"action": "drill_region", "params": {"region": "West"}, "root": "main"})
