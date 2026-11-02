"""
STEP 5 - guardrails: sandbox, permission gate, output limits, budgets.

An agent that can run `bash` can also run `rm -rf ~`. The harness, not the
model, is responsible for safety. Four guards are added around every call:

  1. SANDBOX     file tools may only touch paths inside the workspace
  2. PERMISSION  risky shell commands need a human "y" (or --yes)
  3. TRUNCATION  huge outputs are cut so they don't flood the context
  4. BUDGETS     max steps, max tokens, max estimated $ per run

    cd workspace && python ../step05_safety_budget.py "Clean up the workspace"
"""
import json
import os
import re
import sys

from llm import Usage, chat, model_name
from tools import REGISTRY, schemas

WORKSPACE = os.path.realpath(os.getcwd())
RISKY = re.compile(r"\brm\s+-[rf]|\bsudo\b|curl[^|]*\|\s*(ba)?sh|\bgit\s+push\b|\bmkfs\b|>\s*/dev/")
MAX_OUT = 4000           # chars of tool output kept
MAX_STEPS = 12
MAX_TOKENS = 60_000
USD_PER_1K = 0.0004      # rough blended price; set for your model
AUTO_YES = "--yes" in sys.argv


class Blocked(Exception):
    pass


def guard(name: str, args: dict) -> None:
    # 1. sandbox
    for key in ("path",):
        if key in args:
            real = os.path.realpath(os.path.join(WORKSPACE, args[key]))
            if not real.startswith(WORKSPACE + os.sep) and real != WORKSPACE:
                raise Blocked(f"path {args[key]!r} is outside the workspace")
    # 2. permission
    if name == "bash" and RISKY.search(args["command"]):
        if AUTO_YES:
            return
        if not sys.stdin.isatty():
            raise Blocked(f"risky command needs approval: {args['command']!r}")
        if input(f"  !! allow `{args['command']}` ? [y/N] ").lower() != "y":
            raise Blocked("user denied the command")


def call_tool(name: str, args: dict) -> str:
    if name not in REGISTRY:
        return f"ERROR: unknown tool {name}"
    try:
        guard(name, args)
        out = REGISTRY[name](**args)
    except Blocked as b:
        return f"BLOCKED by harness: {b}. Choose a safer approach."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    if len(out) > MAX_OUT:                                  # 3. truncation
        out = out[:MAX_OUT // 2] + f"\n...[{len(out) - MAX_OUT} chars cut]...\n" + out[-MAX_OUT // 2:]
    return out


def run_agent(task: str) -> str:
    messages = [{"role": "system", "content": "You are a careful coding agent. Stay inside the workspace."},
                {"role": "user", "content": task}]
    for step in range(1, MAX_STEPS + 1):
        if Usage.total() > MAX_TOKENS:                      # 4. budgets
            return f"Stopped: token budget {MAX_TOKENS} exceeded."
        reply = chat(messages, tools=schemas())
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply["content"]
        for call in reply["tool_calls"]:
            name, args = call["function"]["name"], json.loads(call["function"]["arguments"])
            out = call_tool(name, args)
            flag = "BLOCKED" if out.startswith("BLOCKED") else "ok"
            print(f"  [{step}] {name}({args}) -> {flag}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    return f"Stopped: step budget {MAX_STEPS} reached."


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--yes"]
    task = " ".join(args) or "Clean up the workspace"
    print(f"[step05] model = {model_name()}  workspace = {WORKSPACE}\nyou > {task}")
    print("bot >", run_agent(task))
    cost = Usage.total() / 1000 * USD_PER_1K
    print(f"[budget] tokens={Usage.total()}  est. cost=${cost:.5f}")
