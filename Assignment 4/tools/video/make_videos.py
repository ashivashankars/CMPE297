"""Record the walkthrough videos: code walkthrough + terminal execution + live browser demo.

    ./start_all.sh &                       # the six codelab servers must be running
    python tools/video/make_videos.py      # all videos -> videos/*.mp4 (+ .srt narration)
    python tools/video/make_videos.py 03   # just one part

Every scene shows a caption bar with the narration line, so the video explains itself;
the same lines are written to videos/<part>.srt and docs/VIDEO_SCRIPT.md so you can
read them as a voice-over while you re-record.
"""

import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from scripts import PARTS  # noqa: E402

W, H = 1280, 720
OUT = ROOT / "videos"
TMP = ROOT / "videos" / ".raw"

CSS = """
* { box-sizing: border-box; } body { margin: 0; width: 1280px; height: 720px; overflow: hidden; background: #f6f5f1;
  font-family: ui-sans-serif, system-ui, sans-serif; color: #1d1d1b; }
.cap { position: fixed; left: 0; right: 0; bottom: 0; background: rgba(29,29,27,.94); color: #fff; padding: 14px 36px 16px;
  font-size: 21px; line-height: 1.38; z-index: 99999; min-height: 86px; }
.cap b { color: #f2a679; }
.tag { position: fixed; top: 12px; right: 16px; z-index: 99999; background: #b5532c; color: #fff; font: 600 13px ui-monospace, monospace;
  padding: 5px 10px; border-radius: 6px; }
.title { padding: 90px 90px 0; } .title h1 { font-size: 48px; margin: 0 0 8px; letter-spacing: -.02em; }
.title h2 { font-size: 24px; font-weight: 500; color: #6b6a64; margin: 0 0 36px; }
.title li { font-size: 23px; margin: 10px 0; } .title ul { padding-left: 26px; }
.code { padding: 22px 30px 0; } .file { font: 600 15px ui-monospace, monospace; color: #b5532c; margin-bottom: 8px; }
.codebox { background: #1e1f24; border-radius: 12px; padding: 14px 4px; height: 560px; overflow: hidden; }
.codebox pre { margin: 0; font: 14.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; color: #e9e4d8; }
.ln { display: inline-block; width: 46px; text-align: right; color: #6f6c64; margin-right: 14px; user-select: none; }
.hl { background: rgba(242,166,121,.20); display: block; border-left: 3px solid #f2a679; }
.nl { display: block; border-left: 3px solid transparent; }
.term { padding: 22px 30px 0; } .termbox { background: #121316; border-radius: 12px; height: 580px; overflow: hidden; padding: 14px 18px;
  font: 13px/1.45 ui-monospace, Menlo, monospace; color: #d8d4ca; white-space: pre; }
.termbox .cmd { color: #f2c38b; } .termbox .ok { color: #8fd19e; } .termbox .err { color: #ff9b8f; } .termbox .h { color: #f2a679; font-weight: 700; }
"""


def caption_html(text):
    text = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def page_shell(body, caption, tag):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}{HtmlFormatter(style='monokai').get_style_defs('.codebox')}"
            f"</style></head><body>{body}<div class='tag'>{html.escape(tag)}</div><div class='cap'>{caption_html(caption)}</div></body></html>")


def title_scene(s, tag):
    items = "".join(f"<li>{html.escape(b)}</li>" for b in s.get("bullets", []))
    return page_shell(f"<div class='title'><h1>{html.escape(s['title'])}</h1><h2>{html.escape(s.get('subtitle', ''))}</h2><ul>{items}</ul></div>",
                      s["caption"], tag)


def code_scene(s, tag):
    path = ROOT / s["file"]
    lines = path.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if re.search(s["at"], l))
    n = min(s.get("lines", 25), 25)   # what fits in the code box
    window = lines[start:start + n]
    hl_res = [re.compile(r) for r in s.get("hl", [])]
    alias = {".mjs": "x.js", ".oui": "x.py", ".jsonl": "x.json"}   # OpenUI Lang reads well with Python colors
    lexer = get_lexer_for_filename(alias.get(path.suffix, path.name))
    out = []
    for i, line in enumerate(window):
        code = highlight(line or " ", lexer, HtmlFormatter(nowrap=True)).rstrip("\n")
        cls = "hl" if any(r.search(line) for r in hl_res) else "nl"
        out.append(f"<span class='{cls}'><span class='ln'>{start + i + 1}</span>{code}</span>")
    body = f"<div class='code'><div class='file'>{html.escape(s['file'])}  ·  lines {start + 1}-{start + len(window)}</div>" \
           f"<div class='codebox'><pre>{''.join(out)}</pre></div></div>"
    return page_shell(body, s["caption"], tag)


def term_scene(s, tag):
    env = {**os.environ, "NO_COLOR": "1", "GENUI_DELAY": "0", "GENUI_LLM": "scripted"}
    res = subprocess.run(s["cmd"], shell=True, cwd=ROOT / s["cwd"], capture_output=True, text=True, env=env, timeout=120)
    text = (res.stdout + res.stderr).rstrip()
    lines = []
    for l in text.splitlines():
        cls = "ok" if "✓" in l else "err" if "✗" in l else "h" if l.startswith("━━") else ""
        l = l if len(l) <= 158 else l[:150] + "…"
        lines.append(f"<div class='{cls}'>{html.escape(l) or ' '}</div>")
    body = (f"<div class='term'><div class='termbox' id='tb'><div class='cmd'>$ cd {html.escape(s['cwd'])} && {html.escape(s['cmd'])}</div>"
            f"<div id='out'></div></div></div><template id='lines'>{''.join(lines)}</template>"
            f"<script>const all=[...document.getElementById('lines').content.children];const out=document.getElementById('out');"
            f"const tb=document.getElementById('tb');let i=0;const step=Math.max(15,{s['secs'] * 600}/Math.max(all.length,1));"
            f"const t=setInterval(()=>{{if(i>=all.length){{clearInterval(t);return;}}out.append(all[i++]);tb.scrollTop=tb.scrollHeight;}},step);</script>")
    return page_shell(body, s["caption"], tag)


INJECT = """([cap, tag]) => {
  for (const id of ['__cap', '__tag']) document.getElementById(id)?.remove();
  const st = document.getElementById('__vs') || document.head.appendChild(Object.assign(document.createElement('style'), {id: '__vs'}));
  st.textContent = `CSS_HERE body { zoom: .8; } .split .pane { min-height: 300px; } main.split { padding-bottom: 130px; }`;
  const c = document.createElement('div'); c.id = '__cap'; c.className = 'cap'; c.innerHTML = cap; document.body.append(c);
  const t = document.createElement('div'); t.id = '__tag'; t.className = 'tag'; t.textContent = tag; document.body.append(t);
}""".replace("CSS_HERE", ".cap { position: fixed; left: 0; right: 0; bottom: 0; background: rgba(29,29,27,.94); color: #fff; padding: 14px 36px 16px; font-size: 26px; line-height: 1.38; z-index: 99999; min-height: 100px; font-family: system-ui, sans-serif; pointer-events: none; } .cap b { color: #f2a679; } .tag { position: fixed; bottom: 112px; right: 16px; z-index: 99999; background: #b5532c; color: #fff; font: 600 16px ui-monospace, monospace; padding: 5px 10px; border-radius: 6px; pointer-events: none; }")


def locate(page, spec):
    """spec: a CSS selector on the page, or a list = a path through iframes ending in a selector."""
    if isinstance(spec, str):
        return page.locator(spec).first
    loc = page
    for sel in spec[:-1]:
        loc = loc.frame_locator(sel).first
    return loc.locator(spec[-1]).first


def web_scene(page, s, tag):
    page.goto(f"http://127.0.0.1:{s['port']}/?mode={s['mode']}")
    page.evaluate(INJECT, [caption_html(s["caption"]), tag])
    t0 = time.time()
    for step in s.get("steps", []):
        kind = step[0]
        if kind == "idle":
            page.wait_for_function("document.body.dataset.state === 'idle'", timeout=30000)
        elif kind == "hold":
            page.wait_for_timeout(int(step[1] * 1000))
        elif kind == "click":
            target = locate(page, step[1])
            target.scroll_into_view_if_needed()
            if isinstance(step[1], str):
                target.hover()
                page.wait_for_timeout(400)
                target.click()
            else:   # inside sandboxed frames: CSS zoom confuses hit-testing, so click the element directly
                page.wait_for_timeout(400)
                target.evaluate("el => el.click()")
        elif kind == "scroll":
            page.evaluate(f"window.scrollTo({{top: {step[1]}, behavior: 'smooth'}})")
        elif kind == "caption":
            page.evaluate(INJECT, [caption_html(step[1]), tag])
        elif kind == "slider":
            frame = locate(page, step[1])
            frame.evaluate("(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); }", step[2])
    left = s.get("secs", 0) - (time.time() - t0)
    if left > 0:
        page.wait_for_timeout(int(left * 1000))


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def record(key):
    part = PARTS[key]
    TMP.mkdir(parents=True, exist_ok=True)
    tag = part["tag"]
    cues, t = [], 0.0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(TMP / key),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        start = time.time()
        for s in part["scenes"]:
            t = time.time() - start
            if s["kind"] == "web":
                web_scene(page, s, tag)
                caps = [s["caption"]] + [st[1] for st in s.get("steps", []) if st[0] == "caption"]
            else:
                content = {"title": title_scene, "code": code_scene, "term": term_scene}[s["kind"]](s, tag)
                page.set_content(content)
                page.wait_for_timeout(int(s["secs"] * 1000))
                caps = [s["caption"]]
            cues.append((t, time.time() - start, " / ".join(caps)))
        video = page.video.path()
        ctx.close()
        browser.close()
    OUT.mkdir(exist_ok=True)
    name = part["file"]
    tmp = OUT / f"{name}.tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.rename(OUT / f"{name}.mp4")
    Path(video).unlink(missing_ok=True)
    with open(OUT / f"{name}.srt", "w") as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{re.sub(r'[*]', '', text)}\n\n")
    print(f"{name}.mp4  {cues[-1][1]:.0f}s  {len(part['scenes'])} scenes", flush=True)
    return cues


def write_script(all_cues):
    lines = ["# Video narration scripts", "",
             "Each video in `videos/` has these lines burned in as captions (and as an `.srt` file).",
             "Read them aloud while re-recording, or record a voice-over on top of the existing video.", ""]
    for key, cues in all_cues.items():
        lines += [f"## {PARTS[key]['file']}.mp4 - {PARTS[key]['tag']}", "", "| Time | Narration |", "|---|---|"]
        lines += [f"| {srt_time(a)[3:8]} | {text.replace('|', '/')} |" for a, _, text in cues]
        lines.append("")
    (ROOT / "docs" / "VIDEO_SCRIPT.md").write_text("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1:] == ["--script"]:   # rebuild docs/VIDEO_SCRIPT.md from per-part runs
        merged = {}
        for f in sorted(OUT.glob(".cues_*.json")):
            merged.update(json.loads(f.read_text()))
        write_script({k: merged[k] for k in sorted(merged)})
        sys.exit(0)
    keys = [k for k in PARTS if not sys.argv[1:] or any(k.startswith(a) for a in sys.argv[1:])]
    cues = {}
    for k in keys:
        cues[k] = record(k)
    if not sys.argv[1:]:
        write_script(cues)
    else:
        (OUT / f".cues_{'_'.join(keys)}.json").write_text(json.dumps(cues))
