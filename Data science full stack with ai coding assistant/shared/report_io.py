"""Write pipeline reports as strict JSON (NaN/inf -> null, numpy -> python)."""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def dump(obj, path: pathlib.Path) -> None:
    path.write_text(json.dumps(_clean(obj), indent=1, allow_nan=False))
