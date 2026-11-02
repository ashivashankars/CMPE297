"""Central configuration. Every model name is overridable from .env so the same
code runs on Google AI Studio (GOOGLE_API_KEY) or Vertex AI."""
import os

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:  # dotenv is optional at runtime
    pass

# Fast model for routing / JSON formatting, stronger model for research + synthesis.
FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
RESEARCH_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")

# Guardrails on fan-out cost: k companies analysed, m leads generated.
MAX_K = int(os.getenv("LEADGEN_MAX_COMPANIES", "10"))
MAX_M = int(os.getenv("LEADGEN_MAX_LEADS", "10"))
DEFAULT_K = 3
DEFAULT_M = 5
