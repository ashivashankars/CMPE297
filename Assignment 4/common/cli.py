"""Run a codelab in the terminal: every protocol message, then the result drawn
by the terminal renderer. This is the "execution" view used in the videos.

    python cli.py                 all four modes
    python cli.py --mode mixed    one mode
    python cli.py --action        also click "drill_region West" after each run
    python cli.py --full          print whole messages instead of a one-line summary
"""

import argparse
import json
import os
import time

from common import terminal
from common.catalog import count, validate

MODES = ("static", "declarative", "open_ended", "mixed")
C = {"h": "\033[1;38;5;173m", "m": "\033[38;5;245m", "ok": "\033[32m", "err": "\033[31m", "x": "\033[0m"}
if os.environ.get("NO_COLOR"):
    C = {k: "" for k in C}


def short(msg, width=150):
    text = json.dumps(msg)
    return text if len(text) <= width else text[: width - 20] + f"… ({len(text)} chars)"


def main(part, label, trees, action_body=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--action", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--prompt", default=part.default_prompt)
    a = ap.parse_args()
    for mode in [a.mode] if a.mode else MODES:
        print(f"\n{C['h']}━━ {part.name} · mode = {mode} ━━{C['x']}")
        print(f"{C['m']}prompt: {a.prompt}{C['x']}")
        t0 = time.time()
        messages = []
        for msg in part.run(mode, a.prompt):
            if "__meta" in msg:
                print(f"{C['m']}model backend: {msg['__meta']['backend']}{C['x']}")
                continue
            ms = int((time.time() - t0) * 1000)
            if "error" in msg:
                print(f"{C['err']}  ✗ {msg['error']}{C['x']}")
                continue
            messages.append(msg)
            print(f"  {ms:>5} ms  {C['h']}{label(msg):<28}{C['x']} {json.dumps(msg, indent=1) if a.full else short(msg)}")
        if a.action and action_body:
            body = action_body(mode)
            print(f"\n  {C['ok']}⬆ user action:{C['x']} {short(body)}")
            for msg in part.action(mode, body):
                if "__meta" in msg:
                    continue
                if "error" in msg:
                    print(f"{C['err']}  ✗ {msg['error']}{C['x']}")
                    continue
                messages.append(msg)
                print(f"           {C['h']}{label(msg):<28}{C['x']} {short(msg)}")
        print(f"\n  {C['m']}terminal renderer (same tree the browser draws):{C['x']}")
        for tree in trees(messages):
            html_regions = validate(tree)
            print(f"  {C['ok']}✓ catalog-valid tree: {count(tree)} nodes, {html_regions} sandboxed HtmlView region(s){C['x']}")
            print(terminal.render(tree, 1))
