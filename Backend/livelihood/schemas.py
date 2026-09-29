"""Pydantic contracts shared between conversation, matching, location and API layers."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SkillLevel = Literal["basic", "intermediate", "advanced"]
Mobility = Literal["home_only", "within_village", "nearby_town", "district", "can_relocate"]
WorkMode = Literal["wage_employment", "self_employment", "either"]
AspirationTag = Literal["stable_income", "own_business", "higher_income", "flexible_hours", "skill_growth"]

MOBILITY_MAX_KM = {
    "home_only": 0.0,
    "within_village": 12.0,
    "nearby_town": 25.0,
    "district": 50.0,
    "can_relocate": 1000.0,
}

MOBILITY_LABELS = {
    "home_only": "Works from home only",
    "within_village": "Limited travel",
    "nearby_town": "Can travel to nearby town",
    "district": "Can travel within district",
    "can_relocate": "Willing to relocate",
}


def _drop_invalid(value, allowed: tuple):
    return value if value in allowed else None


class ExtractedSkill(BaseModel):
    label: str
    level: Optional[SkillLevel] = None

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, v):
        return _drop_invalid(v, ("basic", "intermediate", "advanced"))


class ExtractedFacts(BaseModel):
    """What the LLM (or the rule extractor) found in the latest turn. Every field is optional."""
    skills: List[ExtractedSkill] = Field(default_factory=list)
    experience: Optional[str] = None
    education: Optional[str] = None
    education_level: Optional[int] = None
    formal_training: Optional[bool] = None
    aspiration: Optional[str] = None
    aspiration_tags: List[AspirationTag] = Field(default_factory=list)
    mobility: Optional[Mobility] = None
    preferred_work: Optional[WorkMode] = None
    location: Optional[str] = None

    @field_validator("skills", mode="before")
    @classmethod
    def _skills(cls, v):
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if isinstance(item, ExtractedSkill):
                out.append(item)
            elif isinstance(item, str) and item.strip():
                out.append({"label": item.strip()})
            elif isinstance(item, dict) and str(item.get("label") or "").strip():
                out.append(item)
        return out

    @field_validator("aspiration_tags", mode="before")
    @classmethod
    def _tags(cls, v):
        allowed = ("stable_income", "own_business", "higher_income", "flexible_hours", "skill_growth")
        return [t for t in v if t in allowed] if isinstance(v, list) else []

    @field_validator("mobility", mode="before")
    @classmethod
    def _mobility(cls, v):
        return _drop_invalid(v, tuple(MOBILITY_MAX_KM))

    @field_validator("preferred_work", mode="before")
    @classmethod
    def _work(cls, v):
        return _drop_invalid(v, ("wage_employment", "self_employment", "either"))

    @field_validator("formal_training", mode="before")
    @classmethod
    def _bool(cls, v):
        return v if isinstance(v, bool) else None

    @field_validator("education_level", mode="before")
    @classmethod
    def _edu(cls, v):
        return v if isinstance(v, int) and 0 <= v <= 20 else None

    @field_validator("experience", "education", "aspiration", "location", mode="before")
    @classmethod
    def _text(cls, v):
        if not isinstance(v, str):
            return None
        v = v.strip()
        return v if v and v.lower() not in ("null", "none", "unknown", "n/a") else None


class LLMTurn(BaseModel):
    """Validated LLM output for a single conversation turn."""
    facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    reply: str = ""


class ProfileSkill(BaseModel):
    id: Optional[str] = None
    label: str
    level: Optional[SkillLevel] = None


class Location(BaseModel):
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str = "stated"


class BeneficiaryProfile(BaseModel):
    aspiration: Optional[str] = None
    aspiration_tags: List[AspirationTag] = Field(default_factory=list)
    skills: List[ProfileSkill] = Field(default_factory=list)
    experience: Optional[str] = None
    education: Optional[str] = None
    education_level: Optional[int] = None
    formal_training: Optional[bool] = None
    mobility: Optional[Mobility] = None
    preferred_work: Optional[WorkMode] = None
    location: Optional[Location] = None
    age: Optional[int] = None

    @property
    def skill_ids(self) -> List[str]:
        return [s.id for s in self.skills if s.id]

    @property
    def max_travel_km(self) -> Optional[float]:
        return MOBILITY_MAX_KM.get(self.mobility) if self.mobility else None


class ProfileField(BaseModel):
    key: str
    label: str
    value: str


class EligibilityCheck(BaseModel):
    rule_id: str
    status: Literal["pass", "fail", "unknown"]
    hard: bool
    label: str


class NearbyOpportunity(BaseModel):
    id: str
    type: str
    name: str
    area: str
    distance_km: Optional[float] = None
    duration_min: Optional[float] = None
    distance_source: str = "cached"
    source: str
    within_reach: bool = True


class ScoreBreakdown(BaseModel):
    skill: float
    eligibility: float
    training: float
    mobility: float
    opportunity: float
    aspiration: float


class PathwayStage(BaseModel):
    key: str
    label: str
    detail: Optional[str] = None


class PathwayMatch(BaseModel):
    pathway_id: str
    pathway: str
    fit_score: int
    skill_fit: Literal["Strong", "Moderate", "Weak"]
    eligibility: Literal["Eligible", "Eligible (to verify)", "Not eligible"]
    travel_fit: Literal["High", "Medium", "Low"]
    skill_gap: List[str]
    next_step: str
    outcome: str
    stages: List[PathwayStage]
    highlights: List[str]
    eligibility_checks: List[EligibilityCheck]
    opportunities: List[NearbyOpportunity]
    breakdown: ScoreBreakdown
    data_note: str = "Prototype knowledge base with illustrative programmes"


class MatchResult(BaseModel):
    best: Optional[PathwayMatch]
    alternatives: List[PathwayMatch]
