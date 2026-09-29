"""Deterministic pathway matching. Every number here is computed in Python, never by the LLM."""
from typing import List, Optional

from knowledge.base import KnowledgeBase
from livelihood.schemas import (
    BeneficiaryProfile,
    MatchResult,
    NearbyOpportunity,
    PathwayMatch,
    PathwayStage,
    ScoreBreakdown,
)
from matching import eligibility

WEIGHTS = {"skill": 35, "eligibility": 15, "training": 10, "mobility": 20, "opportunity": 10, "aspiration": 10}
DEFAULT_MAX_TRAVEL_KM = 25.0


def _skill_score(pathway: dict, profile: BeneficiaryProfile, kb: KnowledgeBase) -> float:
    target_factor = kb.level_factors
    core = [s for s in profile.skills if s.id in pathway["core_skills"]]
    if core:
        best = max(
            (1.0 if pathway["target_level"] == "basic" else target_factor.get(s.level or "intermediate", 1.0))
            for s in core
        )
        return WEIGHTS["skill"] * best
    if any(s.id in pathway.get("related_skills", []) for s in profile.skills):
        return WEIGHTS["skill"] * 0.5
    return 0.0


def _skill_gaps(pathway: dict, profile: BeneficiaryProfile, kb: KnowledgeBase) -> tuple[List[str], bool]:
    """Returns (gaps, bridged_by_pathway_training)."""
    qual_id = pathway.get("required_qualification")
    if not qual_id:
        return [], True
    qual = kb.qualifications.get(qual_id, {})
    certifiable = set(qual.get("certifies_skills", [])) & set(profile.skill_ids)
    if certifiable and profile.formal_training is True:
        return [], True
    program = kb.programs.get(pathway.get("training_program") or "")
    if program:
        return list(program["bridges_gaps"]), True
    return [qual.get("label", qual_id)], False


def _training_score(gaps: List[str], bridged: bool) -> float:
    penalty = (2 if bridged else 5) * len(gaps)
    return max(0.0, WEIGHTS["training"] - penalty)


def _relevant(pathway: dict, opportunities: List[NearbyOpportunity], kind: str) -> List[NearbyOpportunity]:
    return sorted(
        (o for o in opportunities if o.type == kind and o.distance_km is not None),
        key=lambda o: o.distance_km,
    )


def _nearest(opps: List[NearbyOpportunity]) -> Optional[NearbyOpportunity]:
    return opps[0] if opps else None


def match_pathway(
    pathway: dict,
    profile: BeneficiaryProfile,
    opportunities: List[NearbyOpportunity],
    kb: KnowledgeBase,
) -> PathwayMatch:
    max_km = profile.max_travel_km if profile.max_travel_km is not None else DEFAULT_MAX_TRAVEL_KM

    skill = _skill_score(pathway, profile, kb)

    checks = eligibility.evaluate(pathway["id"], profile, kb.rules)
    verdict = eligibility.verdict(checks)
    elig = {"Eligible": 1.0, "Eligible (to verify)": 0.8, "Not eligible": 0.0}[verdict] * WEIGHTS["eligibility"]

    gaps, bridged = _skill_gaps(pathway, profile, kb)
    training = _training_score(gaps, bridged)

    program = kb.programs.get(pathway.get("training_program") or "")
    training_site = _nearest(_relevant(pathway, opportunities, "training_centre")) if program else None
    outcome_sites = sorted(
        (o for t in pathway["opportunity_types"] for o in _relevant(pathway, opportunities, t)),
        key=lambda o: o.distance_km,
    )
    outcome_site = _nearest(outcome_sites)

    travel_points = [o.distance_km for o in (training_site, outcome_site) if o]
    if not travel_points:
        mobility = WEIGHTS["mobility"] * 0.5
    else:
        required_km = max(travel_points)
        if required_km <= max_km:
            mobility = WEIGHTS["mobility"]
        elif required_km <= max_km * 1.5:
            mobility = WEIGHTS["mobility"] * 0.5
        else:
            mobility = 0.0

    reachable = [o for o in outcome_sites if o.distance_km <= max_km]
    opportunity = WEIGHTS["opportunity"] * (1.0 if len(reachable) >= 2 else 0.7 if reachable else 0.0)

    if profile.aspiration_tags:
        overlap = len(set(profile.aspiration_tags) & set(pathway["outcome_tags"]))
        aspiration = WEIGHTS["aspiration"] * overlap / len(profile.aspiration_tags)
    else:
        aspiration = WEIGHTS["aspiration"] * 0.5
    if profile.preferred_work in ("wage_employment", "self_employment") and profile.preferred_work not in pathway["work_modes"]:
        aspiration = max(0.0, aspiration - 5)

    breakdown = ScoreBreakdown(
        skill=round(skill, 2), eligibility=round(elig, 2), training=round(training, 2),
        mobility=round(mobility, 2), opportunity=round(opportunity, 2), aspiration=round(aspiration, 2),
    )
    fit_score = int(round(skill + elig + training + mobility + opportunity + aspiration))

    skill_ratio = skill / WEIGHTS["skill"]
    skill_fit = "Strong" if skill_ratio >= 0.8 else "Moderate" if skill_ratio >= 0.5 else "Weak"
    travel_fit = "High" if mobility == WEIGHTS["mobility"] else "Medium" if mobility > 0 else "Low"

    highlights = []
    if skill_fit == "Strong":
        highlights.append("Strong skill match")
    if verdict != "Not eligible":
        highlights.append("Eligible" if verdict == "Eligible" else "Eligible, details to verify")
    if reachable:
        highlights.append("Local opportunity")
    if travel_fit == "High":
        highlights.append("Low travel requirement")

    stage_details = {
        "training": f"{program['label']} · {program['duration']}" if program else None,
        "opportunity": f"{outcome_site.name} · {outcome_site.distance_km:g} km" if outcome_site else None,
        "outcome": pathway["outcome_label"],
    }
    stages = [PathwayStage(key=s["key"], label=s["label"], detail=stage_details.get(s["key"])) for s in pathway["stages"]]

    shown = [o for o in (training_site, *outcome_sites[:2]) if o]
    for o in shown:
        o.within_reach = o.distance_km <= max_km

    return PathwayMatch(
        pathway_id=pathway["id"],
        pathway=pathway["name"],
        fit_score=fit_score,
        skill_fit=skill_fit,
        eligibility=verdict,
        travel_fit=travel_fit,
        skill_gap=gaps,
        next_step=program["label"] if (program and gaps) else pathway["stages"][0]["label"],
        outcome=pathway["outcome_label"],
        stages=stages,
        highlights=highlights,
        eligibility_checks=checks,
        opportunities=shown,
        breakdown=breakdown,
    )


def match(profile: BeneficiaryProfile, opportunities: List[NearbyOpportunity], kb: KnowledgeBase) -> MatchResult:
    order = {p["id"]: i for i, p in enumerate(kb.pathways)}
    results = [
        match_pathway(p, profile, [o.model_copy() for o in opportunities], kb)
        for p in kb.pathways
    ]
    viable = [r for r in results if r.eligibility != "Not eligible" and r.breakdown.skill > 0]
    viable.sort(key=lambda r: (-r.fit_score, order[r.pathway_id]))
    return MatchResult(best=viable[0] if viable else None, alternatives=viable[1:3])
