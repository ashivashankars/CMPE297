"""FROZEN. Generates the churn dataset and the time-based train / val / test split.

Run once:  python prepare.py
The harness hashes this file, evaluate.py and data/*.csv before every experiment.
"""
import os

import numpy as np
import pandas as pd

TARGET = "churned"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def generate(n=6000, seed=297):
    rng = np.random.default_rng(seed)
    plan = rng.choice(["basic", "pro", "enterprise"], n, p=[0.55, 0.3, 0.15])
    contract = rng.choice(["monthly", "annual"], n, p=[0.6, 0.4])
    region = rng.choice(["west", "east", "south", "north"], n)
    base = pd.Series(plan).map({"basic": 20, "pro": 55, "enterprise": 140}).to_numpy()
    spend = np.round(base * rng.uniform(0.7, 1.3, n), 2)
    discount = rng.choice([0, 0, 0, 10, 20, 30], n)
    tickets = rng.poisson(1.2, n)
    tenure = rng.integers(1, 72, n)
    logins = rng.poisson(12, n)
    last_login = rng.exponential(9, n).round()
    inactive = rng.random(n) < 0.22
    days = rng.integers(0, 365, n)
    signup = pd.to_datetime("2025-01-01") + pd.to_timedelta(days, unit="D")

    logit = (-2.2 + 0.45 * tickets + 0.035 * np.minimum(last_login, 40) - 0.035 * tenure
             + 0.9 * (contract == "monthly") + 1.3 * inactive - 0.05 * logins
             + 0.5 * tickets * (plan == "basic") * (contract == "monthly")
             - 0.6 * (plan == "enterprise") + 0.02 * discount * (tenure < 12)
             + 0.25 * (region == "south"))
    churn = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)

    last_login_obs = np.where(inactive, np.nan, last_login)
    refund = np.where(churn == 1, np.round(spend * rng.uniform(0.5, 1.0, n), 2), 0.0)
    return pd.DataFrame({
        "customer_id": np.arange(1, n + 1), "signup_date": signup.strftime("%Y-%m-%d"),
        "region": region, "plan": plan, "contract": contract, "monthly_spend": spend,
        "discount_pct": discount, "support_tickets": tickets, "tenure_months": tenure,
        "logins_30d": logins, "last_login_days": last_login_obs, "refund_amount": refund,
        TARGET: churn,
    })


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    df = generate().sort_values("signup_date")
    month = pd.to_datetime(df["signup_date"]).dt.month
    splits = {"train": df[month <= 8], "val": df[month.isin([9, 10])], "test": df[month >= 11]}
    for name, part in splits.items():
        part.to_csv(os.path.join(DATA, f"{name}.csv"), index=False)
        print(f"{name:5}: {len(part):5} rows, churn rate {part[TARGET].mean():.3f}")
