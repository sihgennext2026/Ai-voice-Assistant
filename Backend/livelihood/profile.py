"""Profile building: merge extracted facts, normalise against the knowledge base, decide what to ask next."""
from typing import List, Optional

from knowledge.base import KnowledgeBase
from livelihood.schemas import (
    MOBILITY_LABELS,
    BeneficiaryProfile,
    ExtractedFacts,
    Location,
    ProfileField,
    ProfileSkill,
)

ASPIRATION_LABELS = {
    "stable_income": "Stable income",
    "own_business": "Own business",
    "higher_income": "Higher income",
    "flexible_hours": "Flexible working hours",
    "skill_growth": "Skill growth",
}

WORK_LABELS = {
    "wage_employment": "Salaried employment",
    "self_employment": "Self-employment",
    "either": "Employment or enterprise",
}

LOCAL_MOBILITY = ("home_only", "within_village")


def merge_facts(primary: ExtractedFacts, fallback: ExtractedFacts) -> ExtractedFacts:
    """Primary (LLM) wins; fallback (rules) fills anything the primary missed."""
    data = primary.model_dump()
    for key, value in fallback.model_dump().items():
        if data.get(key) in (None, [], ""):
            data[key] = value
    return ExtractedFacts.model_validate(data)


def unknown_only(facts: ExtractedFacts, profile: BeneficiaryProfile) -> ExtractedFacts:
    """Drops facts for fields the profile already knows, so they cannot be overwritten."""
    data = facts.model_dump()
    known = {
        "skills": bool(profile.skills),
        "aspiration": bool(profile.aspiration),
        "aspiration_tags": bool(profile.aspiration_tags),
        "location": profile.location is not None,
    }
    for key in data:
        is_known = known.get(key, getattr(profile, key, None) is not None)
        if is_known:
            data[key] = [] if isinstance(data[key], list) else None
    return ExtractedFacts.model_validate(data)


def apply_facts(profile: BeneficiaryProfile, facts: ExtractedFacts, kb: KnowledgeBase) -> List[str]:
    """Mutates profile with new facts. Returns the list of profile keys that changed."""
    changed: List[str] = []

    for skill in facts.skills:
        skill_id = kb.resolve_skill(skill.label)
        existing = next(
            (s for s in profile.skills if (skill_id and s.id == skill_id) or s.label.lower() == skill.label.lower()),
            None,
        )
        if existing:
            if skill.level and existing.level != skill.level:
                existing.level = skill.level
                changed.append("skills")
            continue
        label = kb.skill_label(skill_id) if skill_id else skill.label.strip().capitalize()
        profile.skills.append(ProfileSkill(id=skill_id, label=label, level=skill.level))
        changed.append("skills")

    for tag in facts.aspiration_tags:
        if tag not in profile.aspiration_tags:
            profile.aspiration_tags.append(tag)
            changed.append("aspiration")

    scalar_fields = ["aspiration", "experience", "education", "education_level",
                     "formal_training", "mobility", "preferred_work"]
    for field in scalar_fields:
        value = getattr(facts, field)
        if value is not None and getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)

    if facts.location and (not profile.location or profile.location.name != facts.location):
        profile.location = Location(name=facts.location, source="stated")
        changed.append("location")

    return sorted(set(changed))


def missing_slots(profile: BeneficiaryProfile) -> List[str]:
    missing = []
    if not profile.skills:
        missing.append("skills")
    if not profile.aspiration and not profile.aspiration_tags:
        missing.append("aspiration")
    if profile.formal_training is None:
        missing.append("formal_training")
    if profile.mobility is None:
        missing.append("mobility")
    if profile.location is None:
        missing.append("location")
    return missing


def next_slot(profile: BeneficiaryProfile) -> Optional[str]:
    missing = missing_slots(profile)
    return missing[0] if missing else None


def is_ready_for_matching(profile: BeneficiaryProfile) -> bool:
    return not missing_slots(profile)


def primary_skill_label(profile: BeneficiaryProfile) -> str:
    return profile.skills[0].label.lower() if profile.skills else "skills"


def question_for(slot: str, profile: BeneficiaryProfile, first_follow_up: bool) -> str:
    """Deterministic follow-up phrasing, used in DEMO_MODE and whenever the LLM is unavailable."""
    ack = "I understand. " if first_follow_up else "Thank you. "
    questions = {
        "skills": "What kind of work do you know how to do, or have done before?",
        "aspiration": "What are you hoping for: a steady income, your own business, or something else?",
        "formal_training": f"Do you have any formal {primary_skill_label(profile)} training?",
        "mobility": "How far are you able to travel for training or work?",
        "location": "Which village or town do you live in?",
    }
    return ack + questions[slot]


def closing_line(profile: BeneficiaryProfile) -> str:
    if profile.mobility in LOCAL_MOBILITY:
        return "Got it. I'll find a pathway that builds on your skills and keeps the opportunity local."
    return "Got it. I'll find the pathway that best builds on your skills."


def goal_label(profile: BeneficiaryProfile) -> Optional[str]:
    if profile.aspiration_tags:
        label = ASPIRATION_LABELS[profile.aspiration_tags[0]]
        if profile.aspiration_tags[0] == "stable_income" and profile.mobility in LOCAL_MOBILITY:
            return "Stable local income"
        return label
    if profile.aspiration:
        return profile.aspiration[:1].upper() + profile.aspiration[1:]
    return None


def display_fields(profile: BeneficiaryProfile) -> List[ProfileField]:
    """Ordered, human-readable profile. Only includes fields that are known."""
    fields: List[ProfileField] = []

    def add(key: str, label: str, value: Optional[str]):
        if value:
            fields.append(ProfileField(key=key, label=label, value=value))

    add("aspiration", "Goal", goal_label(profile))
    if profile.skills:
        add("skills", "Skills", ", ".join(
            f"{s.level.capitalize()} {s.label.lower()}" if s.level else s.label for s in profile.skills
        ))
    if profile.experience:
        add("experience", "Experience", profile.experience[:1].upper() + profile.experience[1:])
    add("education", "Education", profile.education)
    if profile.formal_training is not None:
        add("formal_training", "Training", "Formally trained" if profile.formal_training else "No formal certification")
    if profile.mobility:
        add("mobility", "Constraint", MOBILITY_LABELS[profile.mobility])
    if profile.preferred_work:
        add("preferred_work", "Preferred work", WORK_LABELS[profile.preferred_work])
    elif profile.mobility in LOCAL_MOBILITY:
        add("preferred_work", "Preferred work", "Close to home")
    if profile.location:
        add("location", "Location", profile.location.name)
    return fields
