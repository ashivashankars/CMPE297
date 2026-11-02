import os
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
STORE_DB = os.getenv("STORE_DB", str(HERE / "data" / "store.db"))
STORE_SERVER = str(HERE / "mcp_server" / "store_server.py")
# Demo identity when no authenticated user is present (adk web has no login).
DEMO_USER_EMAIL = os.getenv("DEMO_USER_EMAIL", "alex@example.com")
# Human-in-the-loop confirmation for money-moving tools (adk web shows a dialog).
REQUIRE_ORDER_CONFIRMATION = os.getenv("REQUIRE_ORDER_CONFIRMATION", "true").lower() == "true"
MCP_TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "")   # production: AlloyDB via MCP Toolbox
