"""
STEP 1 - a model with memory.

The simplest possible "harness": keep a list of messages and resend the
whole list every turn. The model itself is stateless; the harness is what
remembers.

    python step01_chat.py "What is an agent harness in one sentence?"
    python step01_chat.py            # interactive REPL
"""
import sys

from llm import chat, model_name

messages = [{"role": "system", "content": "You are a concise assistant."}]


def ask(text: str) -> str:
    messages.append({"role": "user", "content": text})
    reply = chat(messages)                       # no tools yet
    messages.append({"role": "assistant", "content": reply["content"]})
    return reply["content"]


if __name__ == "__main__":
    print(f"[step01] model = {model_name()}")
    if len(sys.argv) > 1:
        for prompt in sys.argv[1:]:              # several args = several turns
            print(f"\nyou > {prompt}\nbot > {ask(prompt)}")
    else:
        while (line := input("\nyou > ").strip()) not in ("", "exit"):
            print("bot >", ask(line))
    print(f"\n[step01] history length = {len(messages)} messages")
