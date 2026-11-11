# Video narration scripts

Each video in `videos/` has these lines burned in as captions (and as an `.srt` file).
Read them aloud while re-recording, or record a voice-over on top of the existing video.

## 00_foundations.mp4 - 00 · Foundations

| Time | Narration |
|---|---|
| 00:00 | Hi! In this assignment I build the same Q3 sales dashboard **six times**, once per generative-UI technology, and each one in **four modes**. |
| 00:12 | The four modes are a ladder of model freedom: **static** gives the least, **open-ended** the most, and **mixed** is the practical default. |
| 00:24 | The **catalog** is the contract. It is the prompt the model reads, the validator for its output, and the registry the page draws from, all from one list. |
| 00:36 | **validate()** walks the normalized tree. Unknown components, wrong prop types and disallowed actions all raise errors written so the model can read them and fix its output. |
| 00:48 | On the page, **components.mjs** has one function per catalog type. It builds DOM nodes and never evaluates model text as code. Buttons only send a named action back. |
| 00:59 | Open-ended HTML is mounted by **sandbox.mjs**: sandbox='allow-scripts' with no same-origin, a CSP with no network, and exactly one message shape back to the page. |
| 01:11 | **llm.py**: with no API key, the model's reply is replayed from a fixture file, streamed in small chunks. With ANTHROPIC_API_KEY or OPENAI_API_KEY set, the same code calls a live model. |
| 01:22 | Running **run_all.sh**: it runs the unit tests for all six parts plus the browser-module tests, then each CLI. Every test passes. |

## 01_a2ui.mp4 - 01 · A2UI

| Time | Narration |
|---|---|
| 00:00 | Part one is **A2UI**. Its key idea is that the layout and the data are sent separately, and components bind to data by path. |
| 00:10 | The **four envelope messages**. A surface must exist first; updateComponents sends a flat list where components reference each other by id. |
| 00:21 | The **Surface** keeps a component map and a data model. **resolve()** turns {path: ...} bindings into values, and **tree()** turns the flat map into the normalized tree. Ids that have not arrived yet render as placeholders. |
| 00:34 | **STATIC mode**: the templates are ours. The model only chooses 'sales_overview' and returns values; our code sends every component. |
| 00:45 | **DECLARATIVE, OPEN-ENDED and MIXED**: the model writes A2UI JSONL. Each complete line is applied and checked before it is forwarded, so the page can render while the model is still writing. |
| 00:57 | Here is what the model sends in declarative mode: components first, data afterwards. The title is a binding to /title, and it fills in when updateDataModel arrives. |
| 01:08 | **Actions**: a click sends an A2UI action. The model designs the detail surface with bindings only, and then the **app** supplies the real numbers with updateDataModel. |
| 01:20 | Running it in the terminal: each message, then the click, then the **same tree drawn by a terminal renderer**. |
| 01:36 | **Static**: the model only chose the template. The wire log shows our fixed updateComponents followed by one updateDataModel. |
| 01:47 | **Declarative**: watch the components stream in. Then I click 'West details', which creates a second surface designed by the model and filled with data by the app. |
| 02:00 | **Open-ended**: a single HtmlView holds model-written HTML in a sandbox. Clicking a legend row sends an action out through postMessage. |
| 02:12 | **Mixed**: catalog KPIs and chart, plus one sandboxed what-if slider, which is something the catalog cannot express. |
| 02:25 | The A2UI tests cover bindings, rejected envelopes, the template ownership in static mode, and the action round trip. |

## 02_ag_ui.mp4 - 02 · AG-UI

| Time | Narration |
|---|---|
| 00:00 | Part two is **AG-UI**. It does not describe what a UI looks like. It describes how text, tool calls and **shared state** move between the agent and the page. |
| 00:10 | Events are written by hand so every field is visible. Text and tool arguments **stream in pieces**, the way a model emits them. |
| 00:21 | One run is a generator: RUN_STARTED, a STATE_SNAPSHOT, the model's text, its tool calls, and finally RUN_FINISHED. If the model call fails, the run ends with **RUN_ERROR**. |
| 00:32 | **DECLARATIVE**: update_ui(patch). Each op is tried on a copy, validated against the catalog, and only then sent as its own **STATE_DELTA**, so the page renders progressively. |
| 00:45 | **STATIC**: the page registers a component for the tool name show_sales_dashboard. **OPEN-ENDED**: render_html shows the bytes received, then mounts a sandbox at TOOL_CALL_END. |
| 00:57 | The client folds events into messages, tool calls and state. **STATE_DELTA** is just a JSON Patch on the shared state, followed by a re-render. |
| 01:09 | In the terminal, one STATE_DELTA per op, then the click as a **new run**: a server tool call, a delta on /detail, and a short message. |
| 01:24 | **Static**: the model called show_sales_dashboard and our pre-built widget renders from the streamed arguments. Then I click to drill into West. |
| 01:35 | **Declarative**: the UI is part of the shared state, and each STATE_DELTA adds a node. The last patch replaces the heading text. |
| 01:48 | **Open-ended**: the HTML arrives as TOOL_CALL_ARGS and mounts in a sandbox when the call ends. |
| 01:59 | **Mixed**: an HtmlView node sits inside the shared-state tree like any other component. |
| 02:09 | The tests check the run lifecycle, argument streaming, one delta per op, rejection of invalid patches, and the action run. |

## 03_mcp_apps.mp4 - 03 · MCP Apps

| Time | Narration |
|---|---|
| 00:00 | Part three is **MCP Apps**. This time **another application hosts the UI**. My page is the host, and an MCP server supplies the views. |
| 00:10 | A normal MCP server (mcp 2.x MCPServer). **sales_dashboard** points at a hand-written view. Its result carries text for the model and structuredContent for the view. |
| 00:22 | **DECLARATIVE**: render_spec validates the model's tree on the **server**, so an invalid spec comes back as isError and the view never sees it. **OPEN-ENDED**: render_html runs the policy check. |
| 00:34 | **drill_region** is app-only, with visibility set to ['app']. The model never sees it; only a view can call it, through the host. |
| 00:43 | The host: **tools/list**, then the model picks a tool, then **tools/call**, then **resources/read** of the ui:// view. A host without MCP Apps support would just show result.content. |
| 00:56 | In the browser, the host answers **ui/initialize**. After ui/notifications/initialized it sends tool-input and tool-result, and it **proxies tools/call** back to the MCP server. |
| 01:09 | **OPEN-ENDED** in MCP Apps is two boundaries deep: the trusted view nests the model's HTML in a second sandbox. |
| 01:19 | Real MCP over stdio. The model sees four tools while drill_region stays hidden, and the view's click becomes a tools/call. |
| 01:36 | **Static**: the hand-written MCP App view. 'Details' calls drill_region through the bridge, and you can see the tools/call request and its response in the log. |
| 01:50 | **Declarative**: a generic catalog view draws whatever tree the server validated. |
| 02:03 | **Open-ended**: the model's HTML runs in a sandbox nested inside the view's sandbox, and clicks still reach the server. |
| 02:16 | **Mixed**: catalog components plus a nested sandboxed slider, all inside one MCP App. |
| 02:26 | The tests start the real server, check the _meta and MIME types, reject invalid specs and network HTML, and check that the host refuses unknown tools. |

## 04_json_render.mp4 - 04 · json-render

| Time | Narration |
|---|---|
| 00:00 | Part four is **json-render**. The spec is a flat map of elements, so the model can stream it one patch line at a time and the page paints as it goes. |
| 00:10 | Every streamed line is checked: allowed paths, known types and known props, and actions must go in the 'on' field, not in props. |
| 00:21 | **to_tree** resolves the spec: $state props, visible filtering and repeat expansion. A Button's **on.press** becomes a named action. |
| 00:33 | The model's output in declarative mode: elements, with state patches right after the elements that use them. The table repeats over /state/regions. |
| 00:45 | **STATIC**: SalesOverview is a custom registry component that we wrote. The model sends a single element with props. |
| 00:55 | In the browser, **setState runs locally** without a server call. drill_region is POSTed, and the server answers with more patches on the same spec. |
| 01:06 | In the terminal, the patch stream, then the app's patches for the click, then the same spec drawn by the terminal renderer. |
| 01:21 | **Static**: one SalesOverview element. The layout is ours; the props come from the model. |
| 01:30 | **Declarative**: elements and state stream in. 'Hide orders' is a **local setState**; 'East details' asks the server for patches. |
| 01:47 | **Open-ended**: one HtmlView element in a sandbox. |
| 01:56 | **Mixed**: catalog elements plus one HtmlView element. |
| 02:04 | The tests check that the first patches already paint a partial tree, that visible and repeat work, and that bad patches are rejected. |

## 05_openui.mp4 - 05 · OpenUI Lang

| Time | Narration |
|---|---|
| 00:00 | Part five is **OpenUI Lang**. The model writes a small **program** instead of JSON, and the page re-parses it on every chunk. |
| 00:10 | This is a program. **root** refers to title, kpis, split and actions before they are defined, which is called hoisting, and it is what makes streaming work. |
| 00:21 | Arguments are **positional**, so each component has a fixed signature. HtmlArtifact maps to our sandboxed HtmlView, and SalesOverview is the pre-built static component. |
| 00:32 | parse() with **partial=True** skips the line that is still being written. resolve() turns names that are not defined yet into placeholders. |
| 00:44 | The same resolver in JavaScript, which the browser runs after every streamed chunk. |
| 00:53 | **Actions**: the app answers drill_region by appending lines. A later root = ... replaces the earlier one. |
| 01:04 | In the terminal: the program as streamed, its size compared with the JSON tree, and the terminal render after the click. |
| 01:19 | **Static**: a single line, root = SalesOverview(...). |
| 01:28 | **Declarative**: placeholders fill in as forward references get defined. The program here is about 60% of the size of the same UI as JSON. |
| 01:42 | **Open-ended**: root = HtmlArtifact(...). The document mounts once its line is complete. |
| 01:53 | **Mixed**: catalog components plus one HtmlArtifact. |
| 02:01 | The tests cover forward references, partial programs, positional props, the rules for each mode, and the appended action. |

## 06_harness.mp4 - 06 · Harness integration

| Time | Narration |
|---|---|
| 00:00 | The final part joins everything to an **agent harness**. Generative UI becomes just another tool in the loop. |
| 00:10 | The classic harness loop: call the model, run its tool calls, and append the results. Errors are results too. The loop stops when there are no more tool calls or it hits **MAX_TURNS**. |
| 00:23 | **render_ui** validates the arguments for the current mode: a pre-built component in static, a catalog tree in declarative, policy-checked HTML in open-ended, and exactly one HtmlView in mixed. |
| 00:36 | The recorded model turns. In turn 2 the model tries a **PieChart**, which is not in the catalog. |
| 00:46 | A click on any surface becomes a **new user message** in the same session, so the model sees the earlier turns. |
| 00:55 | The terminal surface. In turn 2 the render fails with 'unknown component PieChart'. The model reads that error and corrects it in turn 3. |
| 01:11 | The web surface shows the same loop. You can see the error, the correction, and then a click that continues the session. |
| 01:27 | **Static**: the model only picks sales_overview and fills its props. |
| 01:34 | **Open-ended**: render_ui with HTML. The harness checks the policy, and the surface sandboxes it. |
| 01:46 | **Mixed**: catalog plus one HtmlView, which is the default I would recommend for a real product. |
| 01:55 | The tests check one render per mode, recovery from the PieChart error, the click continuing the session, and the turn limit. |
| 02:04 | To sum up: pick a **format**, pick a **transport or host**, validate everything against the catalog, and keep model-written HTML inside a sandbox. Thanks for watching! |
