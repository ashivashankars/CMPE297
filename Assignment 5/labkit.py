"""Small helpers shared by every lab script (paths, headers, result files, course repo)."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
RESULTS = ROOT / "results"
COURSE_REPO = ROOT / ".course_repo"
COURSE_URL = "https://github.com/dlmastery/simple-coding-harness.git"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def header(lab: str, title: str):
    bar = "=" * 78
    print(f"{bar}\n LAB {lab} - {title}\n Problem area: wind-turbine gearbox failure early warning (TurbineGym)\n{bar}")


def section(title: str):
    print(f"\n--- {title} " + "-" * max(0, 72 - len(title)))


def save(name: str, obj) -> pathlib.Path:
    RESULTS.mkdir(exist_ok=True)
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(obj, indent=2, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o)))
    print(f"\n[saved {p.relative_to(ROOT)}]")
    return p


def load(name: str):
    p = RESULTS / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"Missing {p}. Run the earlier lab first (or ./run_all.sh).")
    return json.loads(p.read_text())


def course_repo() -> pathlib.Path:
    """The course's own October-2026 demos live in the course repo; clone it once if needed."""
    if not (COURSE_REPO / "12_october_2026_papers").exists():
        print(f"(cloning {COURSE_URL} into {COURSE_REPO.name}/ ...)")
        subprocess.run(["git", "clone", "-q", "--depth", "1", COURSE_URL, str(COURSE_REPO)], check=True)
    return COURSE_REPO / "12_october_2026_papers"
