# 05 · OpenUI Lang: a compact language for UI

Video: [`videos/05_openui.mp4`](../videos/05_openui.mp4) · Logs: [`docs/execution_logs/05_openui.txt`](../docs/execution_logs/05_openui.txt) · Screenshots: [`docs/screenshots/05_openui/`](../docs/screenshots/05_openui)

**Idea:** instead of JSON, the model writes a small **program**: one `name = Component(args)` statement per line, with **positional** arguments. A name can be used **before** it is defined (hoisting). The page re-parses the whole program after every chunk, skips the line that is still arriving, and draws undefined names as placeholders. With no repeated `"type"`, `"props"` or `"children"` keys, the program is smaller than the equivalent JSON.

```
root = Stack([title, kpis, split, actions])
title = Heading("Q3 2026 - revenue up 12%, West leads")
kpis = Stack([revenue, orders, ticket], "row")
revenue = Metric("Revenue", "$4.20M", "+12%")
...
```

## Files

| File | What it does |
|---|---|
| `openui.py` | `SIGNATURES` (positional parameters per component), `tokenize()`, `parse(partial=)`, `resolve()` (refs → tree, `{"pending"}` for unknown names), `to_node()` |
| `web/openui.mjs` | The same tokenizer, parser and resolver in JavaScript (parity tested in `tests_js/`) |
| `agent.py` | Streams text deltas, validates the finished program per mode, reports program bytes vs JSON-tree bytes, answers actions by appending lines |
| `fixtures/*.oui` | The model's program per mode |
| `web/oui-renderer.mjs` | Re-parse and paint on every chunk; shows the program and the size comparison |
| `cli.py`, `tests/test_openui.py` (7 tests) | |

## Step-by-step walkthrough

**Step 1: tokenize** (`TOKEN` regex): strings with JSON escapes, numbers, names, and the punctuation `[ ] ( ) { } , : =`. Strings are decoded with `json.loads`, so HTML inside a string can contain `\n` and `\"`.

**Step 2: parse.** It is a recursive descent parser over expressions: literals, `[lists]`, `{"objects"}`, `Component(args)` calls, and bare names (`{"$ref": name}`). With `partial=True`, the last line, which may be cut off, is dropped and broken lines are skipped. Without it, errors report the line number (`test_syntax_error_reports_line`).

**Step 3: resolve.** `root` is the entry point, and `$ref`s are looked up in the statement table. An undefined name becomes `{"pending": name}`, which the page draws as "loading name…". Positional arguments are zipped with `SIGNATURES`, so `Metric("Revenue", "$4.20M", "+12%")` becomes `{label, value, delta}`. `Stack(children, "row")` maps to the catalog `Row`, and `HtmlArtifact(title, html)` maps to `HtmlView`.

**Step 4: the four modes** (`ALLOWED` in `agent.py`). The component names actually called are collected from the **parsed** program, not the raw text. (A JavaScript `Number(...)` inside the HTML string is not a component.)
- **Static**: only `SalesOverview(...)`, our pre-built library component. One line.
- **Declarative**: catalog signatures only.
- **Open-ended**: only `HtmlArtifact`, mounted when its line is complete.
- **Mixed**: catalog components plus at least one `HtmlArtifact`.

**Step 5: size.** When the program is done, the server reports `bytes` and `jsonTreeBytes`. The declarative program is **822 bytes vs 1374** for the same tree as JSON (60%). These are bytes for one example, not tokens.

**Step 6: actions by appending.** The page sends the program with the click. The app copies the old root's expression into `page = …`, appends `detail = Card(...)`, and redefines `root = Stack([page, detail])`. Later definitions replace earlier ones, so the program stays valid. A second click only replaces `detail`.

## Run

```bash
python cli.py --mode declarative --action
python agent.py 8005                 # http://127.0.0.1:8005/?mode=declarative
python -m unittest discover -s tests -v
node --test ../tests_js/frontend.test.mjs
```
