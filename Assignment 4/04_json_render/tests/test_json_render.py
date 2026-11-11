import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import jsonrender as jr  # noqa: E402
from agent import PART  # noqa: E402
from cli import trees  # noqa: E402
from common.catalog import CatalogError, validate  # noqa: E402


def run(mode):
    return [m for m in PART.run(mode, "q3") if "__meta" not in m]


class JsonRenderTests(unittest.TestCase):
    def test_every_mode_valid(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            ops = run(mode)
            self.assertFalse([o for o in ops if "error" in o], mode)
            validate(trees(ops)[0])

    def test_first_patch_paints_partial_tree(self):
        ops = run("declarative")[:3]   # root, main, title - title's state not streamed yet
        tree = trees(ops)[0]
        self.assertEqual(tree["type"], "Column")
        self.assertIn({"pending": "kpis"}, tree["children"])

    def test_visible_and_repeat(self):
        ops = run("declarative")
        spec = {"root": None, "elements": {}, "state": {}}
        from common.json_patch import apply_op
        for o in ops:
            apply_op(spec, o)
        types = lambda t: [c.get("props", {}).get("title") for c in t["children"]]  # noqa: E731
        self.assertIn("Orders by region", types(jr.to_tree(spec)))
        table = [c for c in jr.to_tree(spec)["children"] if c["props"].get("title") == "Orders by region"][0]
        self.assertEqual(len(table["children"]), 4)                 # repeat over /state/regions
        spec["state"]["showTable"] = False                          # what setState does on the client
        self.assertNotIn("Orders by region", types(jr.to_tree(spec)))

    def test_bad_patch_rejected(self):
        with self.assertRaises(CatalogError):
            jr.check_op({"op": "add", "path": "/elements/x", "value": {"type": "Button", "props": {"label": "x", "action": "drill_region"}}})
        with self.assertRaises(CatalogError):
            jr.check_op({"op": "add", "path": "/secrets", "value": 1})

    def test_action_answers_with_patches(self):
        out = [o for o in PART.action("declarative", {"action": "drill_region", "params": {"region": "Central"}, "root": "main"}) if "__meta" not in o]
        self.assertEqual(out[-1], {"op": "replace", "path": "/root", "value": "page"})
        self.assertIn("Central", out[0]["value"]["title"])


if __name__ == "__main__":
    unittest.main()
