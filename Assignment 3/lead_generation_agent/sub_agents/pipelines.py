"""The two deep-research pipelines.

PatternDiscoveryPipeline:  CompanyFinder(search) -> CompanyFormatter(JSON)
                           -> CompanyResearchFanout(parallel x k) -> PatternSynthesizer(JSON)
LeadGenerationPipeline:    LeadFinder(search) -> LeadFormatter(JSON)
                           -> LeadAssessmentFanout(parallel x m) -> ReportWriter(markdown artifact)

Gemini cannot combine built-in google_search with a JSON output_schema in the
same call, so every search step is followed by a dedicated formatter step.
"""
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import google_search

from .. import config, prompts
from ..callbacks import save_report_artifact
from ..schemas import (CompanyList, CompanyResearch, IntentResult, LeadAssessment,
                       LeadList, PatternReport)
from .research_fanout import ResearchFanoutAgent

intent_extractor = LlmAgent(
    name="IntentExtractor",
    description="Extracts intent, country, industry and the k/m numbers from a user message.",
    model=config.FAST_MODEL,
    instruction=prompts.INTENT_INSTRUCTION,
    output_schema=IntentResult,
    output_key="intent_result",
)

# ---------------- Pattern discovery ----------------
company_finder = LlmAgent(
    name="CompanyFinder",
    model=config.RESEARCH_MODEL,
    instruction=prompts.COMPANY_FINDER_INSTRUCTION,
    tools=[google_search],
    output_key="company_finder_raw",
)

company_formatter = LlmAgent(
    name="CompanyFormatter",
    model=config.FAST_MODEL,
    instruction=prompts.COMPANY_FORMATTER_INSTRUCTION,
    output_schema=CompanyList,
    output_key="companies",
    include_contents="none",
)

company_research_fanout = ResearchFanoutAgent(
    name="CompanyResearchFanout",
    items_state_key="companies",
    items_field="companies",
    result_key_prefix="company_research",
    collected_state_key="company_research",
    research_instruction=prompts.company_research_prompt,
    output_schema=CompanyResearch,
    researcher_model=config.RESEARCH_MODEL,
    formatter_model=config.FAST_MODEL,
    researcher_tools=[google_search],
    max_items=config.MAX_K,
)

pattern_synthesizer = LlmAgent(
    name="PatternSynthesizer",
    model=config.RESEARCH_MODEL,
    instruction=prompts.PATTERN_SYNTH_INSTRUCTION,
    output_schema=PatternReport,
    output_key="discovered_patterns",
    include_contents="none",
)

pattern_discovery_pipeline = SequentialAgent(
    name="PatternDiscoveryPipeline",
    description=(
        "Finds k successful companies in the target market, researches each in "
        "parallel, and synthesises the success patterns they share."
    ),
    sub_agents=[company_finder, company_formatter, company_research_fanout, pattern_synthesizer],
)

# ---------------- Lead generation ----------------
lead_finder = LlmAgent(
    name="LeadFinder",
    model=config.RESEARCH_MODEL,
    instruction=prompts.LEAD_FINDER_INSTRUCTION,
    tools=[google_search],
    output_key="lead_finder_raw",
)

lead_formatter = LlmAgent(
    name="LeadFormatter",
    model=config.FAST_MODEL,
    instruction=prompts.LEAD_FORMATTER_INSTRUCTION,
    output_schema=LeadList,
    output_key="leads",
    include_contents="none",
)

lead_assessment_fanout = ResearchFanoutAgent(
    name="LeadAssessmentFanout",
    items_state_key="leads",
    items_field="leads",
    result_key_prefix="lead_assessment",
    collected_state_key="lead_research",
    research_instruction=prompts.lead_assessment_prompt,
    output_schema=LeadAssessment,
    researcher_model=config.RESEARCH_MODEL,
    formatter_model=config.FAST_MODEL,
    researcher_tools=[google_search],
    max_items=config.MAX_M,
)

report_writer = LlmAgent(
    name="ReportWriter",
    model=config.RESEARCH_MODEL,
    instruction=prompts.REPORT_INSTRUCTION,
    output_key="final_report",
    include_contents="none",
    after_agent_callback=save_report_artifact,
)

lead_generation_pipeline = SequentialAgent(
    name="LeadGenerationPipeline",
    description=(
        "Uses the discovered patterns to find m new prospects, assesses each in "
        "parallel, and writes a ranked lead report artifact."
    ),
    sub_agents=[lead_finder, lead_formatter, lead_assessment_fanout, report_writer],
)
