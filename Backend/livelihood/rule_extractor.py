"""Deterministic keyword extraction. Runs on every turn so the flow survives LLM failures."""
import re
from typing import Optional

from knowledge.base import KnowledgeBase
from livelihood.schemas import ExtractedFacts, ExtractedSkill


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def extract(text: str, kb: KnowledgeBase, last_asked_slot: Optional[str] = None) -> ExtractedFacts:
    t = " " + text.lower().replace("’", "'") + " "
    facts = ExtractedFacts()

    skill_id = kb.resolve_skill(t)
    if skill_id:
        level = None
        if _has(t, r"\bbasic\b", r"\ba little\b", r"\bsome\b", r"\bbeginner\b"):
            level = "basic"
        elif _has(t, r"\badvanced\b", r"\bexpert\b", r"\bmaster\b", r"\bvery good at\b"):
            level = "advanced"
        facts.skills = [ExtractedSkill(label=kb.skill_label(skill_id), level=level)]

    tags = []
    if _has(t, r"\bstable\b", r"\bsteady\b", r"\bregular (income|salary|work)\b", r"\bfixed income\b", r"\bmonthly salary\b"):
        tags.append("stable_income")
    if _has(t, r"\bown business\b", r"\bstart a business\b", r"\bmy own (shop|work|business)\b"):
        tags.append("own_business")
    if _has(t, r"\bearn more\b", r"\bmore money\b", r"\bhigher income\b", r"\bbetter pay\b"):
        tags.append("higher_income")
    if _has(t, r"\bflexible\b", r"\bpart[- ]time\b"):
        tags.append("flexible_hours")
    facts.aspiration_tags = tags
    if "stable_income" in tags:
        facts.aspiration = "stable income"

    if _has(t, r"\bonly (work )?from home\b", r"\bcan't leave (my )?home\b", r"\bcannot leave (my )?home\b"):
        facts.mobility = "home_only"
    elif _has(t, r"\bcan'?t travel\b", r"\bcannot travel\b", r"\bcan not travel\b", r"\bnot travel far\b",
              r"\bnear my (village|home)\b", r"\bclose to (my )?home\b", r"\bstay in (my )?village\b",
              r"\bwithin (my|the) village\b", r"\bnot (able|willing) to travel\b"):
        facts.mobility = "within_village"
    elif _has(t, r"\brelocate\b", r"\bmove to (the|a) city\b", r"\bmigrate\b"):
        facts.mobility = "can_relocate"
    elif _has(t, r"\bcan travel\b", r"\bready to travel\b", r"\bnearby town\b"):
        facts.mobility = "nearby_town"

    self_taught = _has(t, r"\blearn(ed|t) (it )?(through|by|from) (experience|practice|doing|my (mother|family|mom))",
                       r"\bself[- ]taught\b", r"\bon my own\b")
    no_training = _has(t, r"\bno formal\b", r"\bnot formal(ly)?\b", r"\bno (training|certificate|certification|course)\b",
                       r"\bnever (had|did|took|done) (any )?(training|course)\b", r"\bnot certified\b")
    has_training = _has(t, r"\b(i have|i did|i completed|got) (a |an )?(certificate|certification|diploma|course)\b",
                        r"\b(i am|i'm) certified\b", r"\biti\b")
    if no_training or self_taught:
        facts.formal_training = False
    elif has_training:
        facts.formal_training = True
    elif last_asked_slot == "formal_training":
        if re.match(r"^\s*(no|nope|nah|not really)\b", t):
            facts.formal_training = False
        elif re.match(r"^\s*(yes|yeah|haan|ha)\b", t):
            facts.formal_training = True

    years = re.search(r"\b(\d{1,2})\s+years?\b", t)
    if years:
        facts.experience = f"{years.group(1)} years' practical experience"
    elif self_taught:
        facts.experience = "Practical, self-taught"
    elif _has(t, r"\bexperience\b"):
        facts.experience = "Practical experience"

    std = re.search(r"\b(?:class|standard|std)\s*(\d{1,2})\b|\b(\d{1,2})(?:th|st|nd|rd)\s+(?:pass|class|standard)\b", t)
    if std:
        level = int(std.group(1) or std.group(2))
        facts.education_level = level
        facts.education = f"Class {level}"
    elif _has(t, r"\bgraduat(e|ed|ion)\b"):
        facts.education_level, facts.education = 15, "Graduate"
    elif _has(t, r"\bnever went to school\b", r"\bno schooling\b", r"\billiterate\b"):
        facts.education_level, facts.education = 0, "No formal schooling"

    place = re.search(
        r"\b(?:i live in|i stay in|i am from|i'm from|my village is|village called|town called)\s+"
        r"([a-z][a-z]+(?:\s(?!and\b|but\b|village\b|town\b)[a-z]+){0,2})",
        t,
    )
    if place:
        facts.location = place.group(1).title()
    elif last_asked_slot == "location" and len(t.split()) <= 4:
        facts.location = re.sub(r"[^a-z ]", "", t).strip().title() or None

    return facts
