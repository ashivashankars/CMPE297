"""Root agent for (c): MCP-tools based software bug assistant.

Run:  adk web   (from 'Assignment 3', choose bug_assistant_agent)
The ticket MCP server is started automatically as a stdio subprocess.
"""
from google.adk.agents import LlmAgent

from . import config, prompts
from .tools import build_tools

root_agent = LlmAgent(
    name="BugBuddy",
    description="Triage and debugging assistant backed by MCP ticket tools, search and GitHub.",
    model=config.MODEL,
    instruction=prompts.INSTRUCTION,
    tools=build_tools(),
)
