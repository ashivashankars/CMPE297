"""Plain function tools used by the root agent."""
from typing import Optional

from google.adk.tools import ToolContext

from . import config


def set_research_parameters(
    tool_context: ToolContext, k: Optional[int] = None, m: Optional[int] = None
) -> dict:
    """Store how many successful companies to study (k) and/or how many new leads
    to find (m). Values are clamped to 1-10 to bound research cost.

    Args:
        k: Number of successful companies to analyse for pattern discovery.
        m: Number of new leads to find.
    """
    updated = {}
    if k is not None:
        tool_context.state["k"] = max(1, min(int(k), config.MAX_K))
        updated["k"] = tool_context.state["k"]
    if m is not None:
        tool_context.state["m"] = max(1, min(int(m), config.MAX_M))
        updated["m"] = tool_context.state["m"]
    return {"status": "ok", "updated": updated}


def get_research_status(tool_context: ToolContext) -> dict:
    """Return the current research state (market, parameters, stage, whether patterns
    and a report already exist)."""
    st = tool_context.state
    return {
        "country": st.get("country"),
        "industry": st.get("industry"),
        "k": st.get("k"),
        "m": st.get("m"),
        "stage": st.get("stage"),
        "has_patterns": bool(st.get("discovered_patterns")),
        "has_report": bool(st.get("final_report")),
    }
