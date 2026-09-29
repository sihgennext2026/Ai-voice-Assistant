import unittest

from livelihood import profile as profile_ops
from livelihood.schemas import BeneficiaryProfile, ExtractedFacts, ExtractedSkill, NearbyOpportunity, ProfileSkill
from location.service import LocationService
from matching import eligibility, engine
from tests.helpers import KB, SANGANER, demo_profile, settings


def cached_opportunities():
    return LocationService(settings(demo_mode=True), KB).nearby_opportunities(SANGANER.model_copy())


class ProfileTests(unittest.TestCase):
    def test_facts_merge_llm_first_rules_fill_gaps(self):
        llm = ExtractedFacts(mobility="nearby_town")
        rules = ExtractedFacts(mobility="within_village", formal_training=False)
        merged = profile_ops.merge_facts(llm, rules)
        self.assertEqual(merged.mobility, "nearby_town")
        self.assertIs(merged.formal_training, False)

    def test_skills_are_normalised_and_deduplicated(self):
        p = BeneficiaryProfile()
        profile_ops.apply_facts(p, ExtractedFacts(skills=[ExtractedSkill(label="basic stitching", level="basic")]), KB)
        profile_ops.apply_facts(p, ExtractedFacts(skills=[ExtractedSkill(label="tailoring")]), KB)
        self.assertEqual([(s.id, s.level) for s in p.skills], [("tailoring", "basic")])

    def test_slot_policy_asks_training_after_reference_utterance(self):
        p = demo_profile(formal_training=None, experience=None)
        self.assertEqual(profile_ops.next_slot(p), "formal_training")
        self.assertEqual(profile_ops.question_for("formal_training", p, True),
                         "I understand. Do you have any formal tailoring training?")
        self.assertTrue(profile_ops.is_ready_for_matching(demo_profile()))

    def test_location_is_required_when_not_registered(self):
        self.assertEqual(profile_ops.missing_slots(demo_profile(location=None)), ["location"])

    def test_display_fields(self):
        fields = {f.label: f.value for f in profile_ops.display_fields(demo_profile())}
        self.assertEqual(fields["Goal"], "Stable local income")
        self.assertEqual(fields["Skills"], "Basic tailoring")
        self.assertEqual(fields["Training"], "No formal certification")
        self.assertEqual(fields["Constraint"], "Limited travel")
        self.assertEqual(fields["Location"], "Sanganer, Jaipur")


class EligibilityTests(unittest.TestCase):
    def test_demo_profile_is_eligible_for_certified_tailoring(self):
        checks = eligibility.evaluate("certified-tailoring", demo_profile(), KB.rules)
        self.assertEqual(eligibility.verdict(checks), "Eligible")

    def test_unknown_age_needs_verification(self):
        checks = eligibility.evaluate("certified-tailoring", demo_profile(age=None), KB.rules)
        self.assertEqual(eligibility.verdict(checks), "Eligible (to verify)")

    def test_minor_is_not_eligible(self):
        checks = eligibility.evaluate("certified-tailoring", demo_profile(age=16), KB.rules)
        self.assertEqual(eligibility.verdict(checks), "Not eligible")

    def test_education_gate(self):
        p = demo_profile(skills=[ProfileSkill(id="sales", label="Sales")], education_level=8)
        self.assertEqual(eligibility.verdict(eligibility.evaluate("retail-sales-associate", p, KB.rules)), "Not eligible")
        p.education_level = 10
        self.assertEqual(eligibility.verdict(eligibility.evaluate("retail-sales-associate", p, KB.rules)), "Eligible")

    def test_unknown_operator_is_rejected(self):
        with self.assertRaises(ValueError):
            eligibility._evaluate("approximately", 1, 1)


class MatchingTests(unittest.TestCase):
    def test_reference_case_recommends_certified_tailoring(self):
        result = engine.match(demo_profile(), cached_opportunities(), KB)
        best = result.best
        self.assertEqual(best.pathway, "Certified Tailoring")
        self.assertEqual(best.fit_score, 93)
        self.assertEqual((best.skill_fit, best.eligibility, best.travel_fit), ("Strong", "Eligible", "High"))
        self.assertEqual(best.skill_gap, ["formal tailoring certification"])
        self.assertEqual(best.next_step, "Certified tailoring training")
        self.assertEqual(best.highlights, ["Strong skill match", "Eligible", "Local opportunity", "Low travel requirement"])
        self.assertEqual([s.key for s in best.stages], ["training", "opportunity", "outcome"])
        self.assertEqual([a.pathway for a in result.alternatives],
                         ["Home-based Tailoring Enterprise", "Garment Factory Operator"])

    def test_scores_are_deterministic(self):
        runs = {engine.match(demo_profile(), cached_opportunities(), KB).best.model_dump_json() for _ in range(5)}
        self.assertEqual(len(runs), 1)

    def test_score_equals_breakdown_sum(self):
        best = engine.match(demo_profile(), cached_opportunities(), KB).best
        self.assertEqual(best.fit_score, round(sum(best.breakdown.model_dump().values())))

    def test_formal_certificate_removes_gap(self):
        best = engine.match(demo_profile(formal_training=True), cached_opportunities(), KB).best
        self.assertEqual(best.skill_gap, [])

    def test_own_business_aspiration_prefers_home_enterprise(self):
        p = demo_profile(aspiration="own business", aspiration_tags=["own_business", "flexible_hours"])
        self.assertEqual(engine.match(p, cached_opportunities(), KB).best.pathway, "Home-based Tailoring Enterprise")

    def test_mobility_constraint_penalises_distant_factory(self):
        local = engine.match(demo_profile(), cached_opportunities(), KB)
        factory_local = next(a for a in local.alternatives if a.pathway_id == "garment-factory-operator")
        mobile = demo_profile(mobility="district", aspiration_tags=["stable_income", "higher_income"])
        factory_mobile = next(
            m for m in [engine.match(mobile, cached_opportunities(), KB).best, *engine.match(mobile, cached_opportunities(), KB).alternatives]
            if m.pathway_id == "garment-factory-operator"
        )
        self.assertEqual(factory_local.travel_fit, "Low")
        self.assertGreater(factory_mobile.fit_score, factory_local.fit_score)

    def test_other_sector(self):
        p = demo_profile(skills=[ProfileSkill(id="cooking", label="Cooking")], aspiration_tags=["own_business"])
        self.assertEqual(engine.match(p, cached_opportunities(), KB).best.pathway, "Food Processing Micro-enterprise")

    def test_no_known_skill_gives_no_recommendation(self):
        p = demo_profile(skills=[ProfileSkill(id=None, label="Juggling")])
        self.assertIsNone(engine.match(p, cached_opportunities(), KB).best)

    def test_works_without_any_location_data(self):
        best = engine.match(demo_profile(), [], KB).best
        self.assertIsNotNone(best)
        self.assertEqual(best.opportunities, [])

    def test_out_of_reach_opportunities_are_flagged(self):
        opps = [NearbyOpportunity(id="x", type="apparel_unit", name="Far unit", area="Elsewhere", distance_km=60, source="illustrative")]
        best = engine.match(demo_profile(), opps, KB).best
        self.assertTrue(all(not o.within_reach for o in best.opportunities))


if __name__ == "__main__":
    unittest.main()
