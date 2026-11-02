"""Plot validation AUC per experiment from runs/results.tsv -> runs/progress.png"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(HERE, "runs", "results.tsv"), sep="\t")
df["val"] = pd.to_numeric(df["val_auc"], errors="coerce")
best = df["val"].where(df["status"] == "keep").cummax().ffill()

colors = {"keep": "#1a7f37", "discard": "#9a6700", "crash": "#cf222e", "rejected": "#8250df", "bad-edit": "#57606a"}
fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
ax.step(df["iter"], best, where="post", color="#0969da", lw=2, label="best kept model")
for status, part in df.groupby("status"):
    y = part["val"].fillna(best[part.index])
    ax.scatter(part["iter"], y, s=70, color=colors.get(status, "k"), label=status, zorder=3,
               marker="o" if part["val"].notna().all() else "x")
ax.set_xlabel("experiment"); ax.set_ylabel("validation ROC-AUC")
ax.set_title("Autoresearch: every idea is scored by the frozen evaluator")
ax.grid(alpha=0.3); ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower right")
fig.tight_layout(); fig.savefig(os.path.join(HERE, "runs", "progress.png"))
print("wrote runs/progress.png")
