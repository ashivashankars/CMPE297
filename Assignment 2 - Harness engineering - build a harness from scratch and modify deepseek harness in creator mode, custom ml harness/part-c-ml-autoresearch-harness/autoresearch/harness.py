"""
harness.py - an end-to-end AUTORESEARCH harness for ML experiments.

The researcher (an LLM, or a DSH agent through the dsh-autoresearch plugin)
only ever proposes ONE small edit to train.py plus a hypothesis. Everything
that decides whether the idea was good is owned by this harness:

    propose -> apply edit -> integrity gates -> frozen eval (time budget)
            -> keep if better by >= MIN_DELTA, else revert -> log -> repeat
    finalize: score the best kept model ONCE on the hidden test split

Gates (the "anti-cheat" layer):
  frozen   prepare.py / evaluate.py / data/*.csv must hash the same as at reset
  leakage  train.py may not reference forbidden columns (post-outcome data)
  budget   evaluation must finish within --budget seconds
  sanity   a jump that is too good to be true is rejected for human review

Commands
  python harness.py reset                          baseline train.py, hash frozen files, score baseline
  python harness.py run --iterations 6             LLM researcher loop (OpenRouter or HARNESS_MOCK)
  python harness.py step --hypothesis H --edits E  one externally proposed experiment (E = JSON list or file)
  python harness.py status                         leaderboard
  python harness.py finalize                       test-set score of the best model + report.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # assignment folder
sys.path.insert(0, os.path.join(ROOT, "part-a-harness-from-scratch"))  # reuse Part A's llm.py

TRAIN = os.path.join(HERE, "train.py")
BASELINE = os.path.join(HERE, "train_baseline.py")
STATE = os.path.join(HERE, "runs")
RESULTS = os.path.join(STATE, "results.tsv")
BEST = os.path.join(STATE, "best.json")
FROZEN_FILES = ["prepare.py", "evaluate.py", "data/train.csv", "data/val.csv", "data/test.csv"]
FORBIDDEN = ["refund_amount", "test.csv", "churned"]
MIN_DELTA = 0.001        # smaller gains are treated as noise
SUSPICIOUS_JUMP = 0.08   # bigger single-step gains are held for human review


# ------------------------------------------------------------------ helpers
def sha(path: str) -> str:
    with open(os.path.join(HERE, path), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def read(path: str) -> str:
    with open(path) as f:
        return f.read()


def load_best() -> dict:
    return {**(b := json.load(open(BEST))), "path": os.path.join(HERE, b["path"])} if os.path.exists(BEST) else {}


def log_result(row: dict) -> None:
    new = not os.path.exists(RESULTS)
    with open(RESULTS, "a") as f:
        if new:
            f.write("iter\tstatus\tval_auc\tdelta\tseconds\thypothesis\n")
        f.write("\t".join(str(row.get(k, "")) for k in
                          ("iter", "status", "val_auc", "delta", "seconds", "hypothesis")) + "\n")


def rows() -> list[dict]:
    if not os.path.exists(RESULTS):
        return []
    lines = read(RESULTS).strip().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]


def evaluate(path: str, budget: int, final: bool = False) -> dict:
    cmd = [sys.executable, os.path.join(HERE, "evaluate.py"), path] + (["--final"] if final else [])
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired:
        return {"error": f"timeout: evaluation exceeded the {budget}s budget"}
    if p.returncode != 0:
        tail = (p.stderr.strip().splitlines() or ["unknown error"])[-1]
        return {"error": tail}
    return json.loads(p.stdout.strip().splitlines()[-1])


def apply_edits(src: str, edits: list[dict]) -> str:
    for e in edits:
        n = src.count(e["old"])
        if n != 1:
            raise ValueError(f"edit target found {n} times (must be exactly once): {e['old'][:60]!r}")
        src = src.replace(e["old"], e["new"])
    return src


# ------------------------------------------------------------------ gates
def gate_frozen() -> str | None:
    saved = load_best().get("frozen", {})
    changed = [f for f in FROZEN_FILES if saved.get(f) != sha(f)]
    return f"frozen files changed: {', '.join(changed)}" if changed else None


def gate_leakage(src: str) -> str | None:
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())  # ignore comments
    hits = [w for w in FORBIDDEN if w in code]
    return f"uses forbidden data: {', '.join(hits)} (see program.md rule 2)" if hits else None


# ------------------------------------------------------------------ one experiment
def experiment(hypothesis: str, edits: list[dict], budget: int = 60) -> dict:
    best = load_best()
    it = len(rows())
    current = read(TRAIN)
    row = {"iter": it, "hypothesis": hypothesis.replace("\t", " ")}
    try:
        candidate = apply_edits(current, edits)
    except Exception as e:
        row.update(status="bad-edit", val_auc="-", delta="-", seconds=0, reason=str(e))
        log_result(row)
        return row

    reason = gate_frozen() or gate_leakage(candidate)
    if reason:
        row.update(status="rejected", val_auc="-", delta="-", seconds=0, reason=reason)
        log_result(row)
        return row

    with open(TRAIN, "w") as f:
        f.write(candidate)
    shutil.copy(TRAIN, os.path.join(STATE, f"exp_{it:03d}_train.py"))
    res = evaluate(TRAIN, budget)
    if "error" in res:
        shutil.copy(best["path"], TRAIN)                            # revert
        row.update(status="crash", val_auc="-", delta="-", seconds="-", reason=res["error"])
        log_result(row)
        return row

    auc, delta = res["val_auc"], round(res["val_auc"] - best["val_auc"], 4)
    row.update(val_auc=auc, delta=f"{delta:+.4f}", seconds=res["seconds"], features=res["n_features"])
    if delta > SUSPICIOUS_JUMP or auc > 0.98:
        shutil.copy(best["path"], TRAIN)
        row.update(status="rejected", reason=f"suspicious jump {delta:+.3f}; held for human review")
    elif delta >= MIN_DELTA:
        keep = os.path.join(STATE, "best_train.py")
        shutil.copy(TRAIN, keep)
        best.update(val_auc=auc, path="runs/best_train.py", iter=it, hypothesis=hypothesis, features=res["features"])
        json.dump(best, open(BEST, "w"), indent=1)
        row["status"] = "keep"
    else:
        shutil.copy(best["path"], TRAIN)                            # revert
        row.update(status="discard", reason=f"gain {delta:+.4f} < min {MIN_DELTA}")
    log_result(row)
    return row


def show(row: dict) -> str:
    icon = {"keep": "KEEP   ", "discard": "discard", "crash": "CRASH  ", "rejected": "REJECT ",
            "bad-edit": "bad-edit"}[row["status"]]
    s = f"[exp {row['iter']}] {icon} val_auc={row['val_auc']} ({row['delta']})  {row['hypothesis']}"
    return s + (f"\n          -> {row['reason']}" if row.get("reason") else "")


# ------------------------------------------------------------------ commands
def cmd_reset(_):
    shutil.rmtree(STATE, ignore_errors=True)
    os.makedirs(STATE)
    shutil.copy(BASELINE, TRAIN)
    res = evaluate(TRAIN, 120)
    keep = os.path.join(STATE, "best_train.py")
    shutil.copy(TRAIN, keep)
    json.dump({"val_auc": res["val_auc"], "path": "runs/best_train.py", "iter": 0, "hypothesis": "baseline",
               "features": res["features"], "frozen": {f: sha(f) for f in FROZEN_FILES}},
              open(BEST, "w"), indent=1)
    log_result({"iter": 0, "status": "keep", "val_auc": res["val_auc"], "delta": "+0.0000",
                "seconds": res["seconds"], "hypothesis": "baseline: logistic regression on numeric columns"})
    print(f"[reset] baseline val_auc = {res['val_auc']}   frozen files hashed: {len(FROZEN_FILES)}")


def cmd_status(_):
    print(f"{'exp':>3}  {'status':8} {'val_auc':>7} {'delta':>8}  hypothesis")
    for r in rows():
        print(f"{r['iter']:>3}  {r['status']:8} {r['val_auc']:>7} {r['delta']:>8}  {r['hypothesis'][:70]}")
    b = load_best()
    print(f"\nbest: exp {b.get('iter')}  val_auc={b.get('val_auc')}  ({b.get('hypothesis')})")


def cmd_step(a):
    edits = a.edits
    edits = json.load(open(edits)) if os.path.exists(edits) else json.loads(edits)
    row = experiment(a.hypothesis, edits, a.budget)
    print(show(row))
    print(json.dumps({k: row.get(k) for k in ("status", "val_auc", "delta", "reason")}))


RESEARCHER = """You are an ML researcher running careful experiments.
Reply with ONLY a JSON object: {"hypothesis": "...", "edits": [{"old": "...", "new": "..."}]}
Each `old` must be an exact, unique snippet of the current train.py. Propose ONE idea."""


def ask_researcher(chat) -> dict:
    history = "\n".join(f"{r['iter']}\t{r['status']}\t{r['val_auc']}\t{r['delta']}\t{r['hypothesis']}" for r in rows())
    prompt = (f"# program.md\n{read(os.path.join(HERE, 'program.md'))}\n\n# current train.py\n```python\n"
              f"{read(TRAIN)}```\n\n# results so far (iter, status, val_auc, delta, hypothesis)\n{history}\n\n"
              "Propose the next experiment.")
    reply = chat([{"role": "system", "content": RESEARCHER}, {"role": "user", "content": prompt}])
    text = re.sub(r"^```(json)?|```$", "", (reply.get("content") or "").strip(), flags=re.M).strip()
    return json.loads(text)


def cmd_run(a):
    from llm import chat, model_name                                  # Part A's OpenRouter client
    print(f"[run] researcher = {model_name()}   iterations = {a.iterations}   budget = {a.budget}s")
    print(f"[run] start: best val_auc = {load_best()['val_auc']}\n")
    for _ in range(a.iterations):
        try:
            idea = ask_researcher(chat)
        except Exception as e:                                        # unparsable reply = wasted turn
            print(f"[researcher] invalid proposal: {e}")
            continue
        print(f"[researcher] {idea['hypothesis']}")
        print(show(experiment(idea["hypothesis"], idea["edits"], a.budget)))
        time.sleep(0.2)
    print()
    cmd_status(a)


def cmd_finalize(_):
    b = load_best()
    if gate_frozen():
        sys.exit("refusing to finalize: " + gate_frozen())
    res = evaluate(b["path"], 300, final=True)
    base = evaluate(BASELINE, 300, final=True)
    r = rows()
    counts = {s: sum(x["status"] == s for x in r[1:]) for s in ("keep", "discard", "crash", "rejected", "bad-edit")}
    md = ["# Autoresearch report", "",
          f"- experiments run: **{len(r) - 1}**  ({', '.join(f'{k}: {v}' for k, v in counts.items() if v)})",
          f"- baseline: val AUC **{base['val_auc']}**, test AUC **{base['test_auc']}**",
          f"- best (exp {b['iter']}): val AUC **{res['val_auc']}**, test AUC **{res['test_auc']}**",
          f"- best idea: {b['hypothesis']}", f"- features ({len(b['features'])}): `{', '.join(b['features'])}`", "",
          "| exp | status | val AUC | delta | hypothesis |", "|---:|---|---:|---:|---|"]
    md += [f"| {x['iter']} | {x['status']} | {x['val_auc']} | {x['delta']} | {x['hypothesis']} |" for x in r]
    md += ["", "The test split was scored once, here, after the search ended (rule 5)."]
    open(os.path.join(STATE, "report.md"), "w").write("\n".join(md) + "\n")
    print(f"[finalize] baseline test AUC = {base['test_auc']}")
    print(f"[finalize] best     test AUC = {res['test_auc']}   (val {res['val_auc']}, exp {b['iter']})")
    print(f"[finalize] report -> runs/report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("finalize").set_defaults(fn=cmd_finalize)
    s = sub.add_parser("step"); s.set_defaults(fn=cmd_step)
    s.add_argument("--hypothesis", required=True); s.add_argument("--edits", required=True)
    s.add_argument("--budget", type=int, default=60)
    r = sub.add_parser("run"); r.set_defaults(fn=cmd_run)
    r.add_argument("--iterations", type=int, default=6); r.add_argument("--budget", type=int, default=60)
    args = ap.parse_args()
    args.fn(args)
