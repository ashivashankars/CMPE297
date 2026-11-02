"""Production guardrails implemented as ADK callbacks (deterministic code, not prompts)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from google.genai import types

from . import config

WRITE_TOOLS = {"add_to_shopping_list", "remove_from_shopping_list", "place_order",
               "update_order_delivery_method", "cancel_order"}


def signed_in_email(ctx) -> str:
    """Identity comes from the session, never from the model:
    1. state['user:email'] (set by your frontend / auth layer), else
    2. the ADK user_id when it is an email (e.g. IAP / Firebase auth), else
    3. the demo user."""
    email = ctx.state.get("user:email")
    if email:
        return email
    uid = getattr(ctx, "user_id", "") or ""
    return uid if "@" in uid else config.DEMO_USER_EMAIL


def init_session(callback_context) -> Optional[types.Content]:
    """before_agent_callback: resolve the shopper once per session."""
    st = callback_context.state
    if not st.get("user:email"):
        st["user:email"] = signed_in_email(callback_context)
    if not st.get("user:name"):
        st["user:name"] = st["user:email"].split("@")[0].title()
    return None


def enforce_identity(tool, args: dict[str, Any], tool_context) -> Optional[dict]:
    """before_tool_callback: overwrite user_email so a prompt-injected or confused
    model cannot read or change another customer's cart or orders."""
    if "user_email" in args or tool.name in WRITE_TOOLS:
        args["user_email"] = signed_in_email(tool_context)
    return None  # continue with the (patched) args


def audit_tool_call(tool, args: dict[str, Any], tool_context, tool_response) -> Optional[dict]:
    """after_tool_callback: append executed write operations to an audit trail in state.
    Calls that are only awaiting human confirmation (not executed yet) are skipped."""
    pending = isinstance(tool_response, dict) and "error" in tool_response and "content" not in tool_response
    if tool.name in WRITE_TOOLS and not pending:
        log = list(tool_context.state.get("audit_log", []))
        log.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool.name,
                    "args": {k: v for k, v in args.items() if k != "user_email"}})
        tool_context.state["audit_log"] = log[-50:]
    return None
