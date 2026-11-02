"""Dynamic parallel research: the "deep" part of deep research.

ADK's ParallelAgent needs its sub-agents at construction time, but how many
companies we research is only known at runtime (k or m). ResearchFanoutAgent is
a custom BaseAgent that reads a list from session state, builds one
`research -> format` SequentialAgent per item, runs them all in a ParallelAgent,
then gathers the structured results back into a single state key.
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Callable

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import ConfigDict


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)[:40] or "item"


class ResearchFanoutAgent(BaseAgent):
    """Fan out one research pipeline per list item, then fan the results back in."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items_state_key: str            # e.g. "companies" (a dict holding a list)
    items_field: str                # e.g. "companies" (the list inside that dict)
    result_key_prefix: str          # per-item outputs: f"{prefix}_{i}"
    collected_state_key: str        # final list of results
    research_instruction: Callable[[dict, dict], str]  # (item, state) -> prompt
    output_schema: Any
    researcher_model: Any
    formatter_model: Any
    researcher_tools: list = []
    max_items: int = 10

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        container = ctx.session.state.get(self.items_state_key) or {}
        items = container.get(self.items_field, []) if isinstance(container, dict) else []
        items = items[: self.max_items]
        if not items:
            yield Event(
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text="Nothing to research.")]),
            )
            return

        state_snapshot = dict(ctx.session.state)
        pipelines = []
        for i, item in enumerate(items):
            # Instruction providers (callables) are NOT template-expanded by ADK,
            # so JSON with curly braces is safe to embed here.
            prompt = self.research_instruction(item, state_snapshot)
            researcher = LlmAgent(
                name=f"Researcher_{self.result_key_prefix}_{i}",
                model=self.researcher_model,
                instruction=lambda _ctx, p=prompt: p,
                tools=list(self.researcher_tools),
                output_key=f"{self.result_key_prefix}_raw_{i}",
            )
            raw_key = f"{self.result_key_prefix}_raw_{i}"
            formatter = LlmAgent(
                name=f"Formatter_{self.result_key_prefix}_{i}",
                model=self.formatter_model,
                instruction=lambda c, k=raw_key, it=json.dumps(item, default=str): (
                    "Convert the research notes below into the required JSON schema. "
                    "Do not invent facts; keep every URL you find in `sources`.\n\n"
                    f"SUBJECT: {it}\n\n"
                    f"RESEARCH NOTES:\n{c.state.get(k, '')}"
                ),
                output_schema=self.output_schema,
                output_key=f"{self.result_key_prefix}_{i}",
                include_contents="none",
            )
            pipelines.append(
                SequentialAgent(name=f"Pipeline_{self.result_key_prefix}_{i}",
                                sub_agents=[researcher, formatter])
            )

        fan_out = ParallelAgent(name=f"FanOut_{self.result_key_prefix}", sub_agents=pipelines)
        async for event in fan_out.run_async(ctx):
            yield event

        # Fan-in: collect each structured result into one list.
        results = []
        for i in range(len(items)):
            value = ctx.session.state.get(f"{self.result_key_prefix}_{i}")
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = {"summary": value, "is_valid": False}
            if value:
                results.append(value)

        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"Researched {len(results)} of {len(items)} items in parallel.")],
            ),
            actions=EventActions(state_delta={self.collected_state_key: results}),
        )
