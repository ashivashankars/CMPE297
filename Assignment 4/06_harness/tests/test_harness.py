import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

from harness import MAX_TURNS, Harness, ScriptedModel  # noqa: E402
from common.catalog import validate  # noqa: E402


class HarnessTests(unittest.TestCase):
    def test_every_mode_renders_once_and_finishes(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            ev = list(Harness(mode).run("q3", ScriptedModel(mode)))
            renders = [e["tree"] for e in ev if e["event"] == "render"]
            self.assertEqual(len(renders), 1, mode)
            validate(renders[0])
            self.assertEqual(ev[-1]["event"], "done")

    def test_validation_error_is_a_result_and_model_recovers(self):
        h = Harness("declarative")
        ev = list(h.run("q3", ScriptedModel("declarative")))
        errors = [e for e in ev if e["event"] == "tool_result" and not e["ok"]]
        self.assertEqual(len(errors), 1)
        self.assertIn("PieChart", errors[0]["content"])
        self.assertTrue(any(m["role"] == "tool" and "PieChart" in m["content"] for m in h.messages))  # the model saw it

    def test_static_mode_refuses_free_trees(self):
        h = Harness("static")
        with self.assertRaises(Exception):
            h.tools.render_ui(tree={"type": "Text", "props": {"text": "x"}})

    def test_click_continues_the_same_session(self):
        h = Harness("mixed")
        list(h.run("q3", ScriptedModel("mixed")))
        before = len(h.messages)
        ev = list(h.ui_action("drill_region", {"region": "South"}, ScriptedModel("action", {"region": "South"})))
        self.assertTrue(h.messages[before]["content"].startswith("[ui action] drill_region"))
        self.assertIn("South", [e for e in ev if e["event"] == "render"][0]["tree"]["props"]["title"])

    def test_turn_limit(self):
        class Loop:
            def __call__(self, *_):
                return {"tool_calls": [{"name": "load_sales", "arguments": {}}]}
        ev = list(Harness("static").run("q3", Loop()))
        self.assertEqual(ev[-1], {"event": "done", "turns": MAX_TURNS, "stopped": "turn limit"})


if __name__ == "__main__":
    unittest.main()
