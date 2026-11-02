#!/usr/bin/env python3
"""Stand-in for `gemini -p ... --output-format json` used by the offline tests.
It lists the files in the current directory so we can prove it ran in the repo."""
import json, os, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("0.0.0-fake"); sys.exit(0)
prompt = args[args.index("-p") + 1]
files = sorted(f for f in os.listdir(".") if not f.startswith("."))
print(json.dumps({"response": f"Answer to '{prompt[:40]}'. Files: {', '.join(files)} (see `app.py`)",
                  "stats": {"models": {"fake": {"tokens": {"total": 42}}}}}))
