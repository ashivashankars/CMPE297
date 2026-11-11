"""Screenshot every mode of a running codelab (and the page after one action).

    python tools/shoot.py http://127.0.0.1:8001 docs/screenshots/01_a2ui
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MODES = ("static", "declarative", "open_ended", "mixed")


def wait_idle(page):
    page.wait_for_function("document.body.dataset.state === 'idle'", timeout=30000)
    page.wait_for_timeout(700)   # let sandboxed frames run their scripts and resize


def main(url, out, click_action=True):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        for mode in MODES:
            page.goto(f"{url}/?mode={mode}")
            wait_idle(page)
            page.screenshot(path=str(out / f"{mode}.png"), full_page=True)
            if click_action:
                outer = page.frame_locator("#surface iframe").first
                candidates = [
                    page.locator("#surface button.c-button"),                       # catalog Button on the page
                    page.frame_locator("#surface iframe").first.locator("#legend div"),  # sandboxed HTML
                    outer.locator("button.c-button"),                                # inside an MCP App view
                    outer.locator(".region button"),
                    outer.frame_locator("iframe").first.locator("#legend div"),     # nested sandbox in a view
                ]
                for target in candidates:
                    try:
                        if target.count():
                            target.first.click()
                            wait_idle(page)
                            page.wait_for_timeout(1500)
                            page.screenshot(path=str(out / f"{mode}_action.png"), full_page=True)
                            break
                    except Exception:  # noqa: BLE001 - frame not present for this part
                        continue
            errs = page.locator("#surface .c-error").all_inner_texts()
            print(f"{mode:<12} rendered types: {sorted(set(page.locator('#surface [data-type]').evaluate_all('es => es.map(e => e.dataset.type)')))}  errors={errs}")
        browser.close()
    if errors:
        print("PAGE ERRORS:", errors)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
