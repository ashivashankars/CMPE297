"""
STEP 3 - the agent loop.

The single most important idea in harness engineering:

    while the model keeps asking for tools:
        run the tools
        feed the results back
    stop when the model answers in plain text (or we hit max_steps)

Now the model can investigate step by step: list files, then read one,
then run it...

    python step03_agent_loop.py "Read notes.txt and tell me the 3rd line"
"""
import json
import subprocess
import sys

from llm import chat, model_name

TOOLS = [
    {"type": "function", "function": {
        "name": "bash", "description": "Run a shell command.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a text file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
]


def bash(command):
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return (p.stdout + p.stderr) or "(no output)"


def read_file(path):
    with open(path) as f:
        return f.read()


IMPL = {"bash": bash, "read_file": read_file}


def run_agent(task: str, max_steps: int = 10) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful agent. Use tools, then answer."},
        {"role": "user", "content": task},
    ]
    for step in range(1, max_steps + 1):
        reply = chat(messages, tools=TOOLS)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:                                   # plain answer => done
            return reply["content"]
        for call in calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            print(f"  [{step}] {name}({args})")
            try:
                out = IMPL[name](**args)
            except Exception as e:                      # errors go BACK to the model
                out = f"ERROR: {e}"
            print("       ->", out.strip().splitlines()[0][:70] if out.strip() else "")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    return "Stopped: max_steps reached."


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "Read notes.txt and tell me the 3rd line"
    print(f"[step03] model = {model_name()}\nyou > {task}")
    print("bot >", run_agent(task))
