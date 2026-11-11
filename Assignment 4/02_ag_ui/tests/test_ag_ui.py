import json
import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

from agent import PART  # noqa: E402
from cli import trees  # noqa: E402
from common.catalog import validate  # noqa: E402


def run(mode):
    return [e for e in PART.run(mode, "q3") if "__meta" not in e]


class AGUITests(unittest.TestCase):
    def test_run_lifecycle(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            ev = run(mode)
            self.assertEqual(ev[0]["type"], "RUN_STARTED")
            self.assertEqual(ev[-1]["type"], "RUN_FINISHED")
            self.assertEqual(ev[1]["type"], "STATE_SNAPSHOT")
            for t in trees(ev):
                validate(t)

    def test_tool_args_stream_in_pieces_and_reassemble(self):
        ev = run("open_ended")
        args = "".join(e["delta"] for e in ev if e["type"] == "TOOL_CALL_ARGS")
        self.assertGreater(sum(e["type"] == "TOOL_CALL_ARGS" for e in ev), 3)
        self.assertIn("<!doctype html>", json.loads(args)["html"])

    def test_declarative_is_one_state_delta_per_op(self):
        ev = run("declarative")
        self.assertEqual(sum(e["type"] == "STATE_DELTA" for e in ev), 6)

    def test_invalid_patch_is_rejected_with_a_tool_result(self):
        state = {"ui": {"type": "Column", "props": {}, "children": []}}
        out = list(PART._execute({"name": "update_ui", "arguments": {"patch": [
            {"op": "add", "path": "/ui/children/-", "value": {"type": "Marquee", "props": {}}}]}}, state, "declarative"))
        self.assertFalse([e for e in out if e["type"] == "STATE_DELTA"])
        self.assertIn("unknown component", [e for e in out if e["type"] == "TOOL_CALL_RESULT"][0]["content"])

    def test_wrong_tool_for_mode(self):
        out = list(PART._execute({"name": "render_html", "arguments": {"html": "<p>x</p>"}}, {}, "static"))
        self.assertIn("not available", out[-1]["content"])

    def test_action_new_run_patches_detail(self):
        ev = [e for e in PART.action("static", {"action": {"name": "drill_region", "params": {"region": "East"}}}) if "__meta" not in e]
        delta = [e for e in ev if e["type"] == "STATE_DELTA"][0]["delta"][0]
        self.assertEqual(delta["path"], "/detail")
        self.assertIn("East", delta["value"]["props"]["title"])


if __name__ == "__main__":
    unittest.main()
