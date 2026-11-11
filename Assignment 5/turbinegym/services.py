"""
TurbineGym services - an "Everything-as-a-Service" environment in the spirit of RSIGym.

Improvers never touch the data directly. They call services:

    gym.evaluate(cfg)          full evaluation on the steering split   (cost 1.0)
    gym.evaluate_fit(cfg)      cheap noisy evaluation on a fit split   (cost 0.25)
    gym.audit_heldout(cfg)     held-out score - for the FINAL report only, never for selection
    gym.probe(name)            read-only diagnostic queries on TRAIN/STEER sensor data (cost 0.05)

Every call is written to a ledger so each method's spend can be compared fairly.
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from .fleet import make_fleet, N_TURBINES, FIRMWARE_FACTOR
from .pipeline import config_key, normalise, render

@functools.lru_cache(maxsize=4)
def _fleet(seed: int, firmware_factor: float) -> pd.DataFrame:
    return make_fleet(seed, firmware_factor)


COSTS = {"evaluate": 1.0, "evaluate_fit": 0.25, "probe": 0.05}   # evaluate_suite: 0.1 + 0.9*share


class BudgetExceeded(RuntimeError):
    pass


class TurbineGym:
    _feat_cache: dict = {}          # shared across instances: features are deterministic per (seed, transforms)
    def __init__(self, seed: int = 7, budget: float | None = None, firmware_factor: float = FIRMWARE_FACTOR):
        self.df = _fleet(seed, firmware_factor)
        self.firmware_factor = firmware_factor
        self.budget = budget
        self.spent = 0.0
        self.ledger: list[tuple[str, str, float]] = []
        self.seed = seed
        self._eval_cache: dict = {}
        rng = np.random.default_rng(1234)
        ids = rng.permutation(N_TURBINES)
        self.fit_train_ids = set(ids[:10].tolist())    # cheap eval trains on 10 turbines
        self.fit_score_ids = set(ids[10:18].tolist())  # ...and scores on 8 turbines

    # ------------------------------------------------------------------ plumbing
    def _charge(self, service: str, key: str):
        cost = COSTS[service]
        if self.budget is not None and self.spent + cost > self.budget + 1e-9:
            raise BudgetExceeded(f"{service} would exceed budget {self.budget}")
        self.spent += cost
        self.ledger.append((service, key, cost))

    def load(self, cfg: dict):
        """exec() the rendered pipeline source and return its namespace."""
        src = render(cfg)
        ns: dict = {}
        exec(compile(src, f"<pipeline {config_key(cfg)}>", "exec"), ns)
        return ns

    def _features(self, cfg: dict, ns: dict):
        k = (self.seed, self.firmware_factor, tuple(normalise(cfg)["transforms"]))
        if k not in self._feat_cache:
            self._feat_cache[k] = ns["build_features"](self.df)[0]
        df = self._feat_cache[k]
        return df, df[ns["FEATURES"]].fillna(0.0)

    def _fit_predict(self, cfg: dict, train_mask_fn, score_mask_fn):
        ns = self.load(cfg)
        df, X = self._features(cfg, ns)
        tr, sc = train_mask_fn(df), score_mask_fn(df)
        model = ns["make_model"]()
        model.fit(X[tr], df.label[tr])
        # the pipeline calibrates its own alarm bar on TRAIN scores (no peeking at the scored split)
        bar = float(np.quantile(model.predict_proba(X[tr])[:, 1], 1 - ns["ALARM_RATE"]))
        p = model.predict_proba(X[sc])[:, 1]
        y = df.label[sc].to_numpy()
        yhat = (p > bar).astype(int)
        return {
            "f1": float(f1_score(y, yhat, zero_division=0)),
            "precision": float(precision_score(y, yhat, zero_division=0)),
            "recall": float(recall_score(y, yhat, zero_division=0)),
            "pr_auc": float(average_precision_score(y, p)) if y.sum() else 0.0,
            "alarms": int(yhat.sum()), "positives": int(y.sum()),
            "_proba": p, "_y": y, "_rows": df[sc], "_bar": bar,
        }

    @staticmethod
    def _public(r: dict) -> dict:
        return {k: v for k, v in r.items() if not k.startswith("_")}

    # ------------------------------------------------------------------ services
    def evaluate(self, cfg: dict, detail: bool = False) -> dict:
        """Train on TRAIN, score on STEERING split. Cost 1.0 - re-running an experiment you
        already ran is still charged (a real agent would pay for it), the result is just reused."""
        key = "steer:" + config_key(cfg)
        self._charge("evaluate", key)
        if key not in self._eval_cache:
            self._eval_cache[key] = self._fit_predict(
                cfg, lambda d: (d.split == "train").to_numpy(), lambda d: (d.split == "steer").to_numpy())
        r = self._eval_cache[key]
        return r if detail else self._public(r)

    def evaluate_suite(self, cfg: dict, turbine_ids) -> dict:
        """Evaluate on a SUBSET of steering turbines (a harness / test suite).
        Cost 0.1 + 0.9 * share of turbines - smaller suites are cheaper."""
        ids = sorted(set(int(i) for i in turbine_ids))
        cost = 0.1 + 0.9 * len(ids) / N_TURBINES
        if self.budget is not None and self.spent + cost > self.budget + 1e-9:
            raise BudgetExceeded("suite")
        self.spent += cost
        key = "steer:" + config_key(cfg)
        self.ledger.append(("evaluate_suite", key, cost))
        if key not in self._eval_cache:
            self._eval_cache[key] = self._fit_predict(
                cfg, lambda d: (d.split == "train").to_numpy(), lambda d: (d.split == "steer").to_numpy())
        r = self._eval_cache[key]
        m = r["_rows"].turbine_id.isin(ids).to_numpy()
        y, p = r["_y"][m], r["_proba"][m]
        yhat = (p > r["_bar"]).astype(int)
        return {"f1": float(f1_score(y, yhat, zero_division=0)), "positives": int(y.sum()),
                "alarms": int(yhat.sum())}

    def per_turbine_errors(self, cfg: dict) -> dict:
        """Uses a full evaluation (cost 1.0): false alarms + misses per steering turbine."""
        r = self.evaluate(cfg, detail=True)
        rows = r["_rows"].assign(err=((r["_proba"] > r["_bar"]).astype(int) != r["_y"]).astype(int))
        return rows.groupby("turbine_id").err.sum().to_dict()

    def evaluate_fit(self, cfg: dict) -> dict:
        """Cheap, noisy label: train on 10 turbines, score on 8 others' steering rows. Cost 0.25."""
        key = "fit:" + config_key(cfg)
        if key not in self._eval_cache:
            self._charge("evaluate_fit", key)
            self._eval_cache[key] = self._fit_predict(
                cfg,
                lambda d: ((d.split == "train") & d.turbine_id.isin(self.fit_train_ids)).to_numpy(),
                lambda d: ((d.split == "steer") & d.turbine_id.isin(self.fit_score_ids)).to_numpy())
        return self._public(self._eval_cache[key])

    def audit_heldout(self, cfg: dict, detail: bool = False) -> dict:
        """Held-out score for reporting only. Logged with zero cost and flagged as an audit."""
        key = "heldout:" + config_key(cfg)
        self.ledger.append(("audit_heldout", key, 0.0))
        if key not in self._eval_cache:
            self._eval_cache[key] = self._fit_predict(
                cfg, lambda d: (d.split != "heldout").to_numpy(), lambda d: (d.split == "heldout").to_numpy())
        r = self._eval_cache[key]
        return r if detail else self._public(r)

    def sensor_view(self, splits=("train", "steer")) -> pd.DataFrame:
        """Read-only raw sensor rows for diagnostic probes (labels only for train)."""
        self._charge("probe", "sensor_view")
        d = self.df[self.df.split.isin(splits)].copy()
        d.loc[d.split != "train", "label"] = -1          # steering labels are hidden from probes
        return d

    def spend_summary(self) -> dict:
        out: dict = {}
        for s, _, c in self.ledger:
            n, tot = out.get(s, (0, 0.0))
            out[s] = (n + 1, tot + c)
        return out
