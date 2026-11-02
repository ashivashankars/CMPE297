"""Hub server: one FastAPI process that serves all six project apps.

Each project folder contains
  app.py          -> defines `router` (APIRouter) and `META` (title, blurb, accent)
  static/         -> the project's single-page UI (index.html + app.js)
  code_tour.json  -> annotated code sections shown in the "Code tour" tab

The hub mounts project N at /p/<slug>/ (UI) and /p/<slug>/api/ (JSON API) and adds
a shared /p/<slug>/api/code_tour endpoint that syntax-highlights the annotated
source ranges with Pygments, so the code walkthrough lives inside each app.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
SHARED_STATIC = ROOT / "shared" / "static"


def load_project(folder: pathlib.Path):
    """Import projects/<folder>/app.py under a unique module name."""
    name = f"proj_{folder.name}"
    spec = importlib.util.spec_from_file_location(name, folder / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(folder))  # lets app.py import its sibling pipeline module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    sys.path.remove(str(folder))
    return module


def code_tour(folder: pathlib.Path) -> list[dict]:
    """Return highlighted HTML for each annotated section in code_tour.json."""
    tour_file = folder / "code_tour.json"
    if not tour_file.exists():
        return []
    sections = []
    for item in json.loads(tour_file.read_text()):
        path = (folder / item["file"]).resolve()
        if folder not in path.parents:  # never serve files outside the project
            raise HTTPException(400, "bad path in code tour")
        lines = path.read_text().splitlines()
        start, end = _locate(lines, item)
        snippet = "\n".join(lines[start - 1 : end])
        fmt = HtmlFormatter(linenos="inline", linenostart=start, cssclass="hl")
        sections.append({
            "title": item["title"], "note": item["note"], "file": item["file"],
            "start": start, "end": end,
            "html": highlight(snippet, get_lexer_for_filename(path.name), fmt),
        })
    return sections


def _locate(lines: list[str], item: dict) -> tuple[int, int]:
    """Find a section by an anchor string so line numbers never go stale."""
    if "anchor" not in item:
        return item["start"], item["end"]
    for i, line in enumerate(lines, 1):
        if item["anchor"] in line:
            return i, min(len(lines), i + item.get("lines", 20) - 1)
    raise HTTPException(500, f"anchor not found: {item['anchor']}")


def create_app() -> FastAPI:
    app = FastAPI(title="Data Science Full-Stack Lab")
    registry = []
    for folder in sorted(p for p in PROJECTS.iterdir() if (p / "app.py").exists()):
        mod = load_project(folder)
        slug = folder.name
        meta = {"slug": slug, **mod.META}
        registry.append(meta)
        app.include_router(mod.router, prefix=f"/p/{slug}/api")

        def _tour(folder=folder):
            return code_tour(folder)

        app.add_api_route(f"/p/{slug}/api/code_tour", _tour, methods=["GET"])
        app.add_api_route(f"/p/{slug}/api/meta", (lambda m=meta: m), methods=["GET"])
        app.mount(f"/p/{slug}", StaticFiles(directory=folder / "static", html=True), name=slug)

    @app.get("/api/projects")
    def projects():
        return registry

    @app.get("/", response_class=HTMLResponse)
    def home():
        return FileResponse(SHARED_STATIC / "home.html")

    @app.get("/shared/pygments.css")
    def pyg_css():
        return HTMLResponse(HtmlFormatter(style="friendly").get_style_defs(".hl"), media_type="text/css")

    # mounted last so the explicit /shared/pygments.css route above wins
    app.mount("/shared", StaticFiles(directory=SHARED_STATIC), name="shared")
    return app


app = create_app()
