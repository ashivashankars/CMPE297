"""The ONLY file the researcher edits (copied to train.py by `harness.py reset`).

Baseline: logistic regression on the numeric columns, median-imputed.
"""
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

NUMERIC = ["monthly_spend", "discount_pct", "support_tickets", "tenure_months",
           "logins_30d", "last_login_days"]


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    X = df[NUMERIC].copy()
    return X


def build_model():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=1000))
