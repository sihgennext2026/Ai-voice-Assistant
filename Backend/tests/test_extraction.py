import unittest

from livelihood import rule_extractor
from livelihood.llm import parse_json_object
from livelihood.schemas import ExtractedFacts, LLMTurn
from tests.helpers import KB

UTTERANCE_1 = "I know basic tailoring, but I want a stable income. I also can't travel far from my village."
UTTERANCE_2 = "No, I learned it through experience."


class LLMOutputValidationTests(unittest.TestCase):
    def test_parses_json_inside_code_fence_and_prose(self):
        self.assertEqual(parse_json_object('```json\n{"reply": "hi"}\n```'), {"reply": "hi"})
        self.assertEqual(parse_json_object('Sure! {"reply": "hi"} hope that helps'), {"reply": "hi"})

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_json_object("I cannot answer that"))
        self.assertIsNone(parse_json_object('["a list"]'))
        self.assertIsNone(parse_json_object(""))

    def test_invalid_enum_values_are_dropped_not_fatal(self):
        facts = ExtractedFacts.model_validate({
            "skills": ["tailoring", {"label": "embroidery", "level": "expert-ish"}, {"level": "basic"}, 7],
            "mobility": "far away",
            "aspiration_tags": ["stable_income", "be rich"],
            "formal_training": "no",
            "education_level": "tenth",
            "location": "null",
        })
        self.assertEqual([s.label for s in facts.skills], ["tailoring", "embroidery"])
        self.assertIsNone(facts.skills[1].level)
        self.assertIsNone(facts.mobility)
        self.assertEqual(facts.aspiration_tags, ["stable_income"])
        self.assertIsNone(facts.formal_training)
        self.assertIsNone(facts.education_level)
        self.assertIsNone(facts.location)

    def test_turn_with_missing_fields_gets_defaults(self):
        turn = LLMTurn.model_validate({"reply": "Hello"})
        self.assertEqual(turn.facts.skills, [])


class RuleExtractorTests(unittest.TestCase):
    def test_reference_first_utterance(self):
        facts = rule_extractor.extract(UTTERANCE_1, KB)
        self.assertEqual(facts.skills[0].label, "Tailoring")
        self.assertEqual(facts.skills[0].level, "basic")
        self.assertEqual(facts.aspiration_tags, ["stable_income"])
        self.assertEqual(facts.mobility, "within_village")
        self.assertIsNone(facts.formal_training)

    def test_reference_second_utterance(self):
        facts = rule_extractor.extract(UTTERANCE_2, KB, last_asked_slot="formal_training")
        self.assertIs(facts.formal_training, False)
        self.assertEqual(facts.experience, "Practical, self-taught")

    def test_bare_no_only_counts_after_training_question(self):
        self.assertIs(rule_extractor.extract("No.", KB, last_asked_slot="formal_training").formal_training, False)
        self.assertIsNone(rule_extractor.extract("No.", KB, last_asked_slot="mobility").formal_training)

    def test_asr_style_variants(self):
        facts = rule_extractor.extract("i do silai work and i cant travel far i want steady income", KB)
        self.assertEqual(facts.skills[0].label, "Tailoring")
        self.assertEqual(facts.mobility, "within_village")
        self.assertIn("stable_income", facts.aspiration_tags)

    def test_education_and_location(self):
        facts = rule_extractor.extract("I studied till class 10 and I live in Sanganer.", KB)
        self.assertEqual(facts.education_level, 10)
        self.assertEqual(facts.location, "Sanganer")


if __name__ == "__main__":
    unittest.main()
