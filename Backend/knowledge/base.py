"""Loads the structured local knowledge layer from knowledge/data/*.json."""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class KnowledgeBase:
    def __init__(self):
        skills = _load("skills.json")
        self.skills: List[dict] = skills.get("skills", [])
        self.level_factors: Dict[str, float] = skills.get("levels", {})
        self.qualifications = {q["id"]: q for q in _load("qualifications.json").get("qualifications", [])}
        self.programs = {p["id"]: p for p in _load("training_programs.json").get("programs", [])}
        self.rules: List[dict] = _load("eligibility_rules.json").get("rules", [])
        self.job_roles = {j["id"]: j for j in _load("job_roles.json").get("job_roles", [])}
        self.pathways: List[dict] = _load("pathways.json").get("pathways", [])
        self.opportunities: List[dict] = _load("opportunities.json").get("opportunities", [])
        self.location_cache: dict = _load("location_cache.json")
        self.demo_cases: Dict[str, dict] = _load("demo_cases.json").get("cases", {})
        self._skill_by_id = {s["id"]: s for s in self.skills}

    def skill_label(self, skill_id: str) -> str:
        skill = self._skill_by_id.get(skill_id)
        return skill["label"] if skill else skill_id

    def resolve_skill(self, text: str) -> Optional[str]:
        """Map free text ('basic tailoring', 'silai') to a canonical skill id."""
        lowered = text.lower()
        for skill in self.skills:
            for alias in skill.get("aliases", []):
                if re.search(rf"\b{re.escape(alias)}\b", lowered):
                    return skill["id"]
        return None


@lru_cache
def get_knowledge() -> KnowledgeBase:
    return KnowledgeBase()
