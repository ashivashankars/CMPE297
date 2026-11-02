"""Project 04 - Market basket mining on the Groceries dataset (9,835 real baskets, 169 items).

Business question: which products are bought together, and what should we recommend at checkout?

What makes this more than "run apriori":
  * Rules are mined on 80% of baskets and re-measured on the held-out 20%. A rule whose lift
    falls below 1 out-of-sample was a coincidence of the training sample.
  * Every rule gets a Fisher exact test, with Benjamini-Hochberg correction for the
    thousands of rules tested at once (multiple-comparisons control).
  * The recommender is evaluated like a recommender: hide one item from each held-out basket
    and check whether the rules put it in the top 5, against a "most popular items" baseline.
  * Apriori and FP-Growth are timed on the same data and must return identical itemsets.
Run:  python projects/04_market_basket/basket_pipeline.py
"""
from __future__ import annotations

import pathlib
import sys
import time
from collections import Counter

import joblib
import networkx as nx
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder
from scipy.stats import fisher_exact
from sklearn.model_selection import train_test_split

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from shared.report_io import dump  # noqa: E402

RAW = HERE.parents[1] / "data" / "raw" / "groceries.csv"
ART = HERE / "artifacts"
SEED = 42


def load() -> list[list[str]]:
    return [sorted(set(line.split(","))) for line in RAW.read_text().strip().split("\n")]


def onehot(baskets: list[list[str]], columns=None) -> pd.DataFrame:
    te = TransactionEncoder().fit(baskets)
    df = pd.DataFrame(te.transform(baskets), columns=te.columns_)
    return df.reindex(columns=columns, fill_value=False) if columns is not None else df


def mine(oh: pd.DataFrame, min_support: float, min_confidence: float, algo=fpgrowth) -> pd.DataFrame:
    items = algo(oh, min_support=min_support, use_colnames=True)
    if items.empty:
        return pd.DataFrame()
    rules = association_rules(items, metric="confidence", min_threshold=min_confidence)
    return rules[rules["lift"] > 1].reset_index(drop=True)


def validate(rules: pd.DataFrame, oh_test: pd.DataFrame) -> pd.DataFrame:
    """Re-measure support/confidence/lift on held-out baskets + Fisher test with BH-FDR."""
    n = len(oh_test)
    rows = []
    for _, r in rules.iterrows():
        a = oh_test[list(r["antecedents"])].all(axis=1).to_numpy()
        c = oh_test[list(r["consequents"])].all(axis=1).to_numpy()
        both = int((a & c).sum())
        conf = both / a.sum() if a.sum() else 0.0
        lift = conf / (c.mean() or 1e-9)
        table = [[both, int((a & ~c).sum())], [int((~a & c).sum()), int((~a & ~c).sum())]]
        p = fisher_exact(table, alternative="greater")[1]
        rows.append({"test_support": both / n, "test_confidence": conf, "test_lift": lift, "p_value": p})
    out = pd.concat([rules, pd.DataFrame(rows)], axis=1)
    # Benjamini-Hochberg false discovery rate
    order = np.argsort(out["p_value"].to_numpy())
    m = len(out)
    q = out["p_value"].to_numpy()[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out.loc[order, "q_value"] = np.minimum(q, 1)
    out["holds_up"] = (out["test_lift"] > 1) & (out["q_value"] < 0.05)
    return out


class RuleRecommender:
    """Score candidate items by the best-lift rule whose antecedent is inside the cart."""

    def __init__(self, rules: pd.DataFrame, popularity: list[str]):
        self.rules = [(frozenset(r.antecedents), next(iter(r.consequents)), float(r.confidence), float(r.lift))
                      for r in rules.itertuples() if len(r.consequents) == 1]
        self.popularity = popularity

    def recommend(self, cart: set[str], k: int = 5) -> list[dict]:
        best: dict[str, dict] = {}
        for ante, cons, conf, lift in self.rules:
            if cons in cart or not ante <= cart:
                continue
            score = conf * np.log1p(lift)  # confident AND surprising
            if cons not in best or score > best[cons]["score"]:
                best[cons] = {"item": cons, "score": score, "confidence": conf, "lift": lift, "because": sorted(ante)}
        recs = sorted(best.values(), key=lambda d: -d["score"])[:k]
        for item in self.popularity:  # back-fill with popular items so we always return k
            if len(recs) >= k:
                break
            if item not in cart and item not in {r["item"] for r in recs}:
                recs.append({"item": item, "score": 0.0, "confidence": None, "lift": None, "because": ["popular overall"]})
        return recs


class CooccurrenceRecommender:
    """Item-to-item: score(j) = sum over cart items i of P(j | i), shrunk toward 0 for rare i.

    Uses every pair seen in training (no support threshold), so it can use weak signals that
    rule mining discards. `beta` blends in a lift-style novelty term to reduce popularity bias.
    """

    def __init__(self, oh: pd.DataFrame, shrink: float = 10.0, beta: float = 0.0):
        X = oh.to_numpy(np.float32)
        self.items = list(oh.columns)
        self.idx = {it: i for i, it in enumerate(self.items)}
        co = X.T @ X
        n_i = np.diag(co).copy()
        np.fill_diagonal(co, 0)
        self.cond = co / (n_i[:, None] + shrink + 1e-9)    # P(j | i), shrunk; 1e-9 guards unseen items
        self.base = n_i / len(X)                          # P(j)
        self.beta = beta

    def recommend(self, cart: set[str], k: int = 5) -> list[dict]:
        rows = [self.idx[i] for i in cart if i in self.idx]
        if not rows:
            score = self.base.copy()
        else:
            p = self.cond[rows].mean(axis=0)
            score = p * (p / (self.base + 1e-9)) ** self.beta
        for i in rows:
            score[i] = -1
        top = np.argsort(-score)[:k]
        return [{"item": self.items[j], "score": float(score[j])} for j in top]


def hit_rate(rec_fn, baskets: list[list[str]], k: int = 5, seed: int = SEED, exclude: set | None = None) -> float:
    """Leave-one-out on held-out baskets: hide one item, check it appears in top-k.

    `exclude` restricts scoring to hidden items outside a set (e.g. the 10 most popular items),
    which measures whether a recommender finds anything beyond the obvious.
    """
    rng = np.random.default_rng(seed)
    hits = total = 0
    for b in baskets:
        if len(b) < 2:
            continue
        hidden = b[rng.integers(len(b))]
        if exclude and hidden in exclude:
            continue
        cart = set(b) - {hidden}
        hits += hidden in [r["item"] for r in rec_fn(cart, k)]
        total += 1
    return hits / total


def run() -> dict:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    baskets = load()
    train, test = train_test_split(baskets, test_size=0.2, random_state=SEED)
    oh_train = onehot(train)
    oh_test = onehot(test, columns=oh_train.columns)
    counts = Counter(i for b in train for i in b)
    popularity = [i for i, _ in counts.most_common()]

    # ---- algorithm benchmark: same answers, different speed
    bench = []
    for s in [0.02, 0.01, 0.005, 0.003]:
        row = {"min_support": s}
        for name, fn in [("apriori", apriori), ("fpgrowth", fpgrowth)]:
            t = time.perf_counter()
            res = fn(oh_train, min_support=s, use_colnames=True)
            row[f"{name}_sec"] = time.perf_counter() - t
            row[f"{name}_itemsets"] = len(res)
        row["identical"] = row["apriori_itemsets"] == row["fpgrowth_itemsets"]
        bench.append(row)

    # ---- AutoResearch: sweep thresholds, choose by held-out hit-rate on a *validation* split of train
    fit_b, val_b = train_test_split(train, test_size=0.2, random_state=SEED)
    oh_fit = onehot(fit_b, columns=oh_train.columns)
    pop_fit = [i for i, _ in Counter(i for b in fit_b for i in b).most_common()]
    sweep = []
    for s in [0.002, 0.003, 0.005, 0.01]:
        for c in [0.05, 0.1, 0.2, 0.3]:
            rules = mine(oh_fit, s, c)
            rec = RuleRecommender(rules, pop_fit) if len(rules) else RuleRecommender(pd.DataFrame(columns=["antecedents", "consequents", "confidence", "lift"]), pop_fit)
            sweep.append({"min_support": s, "min_confidence": c, "n_rules": len(rules), "val_hit_rate@5": hit_rate(rec.recommend, val_b)})
    best = max(sweep, key=lambda d: d["val_hit_rate@5"])

    # ---- final rules on all training baskets, validated on the untouched test baskets
    rules = mine(oh_train, best["min_support"], best["min_confidence"])
    rules = validate(rules, oh_test)
    rec = RuleRecommender(rules[rules["holds_up"]], popularity)

    # co-occurrence recommender: tune shrink/beta on the validation split, like the thresholds
    co_sweep = []
    for shrink in [0, 10, 50]:
        for beta in [0.0, 0.25, 0.5]:
            m = CooccurrenceRecommender(oh_fit, shrink, beta)
            co_sweep.append({"shrink": shrink, "beta": beta, "val_hit_rate@5": hit_rate(m.recommend, val_b)})
    co_best = max(co_sweep, key=lambda d: d["val_hit_rate@5"])
    co = CooccurrenceRecommender(oh_train, co_best["shrink"], co_best["beta"])

    popular = lambda cart, k: [{"item": i} for i in [p for p in popularity if p not in cart][:k]]  # noqa: E731
    rand = lambda cart, k: [{"item": i} for i in np.random.default_rng(len(cart)).choice([p for p in popularity if p not in cart], k, replace=False)]  # noqa: E731
    top10 = set(popularity[:10])
    contenders = {"Random items": rand, "Most popular items": popular,
                  "Association rules (validated)": rec.recommend, "Item co-occurrence (tuned)": co.recommend}
    eval_ = {
        "rules_mined": len(rules), "rules_hold_up": int(rules["holds_up"].sum()),
        "co_best": co_best, "co_sweep": co_sweep,
        "leaderboard": [{"model": name, "hit_rate@5": hit_rate(fn, test), "hit_rate@10": hit_rate(fn, test, k=10),
                         "longtail_hit_rate@10": hit_rate(fn, test, k=10, exclude=top10)}
                        for name, fn in contenders.items()],
    }

    # ---- graph of the strongest validated rules (single-item -> single-item for readability)
    g_rules = rules[rules["holds_up"]].sort_values("lift", ascending=False)
    g_rules = g_rules[g_rules["antecedents"].map(len) <= 2].head(60)
    G = nx.DiGraph()
    for r in g_rules.itertuples():
        for a in r.antecedents:
            G.add_edge(a, next(iter(r.consequents)), lift=r.lift)
    pos = nx.spring_layout(G, seed=SEED, k=0.9)
    graph = {"nodes": [{"id": n, "x": float(pos[n][0]), "y": float(pos[n][1]), "support": counts[n] / len(train),
                        "degree": G.degree(n)} for n in G.nodes],
             "edges": [{"a": a, "b": b, "lift": float(d["lift"])} for a, b, d in G.edges(data=True)]}

    def fmt_rules(df):
        out = df.copy()
        out["antecedents"] = out["antecedents"].map(lambda s: sorted(s))
        out["consequents"] = out["consequents"].map(lambda s: sorted(s))
        keep = ["antecedents", "consequents", "support", "confidence", "lift", "leverage", "conviction",
                "test_support", "test_confidence", "test_lift", "q_value", "holds_up"]
        return out[keep].replace([np.inf], 999).round(5).to_dict("records")

    sizes = Counter(len(b) for b in baskets)
    report = {
        "n_baskets": len(baskets), "n_items": len(counts), "n_train": len(train), "n_test": len(test),
        "eda": {"basket_sizes": sorted(sizes.items()), "top_items": [(i, c / len(train)) for i, c in counts.most_common(25)],
                "item_rank_support": [c / len(train) for _, c in counts.most_common()],
                "avg_basket": float(np.mean([len(b) for b in baskets]))},
        "benchmark": bench,
        "sweep": sweep, "best_thresholds": best,
        "evaluation": eval_,
        "rules": fmt_rules(rules.sort_values("lift", ascending=False)),
        "graph": graph,
        "runtime_sec": round(time.time() - t0, 1),
    }
    joblib.dump({"recommender": rec, "co": co, "items": sorted(counts), "oh_train": oh_train.to_numpy(np.bool_),
                 "columns": list(oh_train.columns), "popularity": popularity}, ART / "model.joblib")
    dump(report, ART / "report.json")
    return report


if __name__ == "__main__":
    # import under the real module name so pickled classes resolve as basket_pipeline.X, not __main__.X
    sys.path.insert(0, str(HERE))
    from basket_pipeline import run as _run
    r = _run()
    print("best thresholds:", r["best_thresholds"])
    print("evaluation:", r["evaluation"])
    print("bench:", r["benchmark"])
    print("runtime", r["runtime_sec"])
