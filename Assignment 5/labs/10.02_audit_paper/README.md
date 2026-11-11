# 10.02 · Audit three October 2026 papers

**Purpose:** before building, check what each paper actually measured, and say exactly what my laptop adaptation keeps and what it drops.

Paper facts below come from the course's `12_october_2026_papers/PAPER_SUMMARIES.md`. I did not re-read the arXiv PDFs, so any number here is "as summarised by the course".

There is no code in this lab. The audit decides the experiments in 10.05, 10.08 and 10.11: each untested assumption below becomes an ablation, a baseline or a control.

---

## Audit 1 — Budget RSI: scoring code edits before they run (arXiv:2610.29121)

| Aspect | Paper's setup | My TurbineGym adaptation | What's preserved |
|---|---|---|---|
| Changed object | Coding-agent scaffold edits (diffs) | Diffs of a generated Python pipeline module (`render(cfg)`) | A real code diff is scored before it runs |
| Feedback | Steering-split solve counts; 96 edits labelled on a 16-instance fit split | Steering-split F1; 32–96 edits labelled with the cheap `evaluate_fit` service | Cheap noisy labels train the scorer; steering split selects |
| Scorer | Linear readout on parent rate + 8 diff coordinates | Ridge-linear readout on parent rate + 8 coordinates parsed from the diff text | Same functional form |
| Search | Huxley–Gödel Machine, Thompson sampling on steering counts | Thompson sampling over evaluated pipelines, K=8 proposals per step | Same selection logic |
| Evaluation | Held-out HumanEval+ / Polyglot | Held-out last 75 days of the fleet, audited once | Clean held-out boundary |
| Compute | GPT-4o agent runs | Cost units from a ledger (full eval = 1.0, fit eval = 0.25) | Matched budgets that include the scorer's own cost |
| Untested assumption | That the 8 diff coordinates carry signal beyond the parent's rate | **Tested in 10.04:** with 0 diff coordinates (parent rate only) the readout picks equally well | — |

**Assumption I test:** the paper's +2.8-point gain over the parent-rate ablation. Lab 10.04 compares the selectors directly; lab 10.05 compares them under a matched budget.

## Audit 2 — SO-RSI: second-order diagnostic inquiry (arXiv:2610.05701)

| Aspect | Paper's setup | My TurbineGym adaptation | What's preserved |
|---|---|---|---|
| Changed object | Workflow edits for Lean 4 / Verus agents | Pipeline edits (first-order knobs and structural transforms) | First-order vs second-order edits |
| Feedback | Execution traces | The improver's own trace: edit, predicted effect, steering metrics before/after | Anomalies are detected on the improver's own history |
| Anomalies | Recurrence, opposing edits, expectation mismatch | The same three, detected from the trace | Same three |
| Probes | Lightweight mechanism investigations | 5 read-only statistical probes on raw sensor data (cost 0.05 each) | Probes are cheap, read-only and produce hypotheses |
| Memory | Persistent inquiry memory across RSI rounds | Hypotheses with status supported / refuted-by-test / refuted-by-probe, carried to a second wind farm | Memory persists and is re-verified |
| Evaluation | 24-hour searches, held-out proofs | 20-unit budget, 16 seeds, held-out F1 | Paired comparison against a naive improver with the same policy |
| Untested assumption | That the gain comes from the diagnostics | **Tested in 10.01:** in the course demo it does not (the rate is hard-coded). In my version both improvers share one proposal policy, so any gap comes from the monitor, probes and memory | — |

**Assumption I test:** that inquiry memory transfers across rounds (lab 10.08, part B). **Limit:** I wrote the probe library myself, knowing which mechanisms the simulator plants. A fair reading is "given a good probe library, second-order inquiry uses it well", not "SO-RSI discovers mechanisms it has no probe for".

## Audit 3 — SwarmRSI: evolving scientific agent swarm (arXiv:2610.20431)

| Aspect | Paper's setup | My TurbineGym adaptation | What's preserved |
|---|---|---|---|
| Changed object | Hypotheses + implementations of LLM scientist agents | 5 agents, each with a research direction (preference over edit families) and a pipeline | Hypothesis + implementation per agent |
| Feedback | Results from other agents | Shared experience table: (edit, context) → observed gains | Feedback-guided mutation |
| Recombination | Reuse retained hypotheses and components | Union of transforms each agent has credit for | Complementary recombination |
| Recursion | Swarm evolution integrates both | Agents re-weight their own direction; swarm adapts its recombination rate | The procedure revises itself |
| Evaluation | OpenProblems, NatureBench, MLE-Bench Lite | 30 and 60 units, 16 seeds, held-out F1 | Matched-budget comparison |
| Untested assumption | That a swarm beats one well-run agent at equal compute | **Tested in 10.11** against a single hill-climber with the whole budget | — |

**Two assumptions I test:** whether each component (recombination, recursive revision) helps, through ablations; and whether shared experience must be context-conditional. Building it showed it must: context-free sharing let a "z-scoring doesn't help" finding block z-scoring after the firmware fix, where it does help.

## What a laptop adaptation can and cannot show

- **Can show:** the mechanism runs, its parts can be removed one at a time, and its effect can be measured on real model fits with a held-out split.
- **Cannot show:** any paper's headline number. My fleet is synthetic, small, and has only four planted mechanisms.
