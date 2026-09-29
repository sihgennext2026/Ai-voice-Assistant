"""One beneficiary conversation: VOICE -> UNDERSTAND -> PROFILE -> MATCH -> PATHWAY.

The LLM extracts facts and phrases replies. Python decides what is missing, when to match,
eligibility, scores and the recommended pathway.
"""
import json
import logging
import threading
import time
from typing import Callable, List, Optional

from pydantic import BaseModel

from config import Settings
from knowledge.base import KnowledgeBase
from livelihood import profile as profile_ops
from livelihood import rule_extractor
from livelihood.llm import LLMClient
from livelihood.prompts import (
    EXPLAIN_SYSTEM_PROMPT,
    FOLLOW_UP_SYSTEM_PROMPT,
    TURN_SYSTEM_PROMPT,
    TURN_USER_TEMPLATE,
)
from livelihood.schemas import BeneficiaryProfile, LLMTurn, Location, MatchResult, PathwayMatch
from location.service import LocationService
from matching import engine

logger = logging.getLogger(__name__)

Emit = Callable[[dict], None]
Speak = Callable[[str], None]

ANALYSIS_STEPS = [
    ("skills", "Understanding skills"),
    ("eligibility", "Checking eligibility"),
    ("accessibility", "Evaluating accessibility"),
    ("opportunities", "Finding opportunities"),
]
STEP_PACING_S = 0.8


class _Reply(BaseModel):
    reply: str = ""


def summary_line(match: PathwayMatch, prof: BeneficiaryProfile, short: bool = False) -> str:
    opportunity_stage = next((s for s in match.stages if s.key == "opportunity"), None)
    follow = f", followed by a {opportunity_stage.label.lower()}" if opportunity_stage else ""
    travel = " while keeping your travel requirement low" if match.travel_fit == "High" and prof.mobility in profile_ops.LOCAL_MOBILITY else ""
    first = f"Your best-fit pathway is {match.pathway.lower()}{follow}."
    return first if short else f"{first} It builds on your existing skills{travel}."


class LivelihoodSession:
    def __init__(self, settings: Settings, kb: KnowledgeBase, llm: LLMClient, location: LocationService):
        self.settings = settings
        self.kb = kb
        self.llm = llm
        self.location = location
        self._lock = threading.Lock()
        self.step_pacing_s = STEP_PACING_S
        self.reset()

    # ── state ────────────────────────────────────────────────────────────────
    def reset(self):
        self.profile = BeneficiaryProfile()
        self.transcript: List[dict] = []
        self.last_slot: Optional[str] = None
        self.follow_ups = 0
        self.phase = "conversation"
        self.result: Optional[MatchResult] = None
        self.analysis: List[dict] = []
        case = self.kb.demo_cases.get(self.settings.demo_case_id) if self.settings.demo_mode else None
        self.greeting = (case or {}).get(
            "greeting", "Namaste. Tell me a little about yourself: what work do you know, and what are you hoping for?"
        )
        if case:
            registered = case.get("registered", {})
            self.profile.age = registered.get("age")
            if registered.get("location"):
                self.profile.location = Location(**registered["location"])

    def snapshot(self) -> dict:
        return {
            "type": "session_state",
            "phase": self.phase,
            "demo_mode": self.settings.demo_mode,
            "greeting": self.greeting,
            "transcript": self.transcript,
            "profile": [f.model_dump() for f in profile_ops.display_fields(self.profile)],
            "analysis": self.analysis,
            "pathway": self._pathway_payload(),
        }

    def _pathway_payload(self) -> Optional[dict]:
        if not self.result or not self.result.best:
            return None
        return {
            "best": self.result.best.model_dump(),
            "alternatives": [a.model_dump(include={"pathway", "fit_score", "travel_fit"}) for a in self.result.alternatives],
        }

    def _say(self, text: str, emit: Emit, speak: Speak):
        self.transcript.append({"role": "assistant", "text": text})
        emit({"type": "transcript", "role": "assistant", "text": text})
        speak(text)

    # ── turn handling ────────────────────────────────────────────────────────
    def handle_turn(self, text: str, emit: Emit, speak: Speak):
        text = text.strip()
        if not text:
            return
        with self._lock:
            self.transcript.append({"role": "user", "text": text})
            emit({"type": "transcript", "role": "user", "text": text})
            emit({"type": "status", "status": "understanding"})
            if self.phase == "pathway":
                self._answer_follow_up(text, emit, speak)
            else:
                self._profile_turn(text, emit, speak)

    def _profile_turn(self, text: str, emit: Emit, speak: Speak):
        if self.settings.demo_mode:
            self._demo_profile_turn(text, emit, speak)
        else:
            self._live_profile_turn(text, emit, speak)

    def _live_profile_turn(self, text: str, emit: Emit, speak: Speak):
        """LLM understands and phrases the reply; rules fill anything it missed."""
        rule_facts = rule_extractor.extract(text, self.kb, self.last_slot)
        llm_turn = self.llm.structured(*self._turn_prompt(text), LLMTurn) if self.llm.available else None
        facts = profile_ops.merge_facts(llm_turn.facts, rule_facts) if llm_turn else rule_facts
        self._apply(facts, emit, always_emit=True)

        emit({"type": "status", "status": "responding"})
        if profile_ops.is_ready_for_matching(self.profile):
            self._say(profile_ops.closing_line(self.profile), emit, speak)
            self._run_analysis(emit, speak)
            return
        reply = llm_turn.reply.strip() if llm_turn else ""
        if not reply or "?" not in reply or len(reply) > 220:
            reply = None
        self._ask_next(emit, speak, reply)

    def _demo_profile_turn(self, text: str, emit: Emit, speak: Speak):
        """Deterministic: rules decide the profile and the reply is templated. The LLM still runs every
        turn, in parallel with speech, and may only fill fields that are still unknown."""
        llm_out: dict = {}
        worker = None
        if self.llm.available:
            prompt = self._turn_prompt(text)
            worker = threading.Thread(
                target=lambda: llm_out.update(turn=self.llm.structured(*prompt, LLMTurn)), daemon=True
            )
            worker.start()

        self._apply(rule_extractor.extract(text, self.kb, self.last_slot), emit, always_emit=True)
        ready = profile_ops.is_ready_for_matching(self.profile)
        emit({"type": "status", "status": "responding"})
        if ready:
            self._say(profile_ops.closing_line(self.profile), emit, speak)
        else:
            self._ask_next(emit, speak, None)

        if worker:
            worker.join(timeout=self.settings.llm_timeout_s)
            turn = llm_out.get("turn")
            if turn:
                self._apply(profile_ops.unknown_only(turn.facts, self.profile), emit, always_emit=False)
        if ready:
            self._run_analysis(emit, speak)

    def _apply(self, facts, emit: Emit, always_emit: bool):
        if self.profile.location and self.profile.location.source == "registered case record":
            facts.location = None
        changed = profile_ops.apply_facts(self.profile, facts, self.kb)
        if changed or always_emit:
            emit({
                "type": "profile_update",
                "profile": [f.model_dump() for f in profile_ops.display_fields(self.profile)],
                "changed": changed,
                "complete": profile_ops.is_ready_for_matching(self.profile),
            })

    def _ask_next(self, emit: Emit, speak: Speak, reply: Optional[str]):
        slot = profile_ops.next_slot(self.profile)
        if not reply:
            reply = profile_ops.question_for(slot, self.profile, first_follow_up=self.follow_ups == 0)
        self.follow_ups += 1
        self.last_slot = slot
        self._say(reply, emit, speak)

    def _turn_prompt(self, text: str) -> tuple[str, str]:
        known = self.profile.model_dump(exclude={"age"}, exclude_none=True)
        system = TURN_SYSTEM_PROMPT.replace("{missing_slots}", ", ".join(profile_ops.missing_slots(self.profile)) or "none")
        user = TURN_USER_TEMPLATE.format(
            profile_json=json.dumps(known, ensure_ascii=False),
            last_question=self._last_assistant_text() or "(none, this is the first message)",
            utterance=text.replace('"', "'"),
        )
        return system, user

    def _last_assistant_text(self) -> Optional[str]:
        for msg in reversed(self.transcript):
            if msg["role"] == "assistant":
                return msg["text"]
        return None

    # ── deterministic analysis ───────────────────────────────────────────────
    def _run_analysis(self, emit: Emit, speak: Speak):
        self.phase = "analysing"
        self.analysis = []
        emit({"type": "status", "status": "analysing"})
        emit({"type": "analysis_start", "steps": [{"key": k, "label": l} for k, l in ANALYSIS_STEPS]})

        try:
            opportunities = self.location.nearby_opportunities(self.profile.location)
        except Exception:
            logger.exception("Location lookup failed; matching without opportunities")
            opportunities = []
        result = engine.match(self.profile, opportunities, self.kb)
        best = result.best

        details = self._step_details(best, opportunities)
        for key, label in ANALYSIS_STEPS:
            emit({"type": "analysis_step", "key": key, "state": "active"})
            time.sleep(self.step_pacing_s)
            step = {"key": key, "label": label, "state": "done", "detail": details.get(key)}
            self.analysis.append(step)
            emit({"type": "analysis_step", **step})

        if best is None:
            self.phase = "conversation"
            self.profile.skills = []
            self.last_slot = "skills"
            emit({"type": "profile_update", "profile": [f.model_dump() for f in profile_ops.display_fields(self.profile)],
                  "changed": ["skills"], "complete": False})
            self._say("I couldn't find a suitable pathway from that yet. What other kinds of work have you done?", emit, speak)
            return

        self.result = result
        self.phase = "pathway"
        emit({"type": "pathway", **self._pathway_payload()})
        self._say(self._explain(best), emit, speak)

    def _step_details(self, best: Optional[PathwayMatch], opportunities) -> dict:
        skills = ", ".join(
            f"{s.level} {s.label.lower()}" if s.level else s.label.lower() for s in self.profile.skills
        )
        if not best:
            return {"skills": skills.capitalize()}
        passed = sum(1 for c in best.eligibility_checks if c.status == "pass")
        reach = self.profile.max_travel_km
        in_reach = [o for o in best.opportunities if o.within_reach]
        return {
            "skills": skills.capitalize(),
            "eligibility": f"{passed} of {len(best.eligibility_checks)} criteria met",
            "accessibility": f"Within {reach:g} km of home" if reach else "Travel range noted",
            "opportunities": f"{len(in_reach)} within reach",
        }

    def _explain(self, best: PathwayMatch) -> str:
        template = summary_line(best, self.profile, short=self.settings.demo_mode)
        if self.settings.demo_mode or not self.llm.available:
            return template
        facts = best.model_dump(include={"pathway", "outcome", "highlights", "skill_gap", "next_step"})
        facts["opportunities"] = [f"{o.name} ({o.distance_km:g} km)" for o in best.opportunities]
        out = self.llm.structured(EXPLAIN_SYSTEM_PROMPT, json.dumps(facts, ensure_ascii=False), _Reply)
        reply = out.reply.strip() if out else ""
        return reply if 20 <= len(reply) <= 300 else template

    def _answer_follow_up(self, text: str, emit: Emit, speak: Speak):
        best = self.result.best
        fallback = f"Your next step is {best.next_step.lower()}. A local counsellor can help you enrol."
        reply = ""
        if self.llm.available:
            context = json.dumps(best.model_dump(exclude={"breakdown", "eligibility_checks"}), ensure_ascii=False)
            out = self.llm.structured(FOLLOW_UP_SYSTEM_PROMPT, f"Recommendation: {context}\nQuestion: {text}", _Reply)
            reply = out.reply.strip() if out else ""
        emit({"type": "status", "status": "responding"})
        self._say(reply if 5 <= len(reply) <= 300 else fallback, emit, speak)


class _NoLLM:
    available = False
    provider_names: List[str] = []

    def structured(self, *args, **kwargs):
        return None


def demo_script_lines(settings: Settings, kb: KnowledgeBase, location: LocationService) -> List[str]:
    """Dry-runs the demo case (no LLM, no pacing) and returns every line the guide will speak."""
    case = kb.demo_cases.get(settings.demo_case_id)
    if not settings.demo_mode or not case:
        return []
    dry = LivelihoodSession(settings, kb, _NoLLM(), location)
    dry.step_pacing_s = 0
    spoken: List[str] = []
    for utterance in case.get("sample_utterances", []):
        dry.handle_turn(utterance, lambda _: None, spoken.append)
    return spoken
