// Parity tests for the browser modules (node --test tests_js/).
import { test } from "node:test";
import assert from "node:assert/strict";
import { parse, resolve } from "../05_openui/web/openui.mjs";
import { applyPatch } from "../common/web/json-patch.mjs";
import { readFileSync } from "node:fs";

test("OpenUI JS parser resolves the declarative fixture like the Python one", () => {
  const prog = readFileSync(new URL("../05_openui/fixtures/declarative.oui", import.meta.url), "utf8");
  const tree = resolve(parse(prog));
  assert.equal(tree.type, "Column");
  assert.equal(tree.children[1].children[0].props.value, "$4.20M");
});

test("OpenUI partial program renders placeholders", () => {
  const tree = resolve(parse('root = Stack([a, b])\na = Text("hi")\nb = Me', { partial: true }));
  assert.deepEqual(tree.children[1], { pending: "b" });
});

test("JSON Patch add/replace/remove with '-'", () => {
  const doc = applyPatch({ ui: { children: [] } }, [
    { op: "add", path: "/ui/children/-", value: 1 },
    { op: "add", path: "/ui/children/-", value: 2 },
    { op: "replace", path: "/ui/children/0", value: 9 },
    { op: "remove", path: "/ui/children/1" },
  ]);
  assert.deepEqual(doc, { ui: { children: [9] } });
});
