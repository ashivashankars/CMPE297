"""Train NanoGPT on Tiny Shakespeare and run the architecture ablation.

  python projects/02_nano_llm/train.py --steps 2000 --ablation-steps 400

Data split: first 90% of the text = train, last 10% = validation (contiguous, so no
overlapping windows leak between the two). The BPE tokenizer is trained on the train
split only. Progress is streamed to artifacts/progress.json so the dashboard can show
a run while it is still training.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import time
from dataclasses import asdict

import torch

from nanogpt import BPETokenizer, Config, GPT, ngram_baselines, save_json, train

HERE = pathlib.Path(__file__).parent
RAW = HERE.parents[1] / "data" / "raw" / "tinyshakespeare.txt"
ART = HERE / "artifacts"
PROMPTS = ["ROMEO:\n", "First Citizen:\nWe are", "KING RICHARD III:\nNow is the"]


def main(steps: int, ablation_steps: int, vocab: int) -> None:
    torch.set_num_threads(2)
    ART.mkdir(exist_ok=True)
    text = RAW.read_text()
    cut = int(len(text) * 0.9)
    train_text, val_text = text[:cut], text[cut:]

    t = time.time()
    tok = BPETokenizer.train(train_text, vocab)
    tok_sec = time.time() - t
    train_ids, val_ids = tok.encode(train_text), tok.encode(val_text)
    tr, va = torch.tensor(train_ids), torch.tensor(val_ids)
    base = ngram_baselines(train_ids, val_ids, tok.size)
    longest = sorted(range(256, tok.size), key=lambda i: -len(tok.vocab[i]))[:30]
    report = {
        "corpus": {"chars": len(text), "train_chars": len(train_text), "val_chars": len(val_text),
                   "train_tokens": len(train_ids), "val_tokens": len(val_ids),
                   "chars_per_token": len(train_text) / len(train_ids), "tokenizer_train_sec": tok_sec},
        "tokenizer": {"vocab_size": tok.size, "merges": tok.merges, "first_merges": [tok.piece(256 + i) for i in range(40)],
                      "longest_tokens": [tok.piece(i) for i in longest]},
        "baselines": base, "status": "training", "samples": [],
    }
    save_json(report, ART / "report.json")
    save_json({"merges": tok.merges}, ART / "tokenizer.json")

    cfg = Config(vocab_size=tok.size)
    progress = {"main": [], "ablation": {}}

    def sample(model, prompt, n=80, seed=0):
        torch.manual_seed(seed)
        ids = torch.tensor([tok.encode(prompt)])
        return prompt + tok.decode([t for t, _, _ in model.generate(ids, n, temperature=0.8)])

    def log_main(rec):
        progress["main"].append(rec)
        save_json(progress, ART / "progress.json")
        print(f"step {rec['step']:5d}  train {rec['train_loss']:.3f}  val {rec['val_loss']:.3f}  {rec['elapsed_sec']:.0f}s", flush=True)

    # ---- main run
    model, hist = train(cfg, tr, va, steps, log=log_main, ckpt_path=ART / "model.pt",
                        extra={"merges": tok.merges})
    report["samples"] = [{"prompt": p, "text": sample(model, p, seed=i)} for i, p in enumerate(PROMPTS)]
    best_val = min(h["val_loss"] for h in hist)
    report["main"] = {"config": asdict(cfg), "params": model.n_params(), "history": hist, "best_step": model.best_step,
                      "final_val_loss": best_val, "val_perplexity": math.exp(best_val),
                      "last_val_loss": hist[-1]["val_loss"]}
    save_json(report, ART / "report.json")

    # ---- learning snapshot: the same prompt from random weights vs the trained model
    untrained = GPT(cfg)
    report["learning_snapshots"] = [
        {"label": "Step 0 (random weights)", "text": sample(untrained, PROMPTS[0], 60)},
        {"label": f"Best checkpoint, step {model.best_step}", "text": sample(model, PROMPTS[0], 60)},
    ]

    # ---- ablation at equal steps and roughly equal parameters
    variants = {
        "Modern: RMSNorm + SwiGLU + RoPE": Config(vocab_size=tok.size, modern=True, rope=True),
        "Modern without RoPE (no position info)": Config(vocab_size=tok.size, modern=True, rope=False),
        "GPT-2 style: LayerNorm + GELU + learned pos": Config(vocab_size=tok.size, modern=False),
    }
    report["ablation"] = []
    for name, c in variants.items():
        def log_ab(rec, name=name):
            progress["ablation"].setdefault(name, []).append(rec)
            save_json(progress, ART / "progress.json")
            print(f"[{name[:24]}] step {rec['step']} val {rec['val_loss']:.3f}", flush=True)
        m, h = train(c, tr, va, ablation_steps, log=log_ab, eval_every=50)
        report["ablation"].append({"variant": name, "params": m.n_params(), "history": h, "final_val_loss": min(x["val_loss"] for x in h),
                                   "sec_per_step": h[-1]["elapsed_sec"] / ablation_steps})
        save_json(report, ART / "report.json")
    report["status"] = "done"
    save_json(report, ART / "report.json")
    print("done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--ablation-steps", type=int, default=400)
    ap.add_argument("--vocab", type=int, default=512)
    a = ap.parse_args()
    main(a.steps, a.ablation_steps, a.vocab)
