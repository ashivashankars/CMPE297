"""Root agent for (a) the deep-research lead generation agent.

Run:  adk web            (from the 'Assignment 3' folder, pick lead_generation_agent)
      adk run lead_generation_agent
"""
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from . import config, prompts
from .callbacks import init_state, update_stage
from .sub_agents.pipelines import (intent_extractor, lead_generation_pipeline,
                                   pattern_discovery_pipeline)
from .tools import get_research_status, set_research_parameters

root_agent = LlmAgent(
    name="LeadScout",
    description="Deep-research agent that discovers success patterns and finds matching B2B leads.",
    model=config.FAST_MODEL,
    instruction=prompts.ROOT_INSTRUCTION,
    tools=[
        AgentTool(agent=intent_extractor),
        AgentTool(agent=pattern_discovery_pipeline),
        AgentTool(agent=lead_generation_pipeline),
        set_research_parameters,
        get_research_status,
    ],
    before_agent_callback=init_state,
    after_tool_callback=update_stage,
)
