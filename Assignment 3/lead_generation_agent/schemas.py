"""Pydantic contracts between pipeline stages. Research agents (which use
google_search) produce free text; a formatter agent then forces that text into
one of these schemas so downstream code never has to parse prose."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    intent: Literal["find_patterns", "find_leads", "chitchat", "other"] = Field(
        description="What the user wants right now."
    )
    country: Optional[str] = Field(None, description="Target country, if mentioned.")
    industry: Optional[str] = Field(None, description="Target industry, if mentioned.")
    k: Optional[int] = Field(None, description="Companies to analyse, if the user gave a number.")
    m: Optional[int] = Field(None, description="Leads to find, if the user gave a number.")


class Company(BaseModel):
    company_name: str
    website: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    why_selected: str = Field(description="Why this company counts as a success story.")


class CompanyList(BaseModel):
    companies: List[Company]


class CompanyResearch(BaseModel):
    company_name: str
    is_valid: bool = Field(description="False if the company is defunct, off-target or unverifiable.")
    funding_signals: List[str] = []
    hiring_signals: List[str] = []
    technology_signals: List[str] = []
    growth_signals: List[str] = []
    summary: str
    sources: List[str] = Field(default_factory=list, description="URLs that back the findings.")


class Pattern(BaseModel):
    name: str
    description: str
    signal_type: Literal["funding", "hiring", "technology", "growth", "other"]
    evidence_companies: List[str]
    weight: float = Field(ge=0, le=1, description="How strongly the pattern predicts success.")


class PatternReport(BaseModel):
    patterns: List[Pattern]
    summary: str


class Lead(BaseModel):
    company_name: str
    website: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    rationale: str = Field(description="Which discovered patterns this company appears to match.")


class LeadList(BaseModel):
    leads: List[Lead]


class LeadAssessment(BaseModel):
    company_name: str
    is_valid: bool
    matched_patterns: List[str] = []
    fit_score: int = Field(ge=0, le=100, description="0-100 fit against the discovered patterns.")
    key_signals: List[str] = []
    recommended_outreach_angle: str = ""
    summary: str
    sources: List[str] = []
