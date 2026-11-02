import os
import shutil

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")

# Gemini CLI process settings
GEMINI_CLI_BIN = os.getenv("GEMINI_CLI_BIN", "gemini")
GEMINI_CLI_MODEL = os.getenv("GEMINI_CLI_MODEL", "")          # empty = CLI default
GEMINI_CLI_TIMEOUT_S = int(os.getenv("GEMINI_CLI_TIMEOUT_S", "600"))
GEMINI_CLI_MAX_CALLS = int(os.getenv("GEMINI_CLI_MAX_CALLS", "6"))  # per session
GEMINI_CLI_MAX_OUTPUT_CHARS = int(os.getenv("GEMINI_CLI_MAX_OUTPUT_CHARS", "20000"))
# Read-only by default. "yolo" lets the CLI edit files/run shell in the cloned
# workspace copy - only enable inside a sandbox (e.g. the Cloud Run container).
GEMINI_CLI_APPROVAL = os.getenv("GEMINI_CLI_APPROVAL", "default")

WORKSPACE_DIR = os.getenv("GEMINI_CLI_WORKSPACE", "/tmp/adk_gemini_cli_workspace")
CLONE_TIMEOUT_S = int(os.getenv("GIT_CLONE_TIMEOUT_S", "300"))
MAX_LOOP_ITERATIONS = int(os.getenv("GEMINI_CLI_REFINE_ITERATIONS", "2"))


def cli_path() -> str | None:
    return shutil.which(GEMINI_CLI_BIN)
