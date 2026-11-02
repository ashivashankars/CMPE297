"""Project 02 API: training dashboard data, tokenizer, sampling with token probabilities, attention maps."""
from __future__ import annotations

import json
import pathlib

import torch
import torch.nn.functional as F
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nanogpt import GPT, BPETokenizer, Config

HERE = pathlib.Path(__file__).parent
ART = HERE / "artifacts"
META = {
    "title": "NanoGPT from Scratch",
    "tag": "Deep learning · LLM · CRISP-DM",
    "blurb": "A 2.7M-parameter GPT with RoPE, RMSNorm and SwiGLU, trained on a laptop CPU. Includes a home-made BPE tokenizer, an architecture ablation, and tools to watch it think.",
    "accent": "#8a6aa8", "accent_soft": "#eee8f4",
}
router = APIRouter()
_state: dict = {"mtime": None}


def state() -> dict:
    ckpt = ART / "model.pt"
    if not ckpt.exists():
        raise HTTPException(503, "model is still training: no checkpoint yet")
    mtime = ckpt.stat().st_mtime
    if _state["mtime"] != mtime:  # hot-reload newer checkpoints written during training
        blob = torch.load(ckpt, map_location="cpu", weights_only=False)
        model = GPT(Config(**blob["config"]))
        model.load_state_dict(blob["state"])
        model.eval()
        _state.update(model=model, tok=BPETokenizer(blob["merges"]), step=blob["history"][-1]["step"], mtime=mtime)
    return _state


def _json(name: str):
    p = ART / name
    return json.loads(p.read_text()) if p.exists() else None


class Prompt(BaseModel):
    prompt: str = Field("ROMEO:\n", max_length=600)


class GenRequest(Prompt):
    max_new: int = Field(80, ge=1, le=300)
    temperature: float = Field(0.8, ge=0.05, le=2.0)
    top_k: int = Field(40, ge=0, le=512)
    top_p: float = Field(0.95, ge=0.1, le=1.0)
    seed: int = 0


@router.get("/report")
def report():
    rep = _json("report.json") or {"status": "not started"}
    rep["progress"] = _json("progress.json")
    try:
        rep["serving_step"] = state()["step"]
    except HTTPException:
        rep["serving_step"] = None
    return rep


@router.post("/tokenize")
def tokenize(p: Prompt):
    tok = state()["tok"]
    ids = tok.encode(p.prompt)
    return {"tokens": [{"id": i, "piece": tok.piece(i)} for i in ids], "chars": len(p.prompt), "n_tokens": len(ids)}


@router.post("/generate")
def generate(g: GenRequest):
    s = state()
    tok, model = s["tok"], s["model"]
    ids = tok.encode(g.prompt) or [tok.encode("\n")[0]]
    torch.manual_seed(g.seed)
    out = []
    for t, p, top in model.generate(torch.tensor([ids]), g.max_new, g.temperature, g.top_k, g.top_p):
        out.append({"id": t, "piece": tok.piece(t), "p": p, "alts": [{"piece": tok.piece(i), "p": q} for i, q in top]})
    return {"prompt": g.prompt, "tokens": out, "text": tok.decode([o["id"] for o in out]), "step": s["step"]}


@router.post("/next")
def next_token(p: Prompt):
    s = state()
    ids = s["tok"].encode(p.prompt)
    if not ids:
        raise HTTPException(422, "empty prompt")
    with torch.no_grad():
        logits = s["model"](torch.tensor([ids[-s["model"].c.block_size:]]))[0][0, -1]
    probs = F.softmax(logits, -1)
    top = torch.topk(probs, 15)
    entropy = float(-(probs * probs.clamp_min(1e-12).log()).sum())
    return {"candidates": [{"piece": s["tok"].piece(i), "p": float(q)} for i, q in zip(top.indices.tolist(), top.values.tolist())],
            "entropy_nats": entropy, "perplexity_of_choice": float(torch.exp(torch.tensor(entropy)))}


@router.post("/attention")
def attention(p: Prompt):
    s = state()
    ids = s["tok"].encode(p.prompt)[-48:]
    if len(ids) < 2:
        raise HTTPException(422, "need at least 2 tokens")
    with torch.no_grad():
        _, _, atts = s["model"](torch.tensor([ids]), return_attn=True)
    return {"pieces": [s["tok"].piece(i) for i in ids],
            "layers": [[a[0, h].round(decimals=4).tolist() for h in range(a.shape[1])] for a in atts]}
