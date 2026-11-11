# 10.12 · Compare workflow adaptation: RSIFlow vs Self-HPO

**Purpose:** distinguish adapting the improvement **workflow** (RSIFlow) from co-optimising the **harness and the policy** (Self-HPO), before simulating each one (10.13, 10.14).

| Aspect | RSIFlow (my lab 10.13) | Self-HPO (my lab 10.14) |
|---|---|---|
| What adapts | Which workflow stage gets the next evaluation (data → calibration → signal → model → alerting) | The acceptance test-suite (harness) used to judge edits |
| Who adapts it | An evolving meta-agent that profiles the bottleneck (UCB on recent per-stage gains) and puts stages that keep failing on cooldown | The policy itself: an H-step reads its own per-turbine failures and builds the next suite from its hardest turbines |
| Iteration | Continuous routing | Alternating H-step / P-step |
| Changed object | The improvement procedure (routing) | The evaluation procedure (harness) + the pipeline (policy) |
| Risk | Routing on noisy gains can starve a stage that would pay off later | A suite of hard cases is small and noisy, so it can overfit those turbines |

**RSIFlow is preferable** when the bottleneck moves: e.g. once the firmware drift is fixed, the bottleneck shifts from calibration to the trend signal.

**Self-HPO is preferable** when full evaluations are expensive but a targeted test-suite is cheap, and the system's failures are concentrated (here: on the firmware-v2 turbines).

## Quiz

**Q1. Both methods change the improvement procedure. What exactly does each change?**
RSIFlow changes *where* effort goes. Self-HPO changes *how candidate edits are judged*.

**Q2. Why can Self-HPO beat "evaluate everything fully"?**
A suite of the policy's hardest turbines is cheaper than a full evaluation, so more candidates can be tried. Those turbines are also where the signal for the next improvement is. Lab 10.14 measures this.
