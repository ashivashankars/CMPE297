# Recording guide: one video per part

The assignment asks for a video for each part, showing code and execution, in your own words. Below are six parts, one per studio group in Section 10. Each has what to show on screen, the command to run live, and talking points. Target 6–10 minutes per video.

**Setup before recording**
```bash
cd "Assignment 5"
pip install -r requirements.txt
./run_all.sh 10.01        # warms the course-repo clone so the first video doesn't wait on git
```
Use a large terminal font (≥16pt), keep the editor and terminal side by side, and clear the terminal between commands.

After you upload each video, paste its link into the table in `README.md`.

---

## Part 1 — Reading a frontier claim (labs 10.01–10.02) · ~7 min

**Show:** `labs/10.01_claim_vs_evidence/audit_course_demos.py`, then run it.
```bash
python3 labs/10.01_claim_vs_evidence/audit_course_demos.py
```
**Say:**
1. "Before implementing three RSI methods, I checked whether the course's own demos are *evidence* or *illustration*."
2. Scroll to `generate_synthetic_edits` in the course demo: held-out is `6 × steering + noise`, so a linear scorer must look good.
3. Point at the SO-RSI line `random.random() < 0.5` vs `< 0.3`. Run it: with diagnostics switched off the gap is still 50.5% vs 30%. "The improvement is hard-coded, not caused by the probes."
4. Open `labs/10.02_audit_paper/README.md`: walk through one audit table and the "untested assumption" row for each paper. "Each untested assumption became an ablation in my experiments."

## Part 2 — The problem area and Budget RSI (labs 10.03–10.05) · ~10 min

**Show:** `turbinegym/fleet.py` (the four hidden mechanisms), `turbinegym/pipeline.py` (`render`, `diff_features`), then `methods/budget_rsi.py`.
```bash
python3 labs/10.03_budget_rsi_run_demo/run_demo.py
python3 labs/10.04_budget_rsi_mechanism/analyze_readout.py
python3 labs/10.05_budget_rsi_extend/budget_search.py     # ~2.5 min, start it, then narrate the code
```
**Say:**
1. "My problem area is wind-turbine gearbox failure early warning: predict failure 14 days ahead from vibration, oil temperature and particle sensors."
2. "The thing being improved is a *program*: the config is rendered to real Python source and exec'd. An edit is a real diff." Show the diff and its 8 coordinates printed by 10.03.
3. In `budget_rsi.py`, walk through `LinearReadout`, `label_edits` (cheap fit-split labels), `thompson_parent`, and the three selection rules in `run`.
4. 10.04 result: the readout ranks edits well, but almost all of its weight is on the parent rate. With zero diff coordinates it picks just as well, so the paper's diff-feature advantage did not transfer to my domain.
5. 10.05 result: at a matched budget (Budget RSI pays for its labels), Budget RSI has the best mean and the lowest spread. Read out the sign test honestly: it is not significant at 16 seeds.

## Part 3 — SO-RSI: diagnose before you patch (labs 10.06–10.08) · ~10 min

**Show:** `methods/so_rsi.py`: `PATCHES` (the shared first-order policy), `detect_anomalies`, the five `probe_*` functions, `PROBES_FOR`, and the `banned` / `stale` sets (the improver revising itself).
```bash
python3 labs/10.06_so_rsi_run_demo/run_demo.py
python3 labs/10.07_so_rsi_probes/analyze_probes.py
python3 labs/10.08_so_rsi_apply/debug_and_compare.py
```
**Say:**
1. In the naive trace: it keeps raising the alarm bar and lowering C, and gets stuck around F1 0.3. Its held-out score ends *below* the baseline.
2. In the SO-RSI trace: the first mismatch triggers the firmware-drift probe ("vibration jumps ×2.18 at firmware v2"). The structural fix takes F1 from 0.22 to 0.52 in one step, then the trend probe takes it to 0.69.
3. 10.07 control fleet: the firmware probe goes quiet when the firmware change is removed. "A probe that fires anyway would be a bad probe."
4. 10.08: the acceptance test passes in 16/16 seeds vs 0/16. On a second wind farm, inherited memory passes 16/16 with only 8 units; starting fresh passes 2/16.
5. Limit: "I wrote the probe library knowing the simulator. The claim is *given good probes, second-order inquiry uses them well*."

## Part 4 — Scaling: AReaL-RSI and SwarmRSI (labs 10.09–10.11) · ~9 min

**Show:** `labs/10.09_compare_scaling/README.md`, then `methods/areal_rsi.py` (`ConditionalMemory`, leader choice), then `methods/swarm_rsi.py` (`ctx`, `_pick_edit`, recombination, `p_recomb` update).
```bash
python3 labs/10.10_areal_leader_follower/areal_sim.py
python3 labs/10.11_swarm_rsi/swarm_experiment.py          # ~4 min
```
**Say:**
1. AReaL: the leader over-exploits a direction that just paid off, and loses to a simple round-robin team. Read the orientation sequences it prints.
2. SwarmRSI verbose run: point at "recombine with signal (+firmware_rescale)". That is two agents' findings merged into a pipeline neither found alone.
3. Explain `ctx()`: experience must be conditional on context. Context-free sharing let "z-scoring doesn't help" block z-scoring after the firmware fix, where it does help.
4. Results: sharing clearly beats independent agents. Compare with the single hill-climber honestly, and with the ablations.

## Part 5 — Adaptive workflows: RSIFlow and Self-HPO (labs 10.12–10.14) · ~7 min

**Show:** `labs/10.12_compare_workflows/README.md`, `methods/rsiflow.py` (UCB routing, cooldown), `methods/self_hpo.py` (H-step builds the harness from `per_turbine_errors`).
```bash
python3 labs/10.13_rsiflow_meta_agent/rsiflow_sim.py
python3 labs/10.14_self_hpo/self_hpo_sim.py
```
**Say:** the routing moves from calibration to signal once the firmware drift is fixed. The Self-HPO harness fills up with firmware-v2 turbines, the policy's actual failure mode, and alternating beats both a fixed harness and full evaluation.

## Part 6 — Environments and metrics (labs 10.15–10.17) + conclusion · ~7 min

```bash
python3 labs/10.16_environments/environment_tracks.py
python3 labs/10.15_rsi_index/rsi_index.py
python3 labs/10.17_metrics/metrics_analysis.py
```
**Say:**
1. TurbineGym is an RSIGym-style service environment with a cost ledger. Show the budget enforcement, and the data / harness / joint tracks.
2. Work through the RSI-Index example and read the table, comparing only within a family.
3. The steering-to-held-out gap, reliability and points-per-unit: "a method with a good mean can still be unreliable."
4. Close with the three claims and their limits, from the README "Conclusions" section.
