"""Data-driven, deterministic eligibility evaluation. The LLM never decides eligibility."""
from typing import List

from livelihood.schemas import BeneficiaryProfile, EligibilityCheck


def _field_value(profile: BeneficiaryProfile, field: str):
    if field == "skills":
        return profile.skill_ids
    return getattr(profile, field, None)


def _evaluate(op: str, actual, expected) -> str:
    if op == "has_any_skill":
        return "pass" if set(actual or []) & set(expected) else "fail"
    if actual is None:
        return "unknown"
    if op == "gte":
        return "pass" if actual >= expected else "fail"
    if op == "lte":
        return "pass" if actual <= expected else "fail"
    if op == "in":
        return "pass" if actual in expected else "fail"
    if op == "is_not":
        return "pass" if actual != expected else "fail"
    raise ValueError(f"Unknown eligibility operator: {op}")


def evaluate(pathway_id: str, profile: BeneficiaryProfile, rules: List[dict]) -> List[EligibilityCheck]:
    checks = []
    for rule in rules:
        applies = rule.get("applies_to", [])
        if "*" not in applies and pathway_id not in applies:
            continue
        status = _evaluate(rule["op"], _field_value(profile, rule["field"]), rule["value"])
        label = rule["fail_label"] if status == "fail" else rule["pass_label"]
        if status == "unknown":
            label = f"{rule['pass_label']} (to verify)"
        checks.append(EligibilityCheck(rule_id=rule["id"], status=status, hard=rule.get("hard", True), label=label))
    return checks


def verdict(checks: List[EligibilityCheck]) -> str:
    if any(c.hard and c.status == "fail" for c in checks):
        return "Not eligible"
    if any(c.hard and c.status == "unknown" for c in checks):
        return "Eligible (to verify)"
    return "Eligible"
