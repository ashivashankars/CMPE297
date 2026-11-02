import os
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
TICKETS_DB = os.getenv("TICKETS_DB", str(HERE / "data" / "tickets.db"))
TICKET_SERVER = str(HERE / "mcp_server" / "ticket_server.py")

# Optional integrations - enabled only when configured.
MCP_TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "")                 # production DB path
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")      # GitHub remote MCP
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
ENABLE_STACKEXCHANGE = os.getenv("ENABLE_STACKEXCHANGE", "true").lower() == "true"
