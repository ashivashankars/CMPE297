"""Project 02 - NanoGPT from scratch: tokenizer, model, training loop, sampling. CPU-friendly.

Everything here is written from first principles in ~300 lines so every part can be read:
  * Byte-level BPE tokenizer trained on the corpus (GPT-2-style regex pre-split, 512 tokens).
  * Decoder-only transformer with modern primitives:
      RMSNorm (pre-norm), Rotary position embeddings (RoPE), SwiGLU MLP, tied input/output
      embeddings, no biases, causal attention via scaled_dot_product_attention.
  * A switch to the 2019 GPT-2 recipe (LayerNorm, GELU MLP, learned absolute positions) so the
    ablation compares like for like at the same parameter budget.
  * AdamW + warmup/cosine schedule, gradient clipping, held-out validation loss, checkpoints.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

SPLIT = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?[0-9]+| ?[^\sA-Za-z0-9]+|\s+(?!\S)|\s+""")


# =============================================================== tokenizer
class BPETokenizer:
    """Byte-level BPE. Merges are learned within pre-split words (so they never cross spaces)."""

    def __init__(self, merges: list[tuple[int, int]] | None = None):
        self.merges = [tuple(m) for m in (merges or [])]
        self.ranks = {m: i for i, m in enumerate(self.merges)}
        self.vocab = {i: bytes([i]) for i in range(256)}
        for i, (a, b) in enumerate(self.merges):
            self.vocab[256 + i] = self.vocab[a] + self.vocab[b]
        self.cache: dict[str, list[int]] = {}

    @property
    def size(self) -> int:
        return 256 + len(self.merges)

    @classmethod
    def train(cls, text: str, vocab_size: int) -> "BPETokenizer":
        words = Counter(SPLIT.findall(text))
        seqs = {w: list(w.encode()) for w in words}
        merges = []
        for new_id in range(256, vocab_size):
            pairs = Counter()
            for w, n in words.items():
                s = seqs[w]
                for p in zip(s, s[1:]):
                    pairs[p] += n
            if not pairs:
                break
            best = max(pairs, key=pairs.get)
            merges.append(best)
            for w in words:
                s = seqs[w]
                if len(s) < 2:
                    continue
                out, i = [], 0
                while i < len(s):
                    if i < len(s) - 1 and (s[i], s[i + 1]) == best:
                        out.append(new_id)
                        i += 2
                    else:
                        out.append(s[i])
                        i += 1
                seqs[w] = out
        return cls(merges)

    def _encode_word(self, w: str) -> list[int]:
        if w in self.cache:
            return self.cache[w]
        s = list(w.encode())
        while len(s) > 1:
            pair = min(zip(s, s[1:]), key=lambda p: self.ranks.get(p, 1e9))
            if pair not in self.ranks:
                break
            new_id, out, i = 256 + self.ranks[pair], [], 0
            while i < len(s):
                if i < len(s) - 1 and (s[i], s[i + 1]) == pair:
                    out.append(new_id)
                    i += 2
                else:
                    out.append(s[i])
                    i += 1
            s = out
        self.cache[w] = s
        return s

    def encode(self, text: str) -> list[int]:
        return [t for w in SPLIT.findall(text) for t in self._encode_word(w)]

    def decode(self, ids: list[int]) -> str:
        return b"".join(self.vocab[i] for i in ids).decode("utf-8", errors="replace")

    def piece(self, i: int) -> str:
        return self.vocab[i].decode("utf-8", errors="replace")


# =============================================================== model
@dataclass
class Config:
    vocab_size: int = 512
    block_size: int = 128
    n_layer: int = 6
    n_head: int = 6
    n_embd: int = 192
    dropout: float = 0.2
    modern: bool = True      # RMSNorm + SwiGLU + RoPE  (False = GPT-2: LayerNorm + GELU + learned pos)
    rope: bool = True        # only used when modern=True (ablation: NoPE = no position signal at all)


class RMSNorm(nn.Module):
    def __init__(self, d: int, eps: float = 1e-6):
        super().__init__()
        self.eps, self.weight = eps, nn.Parameter(torch.ones(d))

    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight


def rope_cache(T: int, hd: int, base: float = 10000.0):
    inv = 1.0 / base ** (torch.arange(0, hd, 2).float() / hd)
    ang = torch.outer(torch.arange(T).float(), inv)  # (T, hd/2)
    return ang.cos(), ang.sin()


def apply_rope(x, cos, sin):
    """Rotate each (even, odd) channel pair by a position-dependent angle."""
    x1, x2 = x[..., 0::2], x[..., 1::2]
    return torch.stack((x1 * cos - x2 * sin, x1 * sin + x2 * cos), dim=-1).flatten(-2)


class Attention(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.c, self.hd = c, c.n_embd // c.n_head
        self.qkv = nn.Linear(c.n_embd, 3 * c.n_embd, bias=False)
        self.proj = nn.Linear(c.n_embd, c.n_embd, bias=False)
        self.drop = nn.Dropout(c.dropout)

    def forward(self, x, rope=None, return_attn=False):
        B, T, C = x.shape
        q, k, v = self.qkv(x).view(B, T, 3, self.c.n_head, self.hd).permute(2, 0, 3, 1, 4)
        if rope is not None:
            cos, sin = rope
            q, k = apply_rope(q, cos[:T], sin[:T]), apply_rope(k, cos[:T], sin[:T])
        if return_attn:  # explicit path, used only by the attention viewer
            att = (q @ k.transpose(-2, -1)) / math.sqrt(self.hd)
            att = att.masked_fill(torch.triu(torch.ones(T, T, dtype=torch.bool), 1), float("-inf")).softmax(-1)
            y = att @ v
        else:
            att = None
            y = F.scaled_dot_product_attention(q, k, v, is_causal=True, dropout_p=self.c.dropout if self.training else 0.0)
        return self.drop(self.proj(y.transpose(1, 2).reshape(B, T, C))), att


class MLP(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.modern = c.modern
        if c.modern:  # SwiGLU, hidden sized so params match the 4x GELU MLP
            h = int(8 * c.n_embd / 3 / 8) * 8
            self.w1, self.w3 = nn.Linear(c.n_embd, h, bias=False), nn.Linear(c.n_embd, h, bias=False)
            self.w2 = nn.Linear(h, c.n_embd, bias=False)
        else:
            self.w1, self.w2 = nn.Linear(c.n_embd, 4 * c.n_embd, bias=False), nn.Linear(4 * c.n_embd, c.n_embd, bias=False)
        self.drop = nn.Dropout(c.dropout)

    def forward(self, x):
        h = F.silu(self.w1(x)) * self.w3(x) if self.modern else F.gelu(self.w1(x))
        return self.drop(self.w2(h))


class Block(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        Norm = RMSNorm if c.modern else nn.LayerNorm
        self.n1, self.n2 = Norm(c.n_embd), Norm(c.n_embd)
        self.attn, self.mlp = Attention(c), MLP(c)

    def forward(self, x, rope=None, return_attn=False):
        a, att = self.attn(self.n1(x), rope, return_attn)
        x = x + a                       # pre-norm residual stream
        x = x + self.mlp(self.n2(x))
        return x, att


class GPT(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.c = c
        self.tok = nn.Embedding(c.vocab_size, c.n_embd)
        self.pos = None if c.modern else nn.Embedding(c.block_size, c.n_embd)
        self.drop = nn.Dropout(c.dropout)
        self.blocks = nn.ModuleList(Block(c) for _ in range(c.n_layer))
        self.norm = RMSNorm(c.n_embd) if c.modern else nn.LayerNorm(c.n_embd)
        self.head = nn.Linear(c.n_embd, c.vocab_size, bias=False)
        self.head.weight = self.tok.weight  # weight tying
        if c.modern and c.rope:
            cos, sin = rope_cache(c.block_size, c.n_embd // c.n_head)
            self.register_buffer("cos", cos, persistent=False)
            self.register_buffer("sin", sin, persistent=False)
        self.apply(self._init)
        for n, p in self.named_parameters():  # scaled init for residual projections (GPT-2)
            if n.endswith(("proj.weight", "w2.weight")):
                nn.init.normal_(p, 0.0, 0.02 / math.sqrt(2 * c.n_layer))

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, 0.0, 0.02)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx, targets=None, return_attn=False):
        B, T = idx.shape
        x = self.tok(idx)
        if self.pos is not None:
            x = x + self.pos(torch.arange(T))
        x = self.drop(x)
        rope = (self.cos, self.sin) if self.c.modern and self.c.rope else None
        atts = []
        for b in self.blocks:
            x, att = b(x, rope, return_attn)
            atts.append(att)
        logits = self.head(self.norm(x))
        loss = None if targets is None else F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss, atts

    @torch.no_grad()
    def generate(self, idx, max_new: int, temperature=0.8, top_k=40, top_p=0.95):
        """Yields (token_id, probability, top5 alternatives) one step at a time."""
        self.eval()
        for _ in range(max_new):
            logits = self(idx[:, -self.c.block_size:])[0][:, -1, :]
            probs_full = F.softmax(logits, -1)
            logits = logits / max(temperature, 1e-4)
            if top_k:
                kth = torch.topk(logits, min(top_k, logits.size(-1))).values[:, -1, None]
                logits = logits.masked_fill(logits < kth, float("-inf"))
            probs = F.softmax(logits, -1)
            if top_p < 1.0:  # nucleus: keep the smallest set whose mass >= top_p
                sp, si = torch.sort(probs, descending=True)
                drop = sp.cumsum(-1) - sp > top_p
                sp[drop] = 0
                probs = torch.zeros_like(probs).scatter(-1, si, sp)
                probs = probs / probs.sum(-1, keepdim=True)
            nxt = torch.multinomial(probs, 1)
            top5 = torch.topk(probs_full, 5)
            yield int(nxt), float(probs_full[0, nxt]), list(zip(top5.indices[0].tolist(), top5.values[0].tolist()))
            idx = torch.cat([idx, nxt], 1)


# =============================================================== training
def lr_at(step: int, max_steps: int, peak: float, warmup: int) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = (step - warmup) / max(1, max_steps - warmup)
    return peak * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))  # cosine to 10% of peak


def batches(data: torch.Tensor, block: int, bs: int, gen: torch.Generator):
    ix = torch.randint(len(data) - block - 1, (bs,), generator=gen)
    x = torch.stack([data[i:i + block] for i in ix])
    y = torch.stack([data[i + 1:i + 1 + block] for i in ix])
    return x, y


@torch.no_grad()
def evaluate(model, data, block, bs=32, iters=20, seed=0) -> float:
    model.eval()
    g = torch.Generator().manual_seed(seed)  # same val batches every time -> comparable curves
    losses = [model(*batches(data, block, bs, g))[1].item() for _ in range(iters)]
    model.train()
    return sum(losses) / len(losses)


def train(cfg: Config, train_ids, val_ids, steps: int, bs: int = 32, lr: float = 3e-3, warmup: int = 100,
          eval_every: int = 50, log=None, seed: int = 1337, ckpt_path=None, extra: dict | None = None):
    torch.manual_seed(seed)
    model = GPT(cfg)
    decay = [p for n, p in model.named_parameters() if p.dim() >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.dim() < 2]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": 0.1}, {"params": no_decay, "weight_decay": 0.0}],
                            lr=lr, betas=(0.9, 0.95))
    gen = torch.Generator().manual_seed(seed)
    history, t0, best = [], time.time(), (float("inf"), None, 0)
    for step in range(steps + 1):
        if step % eval_every == 0 or step == steps:
            rec = {"step": step, "train_loss": evaluate(model, train_ids, cfg.block_size),
                   "val_loss": evaluate(model, val_ids, cfg.block_size), "lr": lr_at(step, steps, lr, warmup),
                   "elapsed_sec": round(time.time() - t0, 1)}
            history.append(rec)
            if log:
                log(rec)
            # early-stopping checkpoint: keep the weights with the best validation loss
            if rec["val_loss"] < best[0]:
                best = (rec["val_loss"], {k: v.detach().clone() for k, v in model.state_dict().items()}, step)
                if ckpt_path and step > 0:
                    torch.save({"config": asdict(cfg), "state": best[1], "history": history, "best_step": step,
                                **(extra or {})}, ckpt_path)
        if step == steps:
            break
        for g in opt.param_groups:
            g["lr"] = lr_at(step, steps, lr, warmup)
        x, y = batches(train_ids, cfg.block_size, bs, gen)
        _, loss, _ = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
    model.load_state_dict(best[1])  # return the best-validation weights, not the last ones
    model.best_step = best[2]
    return model, history


def ngram_baselines(train_ids: list[int], val_ids: list[int], vocab: int) -> dict:
    """Cross-entropy (nats/token) of add-one unigram and bigram models: the floor to beat."""
    uni = Counter(train_ids)
    tot = len(train_ids)
    uni_ce = -sum(math.log((uni[t] + 1) / (tot + vocab)) for t in val_ids) / len(val_ids)
    bi = Counter(zip(train_ids, train_ids[1:]))
    bi_ce = -sum(math.log((bi[(a, b)] + 1) / (uni[a] + vocab)) for a, b in zip(val_ids, val_ids[1:])) / (len(val_ids) - 1)
    return {"unigram": uni_ce, "bigram": bi_ce}


def save_json(obj, path):
    path.write_text(json.dumps(obj, indent=1))
