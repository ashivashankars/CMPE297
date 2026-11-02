"""Browser test + screenshot tour: opens every tab of every app, fails on JS errors.

  python scripts/screenshots.py            # all projects
  python scripts/screenshots.py 01_nyc_taxi
Screenshots land in projects/<slug>/screenshots/<nn>_<tab>.png
"""
from __future__ import annotations

import contextlib
import pathlib
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8765


@contextlib.contextmanager
def server():
    proc = subprocess.Popen([sys.executable, "serve.py", "--port", str(PORT)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(240):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                break
        time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError(proc.stderr.read().decode())
    try:
        yield f"http://127.0.0.1:{PORT}"
    finally:
        proc.terminate()


def main(only: list[str]) -> int:
    failures = 0
    with server() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(base)
        page.wait_for_selector(".pcard")
        (ROOT / "docs").mkdir(exist_ok=True)
        page.screenshot(path=ROOT / "docs" / "home.png", full_page=True)
        slugs = [a.get_attribute("href").split("/")[2] for a in page.query_selector_all(".pcard")]
        for slug in slugs:
            if only and slug not in only:
                continue
            out = ROOT / "projects" / slug / "screenshots"
            out.mkdir(exist_ok=True)
            page.goto(f"{base}/p/{slug}/")
            page.wait_for_selector("nav.tabs button")
            page.wait_for_timeout(2500)
            tabs = [b.get_attribute("data-tab") for b in page.query_selector_all("nav.tabs button")]
            for i, tab in enumerate(tabs, 1):
                page.click(f'nav.tabs button[data-tab="{tab}"]')
                page.wait_for_timeout(1800)
                name = tab.lower().replace(" ", "_")
                page.screenshot(path=out / f"{i:02d}_{name}.png", full_page=True)
            status = "OK" if not errors else f"{len(errors)} ERRORS: {errors[:3]}"
            print(f"{slug:32s} {len(tabs)} tabs  {status}")
            failures += bool(errors)
            errors.clear()
        browser.close()
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
