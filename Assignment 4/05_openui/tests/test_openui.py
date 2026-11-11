import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import openui  # noqa: E402
from agent import PART, check_program  # noqa: E402
from common.catalog import CatalogError, validate  # noqa: E402


class OpenUITests(unittest.TestCase):
    def test_every_mode_valid_and_smaller_than_json(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            done = list(PART.run(mode, "q3"))[-1]
            self.assertTrue(done.get("done"), (mode, done))
            self.assertLess(done["bytes"], done["jsonTreeBytes"], mode)

    def test_forward_references_resolve(self):
        tree = openui.resolve(openui.parse('root = Stack([a])\na = Text("hi")'))
        self.assertEqual(tree["children"][0]["props"]["text"], "hi")

    def test_partial_program_has_placeholders(self):
        stmts = openui.parse('root = Stack([a, b])\na = Text("hi")\nb = Metr', partial=True)
        tree = openui.resolve(stmts)
        self.assertEqual(tree["children"][1], {"pending": "b"})

    def test_positional_arguments_map_to_props(self):
        t = openui.resolve(openui.parse('root = Metric("Revenue", "$4.2M", "+12%")'))
        self.assertEqual(t["props"], {"label": "Revenue", "value": "$4.2M", "delta": "+12%"})
        validate(t)

    def test_mode_rules(self):
        with self.assertRaises(CatalogError):
            check_program('root = HtmlArtifact("x", "<p>hi</p>")', "declarative")
        with self.assertRaises(CatalogError):
            check_program('root = Stack([Text("only catalog")])', "mixed")

    def test_syntax_error_reports_line(self):
        with self.assertRaises(openui.ParseError) as e:
            openui.parse('root = Stack([a)\n')
        self.assertIn("line 1", str(e.exception))

    def test_action_appends_and_redefines_root(self):
        prog = open(HERE / "fixtures" / "declarative.oui").read()
        app = list(PART.action("declarative", {"action": "drill_region", "params": {"region": "East"}, "program": prog}))[-1]["append"]
        tree = openui.resolve(openui.parse(prog + app))
        self.assertIn("East", tree["children"][1]["props"]["title"])


if __name__ == "__main__":
    unittest.main()
