import json
import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import a2ui  # noqa: E402
from agent import PART, TEMPLATES  # noqa: E402
from common.catalog import CatalogError, validate  # noqa: E402


def run(mode):
    return [m for m in PART.run(mode, "q3") if "__meta" not in m]


class A2UITests(unittest.TestCase):
    def test_every_mode_streams_valid_messages(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            msgs = run(mode)
            self.assertFalse([m for m in msgs if "error" in m], mode)
            client = a2ui.Client()
            for m in msgs:
                client.apply(m)
            client.validate_all()
            self.assertEqual(a2ui.kind_of(msgs[0]), "createSurface")

    def test_static_layout_comes_from_our_template(self):
        msgs = run("static")
        self.assertEqual(msgs[1]["updateComponents"]["components"], TEMPLATES["sales_overview"])

    def test_binding_reads_data_model(self):
        c = a2ui.Client()
        c.apply(a2ui.create_surface("s"))
        c.apply(a2ui.update_components("s", [{"id": "root", "component": "Text", "text": {"path": "/a/b"}}]))
        c.apply(a2ui.update_data_model("s", "/a", {"b": "hello"}))
        self.assertEqual(c.surfaces["s"].tree()["props"]["text"], "hello")
        c.apply(a2ui.update_data_model("s", "/a/b", "changed"))   # data changes, structure does not
        self.assertEqual(c.surfaces["s"].tree()["props"]["text"], "changed")

    def test_unknown_surface_and_bad_version_rejected(self):
        c = a2ui.Client()
        with self.assertRaises(CatalogError):
            c.apply(a2ui.update_components("nope", []))
        with self.assertRaises(CatalogError):
            c.apply({"version": "v0.8", "createSurface": {"surfaceId": "x", "catalogId": "c"}})

    def test_html_not_allowed_in_declarative(self):
        tree = {"type": "HtmlView", "props": {"html": "<p>x</p>"}}
        with self.assertRaises(CatalogError):
            validate(tree, allow_html=False)

    def test_action_detail_surface_structure_from_model_data_from_app(self):
        out = [m for m in PART.action("declarative", a2ui.action_message("drill_region", "sales", "b", {"region": "South"})) if "__meta" not in m]
        self.assertEqual(a2ui.kind_of(out[-1]), "updateDataModel")
        self.assertEqual(out[-1]["updateDataModel"]["value"]["region"], "South")

    def test_disallowed_action(self):
        out = list(PART.action("static", a2ui.action_message("rm_rf", "sales", "b", {})))
        self.assertIn("error", out[0])


if __name__ == "__main__":
    unittest.main()
