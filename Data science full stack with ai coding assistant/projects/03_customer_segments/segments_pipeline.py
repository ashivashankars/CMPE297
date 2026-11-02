"""Project 03 - Customer segmentation (Kaggle "Mall Customer Segmentation Data").

Business question: which distinct shopper groups exist, and what should marketing do with each?

Beyond the usual elbow plot this pipeline asks harder questions:
  * Is the k we pick *stable*? Bootstrap-resample customers 40x and measure label agreement (ARI).
  * Does the result depend on the algorithm or feature set? A tournament over
    {feature sets} x {k-means, GMM, Ward, DBSCAN} x {k} ranks configs by silhouette AND stability.
  * Do the segments generalize? Fit on 80% of customers, assign the held-out 20%, compare silhouettes.
Run:  python projects/03_customer_segments/segments_pipeline.py
"""
from __future__ import annotations

import pathlib
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score,
                             davies_bouldin_score, silhouette_samples, silhouette_score)
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from shared.report_io import dump  # noqa: E402

RAW = HERE.parents[1] / "data" / "raw" / "mall_customers.csv"
ART = HERE / "artifacts"
SEED = 42
FEATURE_SETS = {
    "income + spending": ["income", "score"],
    "age + income + spending": ["age", "income", "score"],
    "age + income + spending + gender": ["age", "income", "score", "is_male"],
}


def load() -> pd.DataFrame:
    df = pd.read_csv(RAW).rename(columns={"CustomerID": "id", "Genre": "gender", "Age": "age",
                                          "Annual Income (k$)": "income", "Spending Score (1-100)": "score"})
    df["is_male"] = (df["gender"] == "Male").astype(int)
    return df


def fit_labels(algo: str, X: np.ndarray, k: int) -> np.ndarray:
    if algo == "k-means":
        return KMeans(k, n_init=20, random_state=SEED).fit_predict(X)
    if algo == "GMM":
        return GaussianMixture(k, covariance_type="full", n_init=5, random_state=SEED).fit(X).predict(X)
    if algo == "Ward":
        return AgglomerativeClustering(k, linkage="ward").fit_predict(X)
    raise ValueError(algo)


def stability(algo: str, X: np.ndarray, k: int, n_boot: int = 40) -> float:
    """Mean ARI between the full-data labels and labels from bootstrap refits (on shared points)."""
    rng = np.random.default_rng(SEED)
    ref = fit_labels(algo, X, k)
    scores = []
    for _ in range(n_boot):
        idx = np.unique(rng.choice(len(X), len(X), replace=True))
        scores.append(adjusted_rand_score(ref[idx], fit_labels(algo, X[idx], k)))
    return float(np.mean(scores))


def persona(row: pd.Series, overall: pd.Series) -> tuple[str, str]:
    """Rule-based naming from centroid position relative to the population (transparent, not an LLM)."""
    inc = "High-income" if row["income"] > overall["income"] * 1.15 else "Low-income" if row["income"] < overall["income"] * 0.85 else "Mid-income"
    spend = "big spenders" if row["score"] > 60 else "cautious savers" if row["score"] < 40 else "steady shoppers"
    age = "young " if row["age"] < 32 else "older " if row["age"] > 45 else ""
    actions = {
        ("High-income", "big spenders"): "VIP tier, early access, premium brands. Protect this group from churn.",
        ("High-income", "cautious savers"): "Biggest upside. Test quality/value messaging and personal styling offers.",
        ("Low-income", "big spenders"): "Loyalty points and buy-now-pay-later. Watch credit risk and over-discounting.",
        ("Low-income", "cautious savers"): "Low priority for spend. Use bundles and seasonal sales only.",
    }
    action = actions.get((inc, spend), "Core mass market: broad campaigns, cross-sell, and newsletter engagement.")
    return f"{inc} {age}{spend}".replace("  ", " "), action


def run() -> dict:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    df = load()

    # ---------------- tournament: feature set x algorithm x k
    tournament = []
    for fs_name, cols in FEATURE_SETS.items():
        X = StandardScaler().fit_transform(df[cols])
        for algo in ["k-means", "GMM", "Ward"]:
            for k in range(2, 11):
                lab = fit_labels(algo, X, k)
                tournament.append({"features": fs_name, "algo": algo, "k": k,
                                   "silhouette": float(silhouette_score(X, lab)),
                                   "stability": stability(algo, X, k, n_boot=15),
                                   "min_cluster": int(np.bincount(lab).min())})
        # DBSCAN: density based, k is an output not an input
        for eps in np.arange(0.25, 0.85, 0.05):
            lab = DBSCAN(eps=float(eps), min_samples=5).fit_predict(X)
            mask = lab >= 0
            k = len(set(lab[mask]))
            if k >= 2:
                tournament.append({"features": fs_name, "algo": f"DBSCAN eps={eps:.2f}", "k": k,
                                   "silhouette": float(silhouette_score(X[mask], lab[mask])), "stability": None,
                                   "noise_frac": float(1 - mask.mean()), "min_cluster": int(np.bincount(lab[mask]).min())})
    t = pd.DataFrame(tournament)
    ranked = t.dropna(subset=["stability"]).query("min_cluster >= 8").copy()
    ranked["rank_score"] = ranked["silhouette"].rank(pct=True) * 0.5 + ranked["stability"].rank(pct=True) * 0.5
    best = ranked.sort_values("rank_score", ascending=False).iloc[0]
    cols = FEATURE_SETS[best["features"]]

    # ---------------- k-selection detail for the champion feature set
    scaler = StandardScaler().fit(df[cols])
    X = scaler.transform(df[cols])
    ksel = []
    for k in range(2, 11):
        km = KMeans(k, n_init=20, random_state=SEED).fit(X)
        gm = GaussianMixture(k, covariance_type="full", n_init=5, random_state=SEED).fit(X)
        ksel.append({"k": k, "inertia": float(km.inertia_), "silhouette": float(silhouette_score(X, km.labels_)),
                     "calinski_harabasz": float(calinski_harabasz_score(X, km.labels_)),
                     "davies_bouldin": float(davies_bouldin_score(X, km.labels_)),
                     "gmm_bic": float(gm.bic(X)), "stability": stability("k-means", X, k)})
    K = int(best["k"])

    # ---------------- generalization: fit on 80%, assign the unseen 20%
    tr, ho = train_test_split(df, test_size=0.2, random_state=SEED)
    sc_tr = StandardScaler().fit(tr[cols])
    km_tr = KMeans(K, n_init=20, random_state=SEED).fit(sc_tr.transform(tr[cols]))
    ho_lab = km_tr.predict(sc_tr.transform(ho[cols]))
    full_lab_on_ho = KMeans(K, n_init=20, random_state=SEED).fit(X).predict(scaler.transform(ho[cols]))
    holdout = {
        "train_silhouette": float(silhouette_score(sc_tr.transform(tr[cols]), km_tr.labels_)),
        "holdout_silhouette": float(silhouette_score(sc_tr.transform(ho[cols]), ho_lab)),
        "holdout_ari_vs_full_fit": float(adjusted_rand_score(full_lab_on_ho, ho_lab)),
        "n_train": len(tr), "n_holdout": len(ho),
    }

    # ---------------- final model on all customers
    km = KMeans(K, n_init=50, random_state=SEED).fit(X)
    gmm = GaussianMixture(K, covariance_type="full", n_init=10, random_state=SEED).fit(X)
    df["cluster"] = km.labels_
    sil = silhouette_samples(X, km.labels_)
    overall = df[["age", "income", "score"]].mean()
    profiles = []
    for c, g in df.groupby("cluster"):
        name, action = persona(g[["age", "income", "score"]].mean(), overall)
        profiles.append({"cluster": int(c), "persona": name, "action": action, "size": len(g),
                         "share": len(g) / len(df), "age": g["age"].mean(), "income": g["income"].mean(),
                         "score": g["score"].mean(), "male_share": g["is_male"].mean(),
                         "silhouette": float(sil[df["cluster"] == c].mean())})
    # order clusters by income then score so colours are stable and readable
    order = sorted(profiles, key=lambda p: (p["income"], p["score"]))
    remap = {p["cluster"]: i for i, p in enumerate(order)}
    for p in profiles:
        p["cluster"] = remap[p["cluster"]]
    profiles.sort(key=lambda p: p["cluster"])
    df["cluster"] = df["cluster"].map(remap)

    # agreement between algorithms at the chosen k
    algo_labels = {a: fit_labels(a, X, K) for a in ["k-means", "GMM", "Ward"]}
    agreement = [{"a": a, "b": b, "ari": float(adjusted_rand_score(algo_labels[a], algo_labels[b]))}
                 for i, a in enumerate(algo_labels) for b in list(algo_labels)[i + 1:]]

    pca = PCA(2, random_state=SEED).fit(StandardScaler().fit_transform(df[["age", "income", "score"]]))
    proj = pca.transform(StandardScaler().fit_transform(df[["age", "income", "score"]]))
    report = {
        "n_customers": len(df),
        "chosen": {"features": best["features"], "algo": best["algo"], "k": K,
                   "silhouette": float(best["silhouette"]), "stability": float(best["stability"])},
        "tournament": t.round(4).to_dict("records"),
        "k_selection": ksel,
        "holdout": holdout,
        "profiles": profiles,
        "algo_agreement": agreement,
        "points": df[["id", "gender", "age", "income", "score", "cluster"]].assign(
            silhouette=sil.round(3), pc1=proj[:, 0].round(3), pc2=proj[:, 1].round(3)).to_dict("records"),
        "pca_var": pca.explained_variance_ratio_.tolist(),
        "eda": {"describe": df[["age", "income", "score"]].describe().round(2).to_dict(),
                "gender": df["gender"].value_counts().to_dict(),
                "corr": df[["age", "income", "score", "is_male"]].corr().round(3).values.tolist(),
                "corr_cols": ["age", "income", "score", "is_male"]},
        "runtime_sec": round(time.time() - t0, 1),
    }
    joblib.dump({"scaler": scaler, "kmeans": km, "gmm": gmm, "cols": cols, "remap": remap,
                 "profiles": profiles}, ART / "model.joblib")
    dump(report, ART / "report.json")
    return report


if __name__ == "__main__":
    r = run()
    print("chosen:", r["chosen"])
    print("holdout:", r["holdout"])
    for p in r["profiles"]:
        print(f"  {p['cluster']} {p['persona']:38s} n={p['size']:3d} inc={p['income']:.0f} score={p['score']:.0f} age={p['age']:.0f}")
    print("agreement", r["algo_agreement"], "runtime", r["runtime_sec"])
