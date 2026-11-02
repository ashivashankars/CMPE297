"""
STEP 2 - give the model ONE tool (bash), called exactly once.

A "tool" is just:
  1. a JSON schema we send to the model so it knows the tool exists, and
  2. a Python function we run when the model asks for it.
The model never runs anything itself. It *asks*; the harness *does*.

    python step02_one_tool.py "How many python files are in this folder?"
"""
import json
import subprocess
import sys

from llm import chat, model_name

BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command and return stdout+stderr.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}


def bash(command: str) -> str:
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return (p.stdout + p.stderr) or "(no output)"


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How many python files are in this folder?"
    print(f"[step02] model = {model_name()}\nyou > {question}")
    messages = [
        {"role": "system", "content": "You can run shell commands with the bash tool."},
        {"role": "user", "content": question},
    ]

    reply = chat(messages, tools=[BASH_SCHEMA])          # 1) model decides
    messages.append(reply)
    for call in reply.get("tool_calls") or []:
        args = json.loads(call["function"]["arguments"])
        print(f"  tool  > bash({args['command']!r})")
        result = bash(**args)                            # 2) harness executes
        print("  result>", result.strip())
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    final = chat(messages, tools=[BASH_SCHEMA])          # 3) model reads result
    print("bot >", final["content"])
    # Limitation: if the model needs a SECOND command, we can't do it. -> step 3
