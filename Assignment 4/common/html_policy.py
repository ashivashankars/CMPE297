"""Content policy for open-ended (model-written) HTML.

The sandboxed iframe is the real boundary (no same-origin, strict CSP, no network).
This server-side check is a second, cheaper layer: it rejects documents that try
to reach the network or escape the frame, so the model gets a readable error
instead of a silently broken view. A policy check alone is NOT a sandbox.
"""

import re

MAX_BYTES = 60_000

_RULES = [
    (r"<\s*script[^>]+src\s*=", "external <script src> is not allowed; inline your script"),
    (r"<\s*link[^>]+href\s*=\s*['\"]?https?:", "external stylesheets are not allowed"),
    (r"\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(", "network calls are not allowed inside a generated view"),
    (r"\bwindow\.top\b|\bparent\.document\b|\btop\.location\b", "the view may not touch the parent page"),
    (r"<\s*(iframe|object|embed)\b", "nested frames/plugins are not allowed"),
    (r"\bdocument\.cookie\b|\blocalStorage\b", "storage access is not allowed"),
]


class PolicyError(ValueError):
    pass


def check_html(html):
    """Raise PolicyError with a model-readable reason, or return the HTML unchanged."""
    if not isinstance(html, str) or not html.strip():
        raise PolicyError("html is empty")
    if len(html.encode()) > MAX_BYTES:
        raise PolicyError(f"html is {len(html.encode())} bytes; the limit is {MAX_BYTES}")
    for pattern, reason in _RULES:
        if re.search(pattern, html, re.I):
            raise PolicyError(reason)
    return html
