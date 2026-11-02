"""Callbacks keep the conversation state machine deterministic: the LLM decides
*what* to do, but state transitions happen in code."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from google.genai import types

from . import config


def init_state(callback_context) -> Optional[types.Content]:
    """before_agent_callback: seed defaults so prompt templates always resolve."""
    st = callback_context.state
    st["current_date"] = date.today().isoformat()
    for key, default in (("country", ""), ("industry", ""), ("stage", "initial")):
        if key not in st:
            st[key] = default
    return None


def _clamp(value: Any, upper: int) -> Optional[int]:
    try:
        return max(1, min(int(value), upper))
    except (TypeError, ValueError):
        return None


def update_stage(tool, args: dict, tool_context, tool_response) -> Optional[dict]:
    """after_tool_callback: move the state machine forward after each tool."""
    st = tool_context.state
    name = getattr(tool, "name", "")

    if name == "IntentExtractor":
        result = st.get("intent_result") or {}
        if isinstance(result, dict):
            # A new market invalidates earlier research.
            new_market = (
                (result.get("country") and result["country"] != st.get("country"))
                or (result.get("industry") and result["industry"] != st.get("industry"))
            )
            if result.get("country"):
                st["country"] = result["country"]
            if result.get("industry"):
                st["industry"] = result["industry"]
            if result.get("k"):
                st["k"] = _clamp(result["k"], config.MAX_K)
            if result.get("m"):
                st["m"] = _clamp(result["m"], config.MAX_M)
            if new_market and st.get("stage") in ("patterns_ready", "leads_ready"):
                st["stage"] = "initial"
                st["discovered_patterns"] = None

    elif name == "PatternDiscoveryPipeline":
        if st.get("discovered_patterns"):
            st["stage"] = "patterns_ready"

    elif name == "LeadGenerationPipeline":
        if st.get("final_report"):
            st["stage"] = "leads_ready"
    return None


async def save_report_artifact(callback_context) -> Optional[types.Content]:
    """after_agent_callback on the report writer: persist the Markdown report as a
    versioned ADK artifact (visible in the adk web Artifacts tab)."""
    report = callback_context.state.get("final_report")
    if report:
        part = types.Part.from_bytes(data=report.encode("utf-8"), mime_type="text/markdown")
        try:
            version = await callback_context.save_artifact("lead_report.md", part)
            callback_context.state["report_artifact_version"] = version
        except ValueError:
            # No artifact service configured (e.g. bare Runner) - report stays in state.
            pass
    return None
