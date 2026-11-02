"""Root agent for (e): production-quality e-commerce agent.

Tools come from the GenAI Sports MCP server (stdio, SQLite) - or, when
MCP_TOOLBOX_URL is set, from MCP Toolbox for Databases on AlloyDB.
Checkout tools live in a separate toolset that requires human confirmation.
"""
import logging
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from . import config, prompts
from .guards import audit_tool_call, enforce_identity, init_session

log = logging.getLogger(__name__)
CHECKOUT_TOOLS = ["place_order", "cancel_order"]
CATALOG_TOOLS = [
    "search_products", "search_products_by_brand", "get_product_details", "check_inventory",
    "add_to_shopping_list", "remove_from_shopping_list", "show_shopping_list",
    "find_nearby_stores", "list_delivery_methods", "check_order_status",
    "update_order_delivery_method",
]


def _store_server(tool_filter, require_confirmation=False) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable, args=[config.STORE_SERVER],
                env={"STORE_DB": config.STORE_DB, "PYTHONUNBUFFERED": "1"}),
            timeout=30),
        tool_filter=tool_filter,
        require_confirmation=require_confirmation,
    )


def build_tools() -> list:
    if config.MCP_TOOLBOX_URL:
        try:
            from google.adk.tools.toolbox_toolset import ToolboxToolset

            return [ToolboxToolset(server_url=config.MCP_TOOLBOX_URL, toolset_name="store_toolset")]
        except Exception as e:  # noqa: BLE001
            log.warning("MCP Toolbox unavailable (%s); falling back to local MCP server.", e)
    return [
        _store_server(CATALOG_TOOLS),
        _store_server(CHECKOUT_TOOLS, require_confirmation=config.REQUIRE_ORDER_CONFIRMATION),
    ]


root_agent = LlmAgent(
    name="Finn",
    description="Sports shopping assistant: search, cart, store finder, checkout and order management.",
    model=config.MODEL,
    instruction=prompts.INSTRUCTION,
    tools=build_tools(),
    before_agent_callback=init_session,
    before_tool_callback=enforce_identity,
    after_tool_callback=audit_tool_call,
)
