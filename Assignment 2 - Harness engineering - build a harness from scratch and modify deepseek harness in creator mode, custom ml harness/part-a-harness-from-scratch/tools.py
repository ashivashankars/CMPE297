"""
tools.py - STEP 4's tool registry (reused by steps 5 and 6).

Hand-writing JSON schemas (step 3) does not scale. Here a decorator turns
an ordinary Python function into a tool: the schema is generated from the
function's type hints and docstring.

    @tool
    def read_file(path: str) -> str:
        "Read a text file with line numbers."
"""
from __future__ import annotations

import inspect
import os
import subprocess
from typing import Callable

REGISTRY: dict[str, Callable] = {}
_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


def tool(fn: Callable) -> Callable:
    REGISTRY[fn.__name__] = fn
    return fn


def schemas(names: list[str] | None = None) -> list[dict]:
    """OpenAI/OpenRouter 'tools' list built from the registry."""
    out = []
    for name, fn in REGISTRY.items():
        if names and name not in names:
            continue
        sig = inspect.signature(fn)
        props, required = {}, []
        for p in sig.parameters.values():
            props[p.name] = {"type": _PY_TO_JSON.get(p.annotation, "string")}
            if p.default is inspect.Parameter.empty:
                required.append(p.name)
        out.append({"type": "function", "function": {
            "name": name,
            "description": inspect.getdoc(fn) or name,
            "parameters": {"type": "object", "properties": props, "required": required},
        }})
    return out


# ------------------------------------------------------------------ the tools
@tool
def list_dir(path: str = ".") -> str:
    """List files in a directory (non-recursive)."""
    return "\n".join(sorted(os.listdir(path))) or "(empty)"


@tool
def read_file(path: str) -> str:
    """Read a text file. Returns it with line numbers."""
    with open(path) as f:
        return "".join(f"{i:4}| {line}" for i, line in enumerate(f, 1))


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given content."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"wrote {len(content)} chars to {path}"


@tool
def edit_file(path: str, old: str, new: str) -> str:
    """Replace the exact text `old` with `new` in a file. `old` must appear exactly once."""
    with open(path) as f:
        text = f.read()
    n = text.count(old)
    if n != 1:
        return f"ERROR: `old` found {n} times; it must match exactly once. Read the file first."
    with open(path, "w") as f:
        f.write(text.replace(old, new))
    return f"edited {path}"


@tool
def bash(command: str) -> str:
    """Run a shell command (60s timeout) and return its output."""
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return f"exit={p.returncode}\n{p.stdout}{p.stderr}"
