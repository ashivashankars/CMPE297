"""FROZEN. The only code that is allowed to compute the score.

    python evaluate.py train.py            -> prints {"val_auc": ..., "seconds": ...}
    python evaluate.py train.py --final    -> also scores the hidden test split

The researcher never runs its own metric; the harness runs this file.
"""
import importlib.util
import json
import sys
import time

import pandas as pd
from sklearn.metrics import roc_auc_score

from prepare import DATA, TARGET


def load_candidate(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score(mod, train, other):
    X_tr = mod.make_features(train.drop(columns=[TARGET]))
    X_ot = mod.make_features(other.drop(columns=[TARGET])).reindex(columns=X_tr.columns, fill_value=0)
    model = mod.build_model()
    model.fit(X_tr, train[TARGET])
    return roc_auc_score(other[TARGET], model.predict_proba(X_ot)[:, 1]), list(X_tr.columns)


if __name__ == "__main__":
    t0 = time.time()
    mod = load_candidate(sys.argv[1])
    train = pd.read_csv(f"{DATA}/train.csv")
    val = pd.read_csv(f"{DATA}/val.csv")
    val_auc, cols = score(mod, train, val)
    out = {"val_auc": round(val_auc, 4), "n_features": len(cols), "features": cols}
    if "--final" in sys.argv:   # refit on train+val, score the untouched test split once
        test = pd.read_csv(f"{DATA}/test.csv")
        out["test_auc"] = round(score(mod, pd.concat([train, val], ignore_index=True), test)[0], 4)
    out["seconds"] = round(time.time() - t0, 2)
    print(json.dumps(out))
