import json
import pathlib
import sys

import pytest
import torch

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from nanogpt import GPT, BPETokenizer, Config, apply_rope, rope_cache  # noqa: E402


def test_tokenizer_roundtrip():
    tok = BPETokenizer.train("the cat sat on the mat. the cat! " * 50, 300)
    for s in ["the cat sat", "ROMEO:\nO, unseen wörds\t", ""]:
        assert tok.decode(tok.encode(s)) == s


def test_causal_mask_blocks_the_future():
    """Changing a later token must not change logits at earlier positions."""
    torch.manual_seed(0)
    m = GPT(Config(vocab_size=64, block_size=16, n_layer=2, n_head=2, n_embd=32, dropout=0.0)).eval()
    x = torch.randint(0, 64, (1, 12))
    y = x.clone()
    y[0, 8:] = (y[0, 8:] + 7) % 64
    with torch.no_grad():
        a, b = m(x)[0], m(y)[0]
    torch.testing.assert_close(a[:, :8], b[:, :8])


def test_rope_preserves_norm_and_is_relative():
    cos, sin = rope_cache(32, 8)
    q = torch.randn(1, 1, 32, 8)
    torch.testing.assert_close(apply_rope(q, cos, sin).norm(dim=-1), q.norm(dim=-1))
    # q·k depends only on the offset: compare (pos 3, pos 1) with (pos 10, pos 8)
    v, w = torch.randn(8), torch.randn(8)
    seq_q, seq_k = v.repeat(1, 1, 32, 1), w.repeat(1, 1, 32, 1)
    rq, rk = apply_rope(seq_q, cos, sin)[0, 0], apply_rope(seq_k, cos, sin)[0, 0]
    torch.testing.assert_close(rq[3] @ rk[1], rq[10] @ rk[8], atol=1e-4, rtol=1e-4)


def test_ablation_variants_have_similar_size():
    a = GPT(Config(modern=True)).n_params()
    b = GPT(Config(modern=False)).n_params()
    assert abs(a - b) / b < 0.03


def test_trained_model_beats_bigram():
    rep = HERE / "artifacts" / "report.json"
    if not rep.exists() or "main" not in json.loads(rep.read_text()):
        pytest.skip("model not trained yet")
    r = json.loads(rep.read_text())
    assert r["main"]["final_val_loss"] < r["baselines"]["bigram"] - 0.3
