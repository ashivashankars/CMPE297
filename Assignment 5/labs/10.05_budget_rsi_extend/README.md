# 10.05 · Extend Budget RSI to my own edits: matched-budget search

**Purpose:** run Budget RSI as a complete improver on pipeline edits, against the paper's baselines, at an equal cost.

```bash
python3 labs/10.05_budget_rsi_extend/budget_search.py      # ~2.5 min
```
Output: [`output.txt`](output.txt) · `results/10_05_budget_search.json`

## Code walkthrough (`methods/budget_rsi.py: run`)
1. If the strategy is Budget RSI, call `label_edits(...)`: 32 cheap labels (8 units), paid **from the same budget**.
2. Evaluate the baseline and make it the root node.
3. Each step: draw K=8 (parent, child) proposals; parents by `thompson_parent` (Beta draw on steering F1), children by 1–2 random edits.
4. Choose one proposal to evaluate: `random` takes the first; `parent_rate` takes the best parent; `budget_rsi` takes the best readout score from the diff.
5. `budget_rsi_online` refits the readout after every full evaluation, so the improver revises its own scorer.
6. Stop when the ledger says the budget is spent. Return the **earliest** node with the maximal steering F1, then audit it on held-out.

## Results (16 seeds, held-out F1, mean ± 95% CI)
| Strategy | Budget 16 | Budget 32 | Full evals used (32) |
|---|---|---|---|
| HGM random expansion | 0.637 ± 0.081 | 0.736 ± 0.070 | 32 |
| Parent-rate ablation | 0.653 ± 0.071 | 0.700 ± 0.076 | 32 |
| **Budget RSI** | **0.712 ± 0.063** | **0.798 ± 0.019** | 23.7 |
| Budget RSI + online refit | 0.709 ± 0.053 | 0.794 ± 0.038 | 23.7 |

Paired sign tests vs HGM random: budget 16, 11 wins / 5 losses (p=0.21); budget 32, 9/7 (p=0.80). Online refit at budget 16: 12/4 (p=0.077).

## What it means
- Budget RSI has the **best mean at both budgets while using about 25% fewer full evaluations**, and a much smaller spread (std 0.038 vs 0.142 at budget 32). It almost never ends in a bad pipeline.
- The win/loss counts are **not significant** at 16 seeds, so I claim "consistently competitive and more reliable", not "better".
- Parent-rate ablation alone is *worse* than random at budget 32: always expanding the best parent over-exploits a steering score that is partly noise.

**Next:** [Group 02 · SO-RSI](../10.06_so_rsi_run_demo/README.md)
