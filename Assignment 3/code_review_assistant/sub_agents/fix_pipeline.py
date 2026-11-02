"""Fix pipeline: LoopAgent(CodeFixer -> FixTestRunner -> FixValidator) -> FixSynthesizer.
The validator escalates (exits the loop) as soon as a fix is SUCCESSFUL."""
from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.code_executors import BuiltInCodeExecutor

from .. import config
from ..constants import StateKeys as K
from ..tools import compile_fix_report, exit_fix_loop, save_fix_report, validate_fixed_style


def fixer_instruction(ctx: ReadonlyContext) -> str:
    s = ctx.state
    return f"""You fix Python code. Original code:
```python
{s.get(K.CODE_TO_REVIEW, '')}
```
Review feedback: {s.get(K.FINAL_FEEDBACK, '')}
Test results: {s.get(K.TEST_RESULTS, '')}
Previous fix attempt report (empty on first try): {s.get(K.FIX_REPORT, '')}

Produce a corrected version that fixes every bug and style issue while keeping the
public interface the same. Add docstrings and type hints. Output ONLY the complete
code in one ```python block."""


def fix_test_instruction(ctx: ReadonlyContext) -> str:
    return f"""Write and EXECUTE 10-20 tests (with your code executor) for this fixed code,
focusing on the bugs reported earlier: {ctx.state.get(K.TEST_RESULTS, '')}

```python
{ctx.state.get(K.CODE_FIXES, '')}
```
Output ONLY JSON: {{"test_summary": {{"total": n, "passed": n, "failed": n}},
"verdict": {{"status": "WORKING|BUGGY|BROKEN"}}}}"""


code_fixer = LlmAgent(name="CodeFixer", model=config.CRITIC_MODEL, instruction=fixer_instruction,
                      output_key=K.CODE_FIXES, include_contents="none")

fix_test_runner = LlmAgent(name="FixTestRunner", model=config.WORKER_MODEL,
                           instruction=fix_test_instruction, code_executor=BuiltInCodeExecutor(),
                           output_key=K.FIX_TEST_RESULTS, include_contents="none")

fix_validator = LlmAgent(
    name="FixValidator",
    model=config.WORKER_MODEL,
    instruction="""Validate the fix:
1. Call `validate_fixed_style` (no arguments).
2. Call `compile_fix_report` (no arguments). Its `status` is SUCCESSFUL, PARTIAL or FAILED.
3. If status is SUCCESSFUL call `exit_fix_loop`. Otherwise do NOT call it, and list
   precisely what still has to change (another attempt will run).""",
    tools=[validate_fixed_style, compile_fix_report, exit_fix_loop],
    output_key="fix_validation",
    include_contents="none",
)

fix_attempt_loop = LoopAgent(name="FixAttemptLoop",
                             sub_agents=[code_fixer, fix_test_runner, fix_validator],
                             max_iterations=config.MAX_FIX_ITERATIONS)

fix_synthesizer = LlmAgent(
    name="FixSynthesizer",
    model=config.WORKER_MODEL,
    instruction="""Present the outcome of the automated fix.
Fix report: {fix_report?}
Fixed code: {code_fixes?}

Write Markdown: status badge (SUCCESSFUL / PARTIAL / FAILED), a before/after table
(style score, test verdict), a bullet list of what changed, the complete fixed code
in a python block, and anything that still needs manual attention. Call
`save_fix_report` with that Markdown, then output it.""",
    tools=[save_fix_report],
    output_key="fix_summary",
    include_contents="none",
)

code_fix_pipeline = SequentialAgent(
    name="CodeFixPipeline",
    description="Iteratively fixes the reviewed code (up to N attempts) and reports before/after.",
    sub_agents=[fix_attempt_loop, fix_synthesizer],
)
