"""
Lab 10.03 - Run the Budget RSI demo, then meet the same idea in TurbineGym.

Part 1 runs the course's laptop demo unchanged.
Part 2 shows what changes in our problem area: the "code edit" is a real diff of a real
pipeline program, the 8 features are read off that diff BEFORE running it, and the cost
of a full evaluation is a real model fit.
"""
import pathlib, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym import (TurbineGym, baseline_config, render, unified_diff, diff_features,
                        DIFF_FEATURE_NAMES, describe, edits)

labkit.header("10.03", "Run the Budget RSI demo")
labkit.section("Part 1: the course demo, unchanged (python demo.py)")
demo = labkit.course_repo() / "01_budget_rsi" / "demo.py"
print(subprocess.run([sys.executable, str(demo)], capture_output=True, text=True).stdout)

labkit.section("Part 2: the TurbineGym fleet")
gym = TurbineGym()
print(describe(gym.df))
print("Hidden mechanisms: per-sensor calibration offsets, firmware-v2 unit change (x2.2) after day 150-230,")
print("seasonal confounding of oil temperature, 15% particle-sensor dropout.")

labkit.section("The program being improved (rendered from the baseline config)")
base = baseline_config()
print(render(base))

labkit.section("One proposed edit, as a unified diff")
child = edits.apply(base, {"op": "add_transform", "arg": "firmware_rescale"})
child = edits.apply(child, {"op": "threshold_up"})
for line in unified_diff(render(base), render(child)):
    print("   " + line)

labkit.section("The 8 diff coordinates Budget RSI reads (nothing executed yet)")
for n, v in zip(DIFF_FEATURE_NAMES, diff_features(render(base), render(child))):
    print(f"   {n:18s} {v:+.3f}")

labkit.section("What a full evaluation actually costs")
t = time.time(); r0 = gym.evaluate(base); t0 = time.time() - t
t = time.time(); r1 = gym.evaluate(child); t1 = time.time() - t
print(f"   baseline   steering F1 {r0['f1']:.3f}  (precision {r0['precision']:.2f}, recall {r0['recall']:.2f})  {t0*1000:.0f} ms")
print(f"   edited     steering F1 {r1['f1']:.3f}  (precision {r1['precision']:.2f}, recall {r1['recall']:.2f})  {t1*1000:.0f} ms")
t = time.time()
for _ in range(1000):
    diff_features(render(base), render(child))
per = (time.time() - t) / 1000
print(f"   scoring one diff (render + diff + 8 features): {per*1000:.3f} ms  ->  ~{t1/per:.0f}x cheaper than a full evaluation")
print("   (TurbineGym evaluations are cheap on a laptop, so every lab counts COST UNITS from the ledger:")
print("    full evaluation = 1.0, fit-split evaluation = 0.25, probe = 0.05. In the paper one evaluation")
print("    is a coding-agent run over a benchmark split, which is where the real saving comes from.)")
print("   ledger:", gym.spend_summary())
