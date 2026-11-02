"""Tool wiring for the bug assistant. Four kinds of ADK tools are shown:

1. Function tool        - get_current_date
2. Built-in tool        - google_search, wrapped in an AgentTool
3. MCP tools            - (a) our ticket MCP server over stdio  [always on]
                           (b) MCP Toolbox for Databases       [if MCP_TOOLBOX_URL]
                           (c) GitHub's remote MCP server       [if GITHUB token]
4. Third-party tool     - LangChain StackExchange tool          [if installed]
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool import (McpToolset, StdioConnectionParams,
                                       StreamableHTTPConnectionParams)
from mcp import StdioServerParameters

from . import config

log = logging.getLogger(__name__)

TICKET_TOOLS = [
    "search_tickets", "get_ticket_by_id", "get_tickets_by_assignee", "get_tickets_by_status",
    "get_tickets_by_priority", "get_tickets_by_date_range", "create_new_ticket",
    "update_ticket_status", "update_ticket_priority",
]


def get_current_date() -> dict:
    """Get today's date (YYYY-MM-DD). Use it to resolve phrases like 'last week'."""
    return {"current_date": datetime.now().strftime("%Y-%m-%d")}


search_agent = LlmAgent(
    name="google_search_agent",
    model=config.MODEL,
    description="Searches the web (docs, release notes, known issues, CVEs).",
    instruction="You are a Google Search specialist. Answer concisely and include source URLs.",
    tools=[google_search],
)
search_tool = AgentTool(agent=search_agent)


def ticket_mcp_toolset() -> McpToolset:
    """Local QuantumRoast ticket MCP server, launched as a subprocess over stdio."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[config.TICKET_SERVER],
                env={"TICKETS_DB": config.TICKETS_DB, "PYTHONUNBUFFERED": "1"},
            ),
            timeout=30,
        ),
        tool_filter=TICKET_TOOLS,
    )


def toolbox_toolset():
    """Production path: MCP Toolbox for Databases serving deployment/toolbox/tools.yaml
    against Cloud SQL / AlloyDB Postgres with pgvector."""
    if not config.MCP_TOOLBOX_URL:
        return None
    try:
        from google.adk.tools.toolbox_toolset import ToolboxToolset

        return ToolboxToolset(server_url=config.MCP_TOOLBOX_URL, toolset_name="tickets_toolset")
    except Exception as e:  # noqa: BLE001
        log.warning("MCP Toolbox unavailable (%s); using local ticket MCP server.", e)
        return None


def github_mcp_toolset():
    """GitHub's hosted MCP server (streamable HTTP) - read-only subset."""
    if not config.GITHUB_TOKEN:
        return None
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=config.GITHUB_MCP_URL,
            headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}"},
        ),
        tool_filter=["search_repositories", "search_issues", "list_issues", "get_issue",
                     "list_pull_requests", "get_pull_request"],
    )


def stackexchange_tool():
    if not config.ENABLE_STACKEXCHANGE:
        return None
    try:
        from google.adk.tools.langchain_tool import LangchainTool
        from langchain_community.tools import StackExchangeTool
        from langchain_community.utilities import StackExchangeAPIWrapper

        return LangchainTool(tool=StackExchangeTool(api_wrapper=StackExchangeAPIWrapper()))
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def build_tools() -> list:
    tools: list = [get_current_date, search_tool]
    tools.append(toolbox_toolset() or ticket_mcp_toolset())
    for optional in (github_mcp_toolset(), stackexchange_tool()):
        if optional is not None:
            tools.append(optional)
    return tools
