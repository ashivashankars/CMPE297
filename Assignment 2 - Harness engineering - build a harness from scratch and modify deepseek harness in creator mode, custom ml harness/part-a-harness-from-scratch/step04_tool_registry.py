"""
STEP 4 - a real coding agent: tool registry + file editing tools.

Same loop as step 3, but tools come from tools.py, where a @tool decorator
generates each JSON schema from the Python signature. The agent can now
list, read, write and surgically edit files - enough to change code.

    cd workspace && python ../step04_tool_registry.py "Add a multiply(a, b) function to calc.py"
"""
import json
import sys

from llm import chat, model_name
from tools import REGISTRY, schemas

SYSTEM = """You are a coding agent working in the current directory.
Always read a file before editing it. Use edit_file for small changes."""


def run_agent(task: str, max_steps: int = 15) -> str:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    for step in range(1, max_steps + 1):
        reply = chat(messages, tools=schemas())
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply["content"]
        for call in reply["tool_calls"]:
            name, args = call["function"]["name"], json.loads(call["function"]["arguments"])
            short = {k: (v if len(str(v)) < 40 else str(v)[:37] + "...") for k, v in args.items()}
            print(f"  [{step}] {name}{short}")
            try:
                out = REGISTRY[name](**args)
            except Exception as e:
                out = f"ERROR: {type(e).__name__}: {e}"
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    return "Stopped: max_steps reached."


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "Add a multiply(a, b) function to calc.py"
    print(f"[step04] model = {model_name()}   tools = {list(REGISTRY)}\nyou > {task}")
    print("bot >", run_agent(task))
