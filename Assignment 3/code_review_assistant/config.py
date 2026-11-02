import os

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

WORKER_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")   # analysis, tools
CRITIC_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")      # feedback & fixes
MAX_FIX_ITERATIONS = int(os.getenv("CODE_REVIEW_MAX_FIX_ITERATIONS", "3"))
MAX_CODE_CHARS = int(os.getenv("CODE_REVIEW_MAX_CODE_CHARS", "60000"))
MAX_LINE_LENGTH = int(os.getenv("CODE_REVIEW_MAX_LINE_LENGTH", "100"))
