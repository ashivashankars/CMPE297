"""Tools that let ADK agents drive the Gemini CLI safely.

Differences from the reference implementation (derrickchwong/gemini-cli-on-adk):
* no `shell=True` - arguments are passed as a list, so a malicious task string or
  URL cannot inject shell commands;
* GitHub URLs are validated against a strict pattern before cloning (shallow);
* the CLI runs read-only by default, with a timeout, an output cap and a
  per-session call budget;
* JSON output mode is used so the agent gets the answer plus token stats;
* every run is logged into session state for observability.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from google.adk.tools import ToolContext

from . import config

GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) or raise ValueError for anything that is not a plain
    public GitHub repository URL."""
    m = GITHUB_URL_RE.match((url or "").strip())
    if not m or m.group("owner") in (".", "..") or m.group("repo") in (".", ".."):
        raise ValueError(f"Not a valid GitHub repository URL: {url!r}")
    return m.group("owner"), m.group("repo")


def _clone(url: str, dest: Path, ref: str = "") -> None:
    cmd = ["git", "clone", "--depth", "1", "--single-branch"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, str(dest)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=config.CLONE_TIMEOUT_S)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[-2000:])


def _summarise_repo(path: Path) -> dict:
    ext_counts: dict[str, int] = {}
    n_files = 0
    for p in path.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        n_files += 1
        ext_counts[p.suffix or "(none)"] = ext_counts.get(p.suffix or "(none)", 0) + 1
    top = sorted(x.name + ("/" if x.is_dir() else "") for x in path.iterdir() if x.name != ".git")
    langs = sorted(ext_counts.items(), key=lambda kv: -kv[1])[:8]
    return {"file_count": n_files, "top_level": top[:50], "top_extensions": dict(langs)}


def prepare_repository(github_url: str, tool_context: ToolContext, ref: str = "") -> dict:
    """Shallow-clone a public GitHub repository into the agent workspace (or reuse an
    existing clone) and return a short summary of its layout.

    Args:
        github_url: Repository URL, e.g. https://github.com/google/adk-python
        ref: Optional branch or tag to check out.
    """
    try:
        owner, repo = parse_github_url(github_url)
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    if ref and not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", ref):
        return {"status": "error", "error": f"Invalid ref {ref!r}"}

    dest = Path(config.WORKSPACE_DIR) / f"{owner}__{repo}{('@' + ref.replace('/', '_')) if ref else ''}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    reused = dest.exists() and (dest / ".git").exists()
    if not reused:
        try:
            _clone(f"https://github.com/{owner}/{repo}.git", dest, ref)
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "git clone timed out"}
        except RuntimeError as e:
            return {"status": "error", "error": f"git clone failed: {e}"}

    summary = _summarise_repo(dest)
    tool_context.state["repo_dir"] = str(dest)
    tool_context.state["repo_name"] = f"{owner}/{repo}"
    return {"status": "ok", "repo": f"{owner}/{repo}", "reused_existing_clone": reused,
            "local_path": str(dest), **summary}


def _parse_cli_output(stdout: str) -> tuple[str, dict]:
    """Gemini CLI `--output-format json` returns {"response": ..., "stats": ...}.
    Fall back to raw text for older CLI versions."""
    text = stdout.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "response" in data:
            stats = data.get("stats") or {}
            return str(data["response"]), stats
    except json.JSONDecodeError:
        pass
    return text, {}


def build_cli_command(task: str) -> list[str]:
    cmd = [config.GEMINI_CLI_BIN, "-p", task, "--output-format", "json"]
    if config.GEMINI_CLI_MODEL:
        cmd += ["-m", config.GEMINI_CLI_MODEL]
    if config.GEMINI_CLI_APPROVAL == "yolo":
        cmd.append("--yolo")
    return cmd


def run_gemini_cli(task: str, tool_context: ToolContext) -> dict:
    """Run the Gemini CLI non-interactively inside the prepared repository. The CLI
    reads the codebase itself (file discovery, grep, reading files) so use it for
    codebase-wide questions: explaining architecture, finding where something is
    implemented, generating a test plan, drafting unit tests, reviewing quality.

    Args:
        task: A focused, self-contained instruction for the CLI. Ask it to cite
            file paths for every claim.
    """
    repo_dir = tool_context.state.get("repo_dir")
    if not repo_dir or not Path(repo_dir).is_dir():
        return {"status": "error", "error": "No repository prepared. Call prepare_repository first."}
    if not task or len(task) > 8000:
        return {"status": "error", "error": "Task must be 1-8000 characters."}

    calls = int(tool_context.state.get("cli_calls", 0))
    if calls >= config.GEMINI_CLI_MAX_CALLS:
        return {"status": "error",
                "error": f"Gemini CLI budget exhausted ({config.GEMINI_CLI_MAX_CALLS} calls). "
                         "Answer with what you already have."}
    if not config.cli_path():
        return {"status": "error",
                "error": f"'{config.GEMINI_CLI_BIN}' not found. Install with: npm install -g @google/gemini-cli"}

    env = os.environ.copy()
    # Gemini CLI reads GEMINI_API_KEY; reuse the ADK key if only that is set.
    if not env.get("GEMINI_API_KEY") and env.get("GOOGLE_API_KEY"):
        env["GEMINI_API_KEY"] = env["GOOGLE_API_KEY"]

    started = time.monotonic()
    try:
        res = subprocess.run(build_cli_command(task), capture_output=True, text=True,
                             cwd=repo_dir, env=env, timeout=config.GEMINI_CLI_TIMEOUT_S,
                             stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        result = {"status": "error", "error": f"Gemini CLI timed out after {config.GEMINI_CLI_TIMEOUT_S}s"}
    else:
        if res.returncode == 0:
            answer, stats = _parse_cli_output(res.stdout)
            truncated = len(answer) > config.GEMINI_CLI_MAX_OUTPUT_CHARS
            result = {"status": "ok", "response": answer[: config.GEMINI_CLI_MAX_OUTPUT_CHARS],
                      "truncated": truncated, "stats": stats}
        else:
            result = {"status": "error", "error": (res.stderr or res.stdout).strip()[-3000:]}

    elapsed = round(time.monotonic() - started, 2)
    log = list(tool_context.state.get("cli_runs", []))
    log.append({"task": task[:200], "status": result["status"], "seconds": elapsed})
    tool_context.state["cli_runs"] = log
    tool_context.state["cli_calls"] = calls + 1
    result["seconds"] = elapsed
    result["calls_remaining"] = config.GEMINI_CLI_MAX_CALLS - calls - 1
    return result


def gemini_cli_health() -> dict:
    """Check that the Gemini CLI is installed and authenticated; returns its version."""
    path = config.cli_path()
    if not path:
        return {"installed": False, "hint": "npm install -g @google/gemini-cli"}
    try:
        v = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
        version = v.stdout.strip() or v.stderr.strip()
    except Exception as e:  # noqa: BLE001
        version = f"unknown ({e})"
    auth = ("GEMINI_API_KEY" in os.environ or "GOOGLE_API_KEY" in os.environ
            or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true")
    return {"installed": True, "path": path, "version": version, "auth_configured": auth,
            "approval_mode": config.GEMINI_CLI_APPROVAL}
