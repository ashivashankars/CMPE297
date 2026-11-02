"""Root agent for (d): production-quality code review assistant.

  CodeReviewAssistant (router)
   ├─ CodeReviewPipeline  : CodeAnalyzer -> StyleChecker -> TestRunner(sandbox) -> FeedbackSynthesizer
   └─ CodeFixPipeline     : Loop[CodeFixer -> FixTestRunner(sandbox) -> FixValidator] -> FixSynthesizer
"""
from google.adk.agents import LlmAgent

from . import config
from .sub_agents.fix_pipeline import code_fix_pipeline
from .sub_agents.review_pipeline import code_review_pipeline

root_agent = LlmAgent(
    name="CodeReviewAssistant",
    model=config.WORKER_MODEL,
    description="Reviews Python code (structure, style, executed tests) and can auto-fix it.",
    instruction="""You are a Python code review assistant.

- When the user shares Python code to review, transfer to `CodeReviewPipeline`
  immediately; do not review it yourself.
- After a review, if style score < 100 or tests are not WORKING, the review ends
  with an offer to fix. When the user accepts (e.g. "yes", "fix it"), transfer to
  `CodeFixPipeline`. Only do this if a review exists (current style score:
  {style_score?}).
- For questions about what you can do, explain briefly: AST structure & complexity
  analysis, PEP 8 scoring, tests executed in a sandbox, history-aware feedback,
  and an iterative auto-fix loop with before/after metrics. Reviews and fixes are
  saved as downloadable artifacts.""",
    sub_agents=[code_review_pipeline, code_fix_pipeline],
)
