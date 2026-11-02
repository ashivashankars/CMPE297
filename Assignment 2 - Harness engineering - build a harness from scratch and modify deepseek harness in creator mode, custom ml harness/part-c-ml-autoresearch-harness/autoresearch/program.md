# Research program: customer churn

**Goal.** Maximise validation ROC-AUC for predicting `churned` on the churn dataset.

**You may edit only `train.py`.** It must define:
- `make_features(df) -> pandas.DataFrame` — turns raw columns into numeric features.
  `df` never contains the target column.
- `build_model()` — returns an unfitted scikit-learn estimator with `predict_proba`.

**Rules (enforced by the harness, not by trust):**
1. `prepare.py`, `evaluate.py` and `data/` are frozen. Any change to them voids the run.
2. `refund_amount` is recorded *after* a customer churns. Using it is target leakage.
3. Each experiment must finish in the time budget (default 60 s).
4. One idea per experiment, stated as a hypothesis. Keep changes small so results are attributable.
5. The test split is never shown to you. It is scored once, at the end, on the best kept model.

**Columns:** customer_id, signup_date, region, plan, contract, monthly_spend, discount_pct,
support_tickets, tenure_months, logins_30d, last_login_days (missing = no recent login), refund_amount.
