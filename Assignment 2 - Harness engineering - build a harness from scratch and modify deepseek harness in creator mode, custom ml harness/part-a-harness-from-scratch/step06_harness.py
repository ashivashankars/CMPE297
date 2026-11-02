"""
STEP 6 - the complete harness:  Model + Harness = Agent.

Adds the four pieces that turn a tool loop into something you can trust:

  CONTEXT ENGINEERING  AGENTS.md from the workspace is loaded into the
                       system prompt (project rules the model must follow).
  COMPACTION           when the conversation grows past a size limit, old
                       turns are folded into a short summary so the run
                       never overflows the context window.
  VERIFIER (loop eng.) when the model says "done", the HARNESS runs the
                       --verify command. If it fails, the failure is fed
                       back and the loop continues: act -> verify -> repair.
  SESSION LOG          every event is appended to runs/<id>.jsonl so a run
                       can be inspected, replayed or graded later.

    cd workspace
    python ../step06_harness.py --verify "python test_calc.py" "Make the tests pass"
"""
import argparse
import json
import os
import subprocess
import time

from llm import Usage, chat, model_name
from step05_safety_budget import call_tool          # reuse step 5's guards
from tools import schemas

COMPACT_AT_CHARS = 12_000
KEEP_RECENT = 6


class SessionLog:
    def __init__(self):
        os.makedirs("runs", exist_ok=True)
        self.path = f"runs/{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    def write(self, kind: str, **data):
        with open(self.path, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 2), "kind": kind, **data}) + "\n")


def system_prompt() -> str:
    base = ("You are a coding agent. Read before you edit. Make the smallest change "
            "that solves the task. When finished, reply with a short summary and no tool calls.")
    if os.path.exists("AGENTS.md"):
        base += "\n\n# Project rules (AGENTS.md)\n" + open("AGENTS.md").read()
    return base


def compact(messages: list[dict], log: SessionLog) -> list[dict]:
    """Fold old turns into one summary message (no extra model call)."""
    size = sum(len(json.dumps(m)) for m in messages)
    if size < COMPACT_AT_CHARS or len(messages) <= KEEP_RECENT + 2:
        return messages
    head, old, recent = messages[:2], messages[2:-KEEP_RECENT], messages[-KEEP_RECENT:]
    while recent and recent[0]["role"] == "tool":       # never orphan a tool result
        old.append(recent.pop(0))
    notes = []
    for m in old:
        for c in m.get("tool_calls") or []:
            notes.append(f"- called {c['function']['name']} {c['function']['arguments'][:80]}")
        if m["role"] == "tool":
            notes.append(f"  result: {m['content'].strip()[:100]}")
    summary = {"role": "user", "content": "[harness] Summary of earlier work:\n" + "\n".join(notes)}
    log.write("compaction", before_chars=size, folded=len(old))
    print(f"  [harness] compacted {len(old)} old messages ({size} chars)")
    return head + [summary] + recent


def verify(cmd: str) -> tuple[bool, str]:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    return p.returncode == 0, (p.stdout + p.stderr)[-1500:]


def run(task: str, verify_cmd: str | None, max_steps: int, max_repairs: int) -> str:
    log = SessionLog()
    log.write("start", task=task, model=model_name(), verify=verify_cmd)
    messages = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": task}]
    repairs = 0
    for step in range(1, max_steps + 1):
        messages = compact(messages, log)
        reply = chat(messages, tools=schemas())
        messages.append(reply)
        log.write("assistant", step=step, content=reply.get("content"),
                  tool_calls=[c["function"] for c in reply.get("tool_calls") or []])

        if not reply.get("tool_calls"):                  # model claims it is done
            if not verify_cmd:
                return reply["content"]
            ok, out = verify(verify_cmd)
            log.write("verify", ok=ok, output=out)
            print(f"  [harness] verify `{verify_cmd}` -> {'PASS' if ok else 'FAIL'}")
            if ok:
                log.write("end", status="verified", tokens=Usage.total())
                return reply["content"] + "\n(verified by harness)"
            repairs += 1
            if repairs > max_repairs:
                return "Stopped: verification still failing after repairs."
            messages.append({"role": "user", "content":
                             f"[harness] Verification failed. You are not done.\n```\n{out}\n```\nFix it."})
            continue

        for call in reply["tool_calls"]:
            name, args = call["function"]["name"], json.loads(call["function"]["arguments"])
            out = call_tool(name, args)
            short = {k: (str(v)[:34] + "..." if len(str(v)) > 37 else v) for k, v in args.items()}
            print(f"  [{step}] {name}{short}")
            log.write("tool", name=name, args=args, output=out[:2000])
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    return "Stopped: max steps."


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Minimal coding-agent harness")
    ap.add_argument("task", nargs="+")
    ap.add_argument("--verify", help="shell command that must exit 0 before the task counts as done")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--max-repairs", type=int, default=3)
    ap.add_argument("--compact-at", type=int, default=COMPACT_AT_CHARS,
                    help="compact the conversation once it exceeds this many chars")
    a = ap.parse_args()
    COMPACT_AT_CHARS = a.compact_at
    task = " ".join(a.task)
    print(f"[step06] model = {model_name()}  verify = {a.verify!r}\nyou > {task}")
    result = run(task, a.verify, a.max_steps, a.max_repairs)
    print("bot >", result)
    print(f"[harness] tokens={Usage.total()}  log=runs/ (JSONL)")
