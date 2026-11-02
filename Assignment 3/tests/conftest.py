import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

# Never let tests hit a real model/API by accident.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
