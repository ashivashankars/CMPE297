"""
Lab 10.06 - Run the SO-RSI demo, then watch first-order vs second-order improvement in TurbineGym.

Part 1 runs the course demo unchanged.
Part 2 runs our two improvers side by side on the same seed and budget (20 units). They share the
SAME first-order proposal policy; the only difference is the anomaly monitor + probes + inquiry memory.
"""
import pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from methods import so_rsi as S

labkit.header("10.06", "Run the SO-RSI demo")
labkit.section("Part 1: the course demo, unchanged (python demo.py) - last 25 lines")
demo = labkit.course_repo() / "02_second_order_rsi" / "demo.py"
out = subprocess.run([sys.executable, str(demo)], capture_output=True, text=True).stdout.splitlines()
print("\n".join(out[-25:]))

for mode in ("naive", "so_rsi"):
    labkit.section(f"Part 2: {mode.upper()} on TurbineGym (seed 0, budget 20 units)")
    print("  [step] source  symptom         edit                               steering F1           decision")
    r = S.run(mode, 0, budget=20, log=print)
    print(f"\n  final steering F1 {r.steer:.3f}  held-out F1 {r.heldout:.3f}  (baseline held-out {r.baseline_heldout:.3f})")
    print(f"  thrash: {r.thrash()}   spent {r.spent:.2f} units")
    print(f"  final pipeline: transforms={r.final_cfg['transforms']} model={r.final_cfg['model']} "
          f"alarm_rate={r.final_cfg['alarm_rate']}")
    if mode == "so_rsi":
        print("\n  INQUIRY MEMORY")
        for m in r.inquiry_memory:
            print(f"   - [{m['status']:16s}] {m['hypothesis']:52s} evidence: {m['evidence']}")
