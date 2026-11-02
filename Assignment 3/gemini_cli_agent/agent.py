"""Root agent for (b): Gemini CLI as a tool inside an ADK pipeline.

Pipeline (exposed to the root agent as a single AgentTool):

  RepoTaskPipeline (SequentialAgent)
   ├─ RepoPreparer        -> prepare_repository (safe shallow git clone)
   ├─ RefinementLoop (LoopAgent, max N)
   │    ├─ CliExecutor    -> run_gemini_cli (1-3 focused headless CLI runs) -> draft
   │    └─ Critic         -> exit_loop when the draft is grounded and complete
   └─ ReportWriter        -> final Markdown + artifact gemini_cli_report.md
"""
from typing import Optional

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.tools import exit_loop
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from . import config, prompts
from .tools import gemini_cli_health, prepare_repository, run_gemini_cli


def capture_task(callback_context) -> Optional[types.Content]:
    """Store the request text handed to the pipeline so every stage can see it."""
    content = callback_context.user_content
    if content and content.parts:
        text = " ".join(p.text for p in content.parts if p.text)
        if text:
            callback_context.state["user_task"] = text
    callback_context.state["critique"] = ""
    callback_context.state["cli_calls"] = 0
    return None


async def save_report(callback_context) -> Optional[types.Content]:
    report = callback_context.state.get("final_answer")
    if report:
        part = types.Part.from_bytes(data=report.encode(), mime_type="text/markdown")
        try:
            await callback_context.save_artifact("gemini_cli_report.md", part)
        except ValueError:
            pass
    return None


repo_preparer = LlmAgent(
    name="RepoPreparer",
    model=config.FAST_MODEL,
    instruction=prompts.PREPARER_INSTRUCTION,
    tools=[prepare_repository],
    output_key="repo_summary",
)

cli_executor = LlmAgent(
    name="CliExecutor",
    model=config.PRO_MODEL,
    instruction=prompts.EXECUTOR_INSTRUCTION,
    tools=[run_gemini_cli],
    output_key="draft",
)

critic = LlmAgent(
    name="Critic",
    model=config.FAST_MODEL,
    instruction=prompts.CRITIC_INSTRUCTION,
    tools=[exit_loop],
    output_key="critique",
    include_contents="none",
)

refinement_loop = LoopAgent(
    name="RefinementLoop",
    sub_agents=[cli_executor, critic],
    max_iterations=config.MAX_LOOP_ITERATIONS,
)

report_writer = LlmAgent(
    name="ReportWriter",
    model=config.FAST_MODEL,
    instruction=prompts.WRITER_INSTRUCTION,
    output_key="final_answer",
    include_contents="none",
    after_agent_callback=save_report,
)

repo_task_pipeline = SequentialAgent(
    name="RepoTaskPipeline",
    description=("Clones a GitHub repo, runs the Gemini CLI on it with a self-critique "
                 "loop, and returns a polished Markdown answer. Input: the repo URL "
                 "plus the task."),
    sub_agents=[repo_preparer, refinement_loop, report_writer],
    before_agent_callback=capture_task,
)

root_agent = LlmAgent(
    name="CodeNavigator",
    description="Software engineering assistant that uses the Gemini CLI as a tool.",
    model=config.FAST_MODEL,
    instruction=prompts.ROOT_INSTRUCTION,
    tools=[AgentTool(agent=repo_task_pipeline), gemini_cli_health],
)
