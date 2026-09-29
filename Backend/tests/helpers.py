from config import get_settings
from knowledge.base import get_knowledge
from livelihood.schemas import BeneficiaryProfile, Location, ProfileSkill

KB = get_knowledge()
SANGANER = Location(name="Sanganer, Jaipur", lat=26.8146217, lon=75.7731874, source="registered case record")


def settings(**overrides):
    return get_settings().model_copy(update=overrides)


def demo_profile(**overrides) -> BeneficiaryProfile:
    data = dict(
        aspiration="stable income",
        aspiration_tags=["stable_income"],
        skills=[ProfileSkill(id="tailoring", label="Tailoring", level="basic")],
        experience="Practical, self-taught",
        formal_training=False,
        mobility="within_village",
        location=SANGANER.model_copy(),
        age=32,
    )
    data.update(overrides)
    return BeneficiaryProfile(**data)


class NoLLM:
    available = False
    provider_names = []

    def structured(self, *args, **kwargs):
        return None


class ScriptedLLM:
    """Returns pre-baked payloads (validated by the caller's schema) in order."""
    available = True
    provider_names = ["scripted"]

    def __init__(self, *payloads):
        self.payloads = list(payloads)

    def structured(self, system, user, schema):
        if not self.payloads:
            return None
        payload = self.payloads.pop(0)
        return None if payload is None else schema.model_validate(payload)
