"""Review pipeline: Analyzer -> StyleChecker -> TestRunner -> FeedbackSynthesizer."""
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.code_executors import BuiltInCodeExecutor

from .. import config
from ..constants import StateKeys as K
from ..tools import (analyze_code_structure, check_code_style, save_review_report,
                     search_past_feedback)

code_analyzer = LlmAgent(
    name="CodeAnalyzer",
    model=config.WORKER_MODEL,
    description="Parses the code and extracts structure, complexity and risk flags.",
    instruction="""You analyse Python code structure.
Call `analyze_code_structure` with the user's code EXACTLY as provided (no edits).
If it returns a syntax_error, report the line and message and stop.
Otherwise summarise in <=6 bullets: what the code does, functions/classes, the most
complex function (complexity score), docstring coverage and any risk flags
(eval/exec, bare except, mutable default args).""",
    tools=[analyze_code_structure],
    output_key="structure_summary",
)

style_checker = LlmAgent(
    name="StyleChecker",
    model=config.WORKER_MODEL,
    description="Runs PEP 8 and naming checks and computes a style score.",
    instruction="""You check code style. Call `check_code_style` with an empty string
for `code` (the tool reads the code saved in state). Report the score out of 100,
group the issues by type, and list the 5 most important with line numbers.""",
    tools=[check_code_style],
    output_key="style_summary",
    include_contents="none",
)


def test_runner_instruction(ctx: ReadonlyContext) -> str:
    # Callable instructions are not template-expanded, so braces in code are safe.
    code = ctx.state.get(K.CODE_TO_REVIEW, "")
    return f"""You are a testing specialist. Infer what this code is supposed to do
from its names, docstrings and structure, then WRITE AND EXECUTE 10-20 tests with
your code executor (normal cases, edge cases, invalid input).

CODE UNDER TEST:
```python
{code}
```

After executing, output ONLY this JSON:
{{"test_summary": {{"total": n, "passed": n, "failed": n, "errors": n}},
  "critical_issues": [{{"type": "logic_error|crash|interface_bug", "description": "...",
     "example_input": "...", "expected": "...", "actual": "...", "severity": "high|medium|low"}}],
  "verdict": {{"status": "WORKING|BUGGY|BROKEN", "confidence": "high|medium|low"}}}}"""


test_runner = LlmAgent(
    name="TestRunner",
    model=config.WORKER_MODEL,
    description="Generates and executes tests in Gemini's sandboxed code executor.",
    instruction=test_runner_instruction,
    code_executor=BuiltInCodeExecutor(),
    output_key=K.TEST_RESULTS,
    include_contents="none",
)

feedback_synthesizer = LlmAgent(
    name="FeedbackSynthesizer",
    model=config.CRITIC_MODEL,
    description="Combines all findings into prioritised, educational feedback.",
    instruction="""You are a senior engineer writing a code review for a developer.

Inputs:
- Structure: {structure_summary?}
- Style (score {style_score?}/100): {style_summary?}
- Tests: {test_execution_summary?}

Steps:
1. Call `search_past_feedback` to see this developer's history; if issues recur,
   say so kindly, and celebrate improvements.
2. Write the review in Markdown:
   ## Summary (one paragraph + overall verdict)
   ## What works well
   ## Must fix (bugs/crashes from tests, security risks) - with line numbers
   ## Should improve (complexity, style, docs) - with concrete before/after snippets
   ## Scores (table: Style, Tests passed, Max complexity, Docstring coverage)
3. Call `save_review_report` with the full Markdown.
4. Output the same Markdown as your final answer.""",
    tools=[search_past_feedback, save_review_report],
    output_key=K.FINAL_FEEDBACK,
)

code_review_pipeline = SequentialAgent(
    name="CodeReviewPipeline",
    description="Full review: structure analysis, style scoring, test execution, feedback.",
    sub_agents=[code_analyzer, style_checker, test_runner, feedback_synthesizer],
)
