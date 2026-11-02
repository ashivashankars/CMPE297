"""Offline tests for (b): URL validation, real subprocess execution of a fake
Gemini CLI binary inside a 'cloned' repo, budget enforcement, and the full
Sequential -> Loop(critic) -> Writer pipeline driven by the root agent."""
import asyncio
import subprocess
from pathlib import Path

import pytest
from fake_llm import ScriptedLlm, run_agent

import gemini_cli_agent.agent as A
from gemini_cli_agent import config, tools

FAKE_CLI = str(Path(__file__).parent / "fixtures" / "fake_gemini_cli.py")


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setattr(config, "GEMINI_CLI_BIN", FAKE_CLI)

    def fake_clone(url, dest, ref=""):
        dest.mkdir(parents=True)
        (dest / "app.py").write_text("print('hi')\n")
        (dest / "README.md").write_text("# demo\n")
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
    monkeypatch.setattr(tools, "_clone", fake_clone)


@pytest.mark.parametrize("url,ok", [
    ("https://github.com/google/adk-python", True),
    ("https://github.com/google/adk-python.git", True),
    ("https://github.com/a/b; rm -rf /", False),
    ("http://github.com/a/b", False),
    ("https://evil.com/a/b", False),
    ("https://github.com/../etc", False),
])
def test_url_validation(url, ok):
    if ok:
        assert tools.parse_github_url(url)[0] == "google"
    else:
        with pytest.raises(ValueError):
            tools.parse_github_url(url)


def test_command_has_no_shell_and_is_readonly_by_default():
    cmd = tools.build_cli_command('explain "$(whoami)"')
    assert cmd[1:3] == ["-p", 'explain "$(whoami)"'] and "--yolo" not in cmd


def test_pipeline_end_to_end():
    A.root_agent.model = ScriptedLlm([
        ("call", "RepoTaskPipeline", {"request": "https://github.com/acme/demo explain the codebase"}),
        "Here is the explanation ...",
    ])
    A.repo_preparer.model = ScriptedLlm([
        ("call", "prepare_repository", {"github_url": "https://github.com/acme/demo"}),
        "acme/demo: 2 files, Python",
    ])
    A.cli_executor.model = ScriptedLlm([
        ("call", "run_gemini_cli", {"task": "Explain the architecture, cite file paths"}),
        "Draft v1",                                    # iteration 1
        ("call", "run_gemini_cli", {"task": "What does app.py do?"}),
        "Draft v2 citing `app.py`",                    # iteration 2
    ])
    A.critic.model = ScriptedLlm([
        "1. Cite file paths",                          # reject v1
        ("call", "exit_loop", {}), "APPROVED",         # approve v2
    ])
    A.report_writer.model = ScriptedLlm(["## Codebase overview\nDraft v2 citing `app.py`"])

    events, s, runner = asyncio.run(run_agent(A.root_agent, "Explain https://github.com/acme/demo"))
    st = s.state
    assert st["repo_name"] == "acme/demo"
    assert st["cli_calls"] == 2 and all(r["status"] == "ok" for r in st["cli_runs"])
    assert st["draft"] == "Draft v2 citing `app.py`"
    assert st["final_answer"].startswith("## Codebase overview")
    # the fake CLI really executed inside the cloned repo:
    resp = A.cli_executor.model.requests[1].contents[-1].parts[0].function_response.response
    assert "app.py" in resp["response"] and resp["stats"]


def test_budget_enforced(tmp_path):
    class Ctx:
        state = {"repo_dir": str(tmp_path), "cli_calls": config.GEMINI_CLI_MAX_CALLS}
    out = tools.run_gemini_cli("anything", Ctx())
    assert out["status"] == "error" and "budget" in out["error"]
