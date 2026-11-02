"""Deterministic analysis tools. The LLM agents interpret results, but every
number (complexity, style score, before/after deltas) is computed in code so the
review is reproducible and testable."""
from __future__ import annotations

import ast
import difflib
import io
import re
from datetime import datetime, timezone
from typing import Any

import pycodestyle
from google.adk.tools import ToolContext
from google.genai import types

from . import config
from .constants import StateKeys as K

SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*_{0,2}$")
PASCAL = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")
FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def extract_code(text: str) -> str:
    """Strip Markdown fences if the model wrapped the code in them."""
    m = FENCE.search(text or "")
    return (m.group(1) if m else (text or "")).strip("\n") + "\n"


# ---------------------------------------------------------------- structure
def _complexity(node: ast.AST) -> int:
    """McCabe-style cyclomatic complexity approximation."""
    branches = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With,
                ast.AsyncWith, ast.IfExp, ast.comprehension, ast.Assert)
    score = 1
    for n in ast.walk(node):
        if isinstance(n, branches):
            score += 1
        elif isinstance(n, ast.BoolOp):
            score += len(n.values) - 1
        elif isinstance(n, ast.Match):
            score += len(n.cases)
    return score


def structure_of(code: str) -> dict[str, Any]:
    tree = ast.parse(code)
    functions, classes, imports = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name, "line": node.lineno,
                "length": (node.end_lineno or node.lineno) - node.lineno + 1,
                "args": [a.arg for a in node.args.args],
                "has_docstring": ast.get_docstring(node) is not None,
                "has_type_hints": node.returns is not None or any(a.annotation for a in node.args.args),
                "complexity": _complexity(node),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno,
                            "methods": [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                            "has_docstring": ast.get_docstring(node) is not None})
        elif isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(f"{node.module or ''}." + ",".join(a.name for a in node.names))
    risky = [{"line": n.lineno, "call": n.func.id} for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("eval", "exec")]
    bare_except = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    mutable_defaults = [f.name for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and any(isinstance(d, (ast.List, ast.Dict, ast.Set)) for d in f.args.defaults)]
    lines = code.splitlines()
    return {
        "functions": functions, "classes": classes, "imports": imports,
        "metrics": {
            "lines": len(lines),
            "code_lines": sum(1 for l in lines if l.strip() and not l.strip().startswith("#")),
            "function_count": len(functions), "class_count": len(classes),
            "max_complexity": max((f["complexity"] for f in functions), default=0),
            "avg_function_length": round(sum(f["length"] for f in functions) / len(functions), 1) if functions else 0,
            "docstring_coverage": round(sum(f["has_docstring"] for f in functions) / len(functions), 2) if functions else 1.0,
        },
        "risk_flags": {"eval_exec_calls": risky, "bare_except_lines": bare_except,
                       "mutable_default_args": mutable_defaults},
    }


async def analyze_code_structure(code: str, tool_context: ToolContext) -> dict:
    """Parse Python code with the AST and return functions, classes, imports,
    complexity metrics and risk flags. Pass the user's code EXACTLY as given.

    Args:
        code: The complete Python source to review.
    """
    code = extract_code(code)
    if len(code) > config.MAX_CODE_CHARS:
        return {"status": "error", "error": f"Code exceeds {config.MAX_CODE_CHARS} characters."}
    tool_context.state[K.CODE_TO_REVIEW] = code
    try:
        analysis = structure_of(code)
    except SyntaxError as e:
        result = {"status": "syntax_error", "line": e.lineno, "message": e.msg,
                  "text": (e.text or "").strip()}
        tool_context.state[K.CODE_ANALYSIS] = result
        return result
    tool_context.state[K.CODE_ANALYSIS] = analysis
    return {"status": "success", **analysis}


# ---------------------------------------------------------------- style
def _naming_issues(tree: ast.AST) -> list[dict]:
    issues = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not SNAKE.match(n.name):
            issues.append({"line": n.lineno, "code": "N802", "message": f"function '{n.name}' should be snake_case"})
        elif isinstance(n, ast.ClassDef) and not PASCAL.match(n.name):
            issues.append({"line": n.lineno, "code": "N801", "message": f"class '{n.name}' should be PascalCase"})
    return issues


def style_of(code: str) -> dict:
    class Collect(pycodestyle.BaseReport):
        def __init__(self, options):
            super().__init__(options)
            self.items = []

        def error(self, line_number, offset, text, check):
            code_ = text[:4]
            if code_ not in self.expected:
                self.items.append({"line": line_number, "column": offset + 1,
                                   "code": code_, "message": text[5:]})
            return super().error(line_number, offset, text, check)

    guide = pycodestyle.StyleGuide(quiet=True, max_line_length=config.MAX_LINE_LENGTH,
                                   reporter=Collect)
    checker = pycodestyle.Checker(lines=io.StringIO(code).readlines(), options=guide.options)
    checker.check_all()
    issues = checker.report.items
    try:
        issues += _naming_issues(ast.parse(code))
    except SyntaxError:
        pass
    # E/N issues cost more than whitespace (W) issues; floor at 0.
    penalty = sum(5 if i["code"][0] in "EN" else 2 for i in issues)
    score = max(0, 100 - penalty)
    by_code: dict[str, int] = {}
    for i in issues:
        by_code[i["code"]] = by_code.get(i["code"], 0) + 1
    return {"score": score, "issue_count": len(issues), "issues": issues[:40],
            "issue_breakdown": by_code}


async def check_code_style(code: str, tool_context: ToolContext) -> dict:
    """Run PEP 8 checks (pycodestyle) plus naming-convention checks and compute a
    0-100 style score. If `code` is empty, the code stored in state is used.

    Args:
        code: The Python source to check.
    """
    code = extract_code(code) if code and code.strip() else tool_context.state.get(K.CODE_TO_REVIEW, "")
    result = style_of(code)
    tool_context.state[K.STYLE_SCORE] = result["score"]
    tool_context.state[K.STYLE_ISSUES] = result["issues"]
    return {"status": "success", **result}


# ---------------------------------------------------------------- history & reports
async def search_past_feedback(tool_context: ToolContext) -> dict:
    """Return this developer's previous review results (persisted across sessions)
    so feedback can point out recurring problems and improvement."""
    history = tool_context.state.get(K.REVIEW_HISTORY, [])
    return {"submission_count": tool_context.state.get(K.SUBMISSION_COUNT, 0),
            "recent_reviews": history[-5:]}


async def save_review_report(feedback_markdown: str, tool_context: ToolContext) -> dict:
    """Persist the final review as a versioned artifact and record it in the
    developer's history.

    Args:
        feedback_markdown: The complete Markdown review shown to the developer.
    """
    st = tool_context.state
    count = int(st.get(K.SUBMISSION_COUNT, 0)) + 1
    analysis = st.get(K.CODE_ANALYSIS) or {}
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "style_score": st.get(K.STYLE_SCORE),
        "max_complexity": (analysis.get("metrics") or {}).get("max_complexity"),
        "test_verdict": _verdict(st.get(K.TEST_RESULTS)),
    }
    st[K.SUBMISSION_COUNT] = count
    st[K.REVIEW_HISTORY] = (list(st.get(K.REVIEW_HISTORY, [])) + [entry])[-20:]
    st[K.FINAL_FEEDBACK] = feedback_markdown
    filename = f"review_{count:03d}.md"
    try:
        version = await tool_context.save_artifact(
            filename, types.Part.from_bytes(data=feedback_markdown.encode(), mime_type="text/markdown"))
    except ValueError:
        version = None
    return {"status": "saved", "artifact": filename, "version": version, "submission": count}


def _verdict(test_summary: Any) -> str:
    text = str(test_summary or "")
    for v in ("BROKEN", "BUGGY", "WORKING"):
        if v in text:
            return v
    return "UNKNOWN"


# ---------------------------------------------------------------- fix loop
async def validate_fixed_style(tool_context: ToolContext) -> dict:
    """Check the style of the fixed code (read from state) and compare with the original."""
    fixed = extract_code(str(tool_context.state.get(K.CODE_FIXES, "")))
    try:
        ast.parse(fixed)
    except SyntaxError as e:
        return {"status": "syntax_error", "line": e.lineno, "message": e.msg}
    result = style_of(fixed)
    tool_context.state[K.FIXED_STYLE_SCORE] = result["score"]
    return {"status": "success", "original_score": tool_context.state.get(K.STYLE_SCORE),
            "fixed_score": result["score"], "remaining_issues": result["issues"][:10]}


async def compile_fix_report(tool_context: ToolContext) -> dict:
    """Build a quantitative before/after report of the fix attempt (style scores,
    test verdicts, unified diff) from state."""
    st = tool_context.state
    original = st.get(K.CODE_TO_REVIEW, "")
    fixed = extract_code(str(st.get(K.CODE_FIXES, "")))
    diff = "".join(difflib.unified_diff(original.splitlines(True), fixed.splitlines(True),
                                        "original.py", "fixed.py"))
    before, after = _verdict(st.get(K.TEST_RESULTS)), _verdict(st.get(K.FIX_TEST_RESULTS))
    s0, s1 = st.get(K.STYLE_SCORE) or 0, st.get(K.FIXED_STYLE_SCORE) or 0
    status = ("SUCCESSFUL" if after == "WORKING" and s1 >= 90 else
              "PARTIAL" if (s1 > s0 or (before != "WORKING" and after == "WORKING")) else "FAILED")
    report = {"status": status, "style_score": {"before": s0, "after": s1},
              "tests": {"before": before, "after": after},
              "lines_changed": sum(1 for l in diff.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")),
              "diff": diff[:8000]}
    st[K.FIX_REPORT] = report
    st[K.FIX_STATUS] = status
    return report


def exit_fix_loop(tool_context: ToolContext) -> dict:
    """Call ONLY when the fix status is SUCCESSFUL to stop further fix iterations."""
    tool_context.actions.escalate = True
    return {"message": "Fix accepted; leaving the fix loop."}


async def save_fix_report(summary_markdown: str, tool_context: ToolContext) -> dict:
    """Save the fixed code and the fix summary as artifacts.

    Args:
        summary_markdown: The Markdown summary shown to the developer.
    """
    fixed = extract_code(str(tool_context.state.get(K.CODE_FIXES, "")))
    saved = []
    for name, data, mime in (("fixed_code.py", fixed, "text/x-python"),
                             ("fix_report.md", summary_markdown, "text/markdown")):
        try:
            await tool_context.save_artifact(name, types.Part.from_bytes(data=data.encode(), mime_type=mime))
            saved.append(name)
        except ValueError:
            pass
    return {"status": "saved", "artifacts": saved}
