import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import requests

from livelihood.schemas import Location
from livelihood.session import LivelihoodSession, demo_script_lines
from location.service import LocationService
from tests.helpers import KB, SANGANER, NoLLM, ScriptedLLM, settings
from tests.test_extraction import UTTERANCE_1, UTTERANCE_2
from tts.service import SpeechService

NETWORK_DOWN = mock.patch("requests.post", side_effect=requests.ConnectionError("offline"))
NETWORK_DOWN_GET = mock.patch("requests.get", side_effect=requests.ConnectionError("offline"))


class LocationFallbackTests(unittest.TestCase):
    def test_demo_mode_uses_cache_without_network(self):
        with NETWORK_DOWN as post, NETWORK_DOWN_GET as get:
            opps = LocationService(settings(demo_mode=True), KB).nearby_opportunities(SANGANER.model_copy())
            post.assert_not_called()
            get.assert_not_called()
        by_id = {o.id: o for o in opps}
        self.assertEqual(by_id["opp-training-pratap-nagar"].distance_km, 7.7)
        self.assertEqual(by_id["osm-tailoring-demand"].source, "openstreetmap (cached)")

    def test_live_mode_falls_back_when_every_api_fails(self):
        with NETWORK_DOWN, NETWORK_DOWN_GET:
            opps = LocationService(settings(demo_mode=False), KB).nearby_opportunities(SANGANER.model_copy())
        by_id = {o.id: o for o in opps}
        self.assertEqual(by_id["opp-training-pratap-nagar"].distance_source, "estimated")
        self.assertGreater(by_id["opp-training-pratap-nagar"].distance_km, 0)
        self.assertEqual(by_id["osm-tailoring-demand"].source, "openstreetmap")

    def test_unknown_place_with_failed_geocoding_returns_empty(self):
        with NETWORK_DOWN, NETWORK_DOWN_GET:
            opps = LocationService(settings(demo_mode=False), KB).nearby_opportunities(Location(name="Nowhere"))
        self.assertEqual(opps, [])


class SpeechFallbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _service(self, **overrides):
        cfg = dict(tts_provider="elevenlabs", elevenlabs_api_key="k", elevenlabs_voice_id="v")
        cfg.update(overrides)
        with mock.patch("tts.service.PiperTTS") as piper_cls:
            service = SpeechService(settings(**cfg), "models", cache_dir=self.cache)
        return service, piper_cls.return_value

    def _ok_response(self):
        response = mock.Mock(content=np.zeros(100, dtype=np.int16).tobytes())
        response.raise_for_status.return_value = None
        return response

    def test_cached_line_plays_even_when_elevenlabs_is_down(self):
        service, _ = self._service()
        with mock.patch("requests.post", return_value=self._ok_response()):
            self.assertTrue(service.prefetch("Hello"))
        fresh, piper = self._service()
        with NETWORK_DOWN as post:
            fresh.synthesize("Hello")
        post.assert_not_called()
        piper.audio_queue.put.assert_called_once()
        piper.synthesize.assert_not_called()

    def test_elevenlabs_audio_goes_to_shared_playback_queue(self):
        service, piper = self._service()
        with mock.patch("requests.post", return_value=self._ok_response()):
            service.synthesize("Hello")
        piper.audio_queue.put.assert_called_once()
        piper.synthesize.assert_not_called()
        self.assertEqual(service.last_provider, "elevenlabs")

    def test_falls_back_to_piper_and_stops_retrying(self):
        service, piper = self._service()
        with NETWORK_DOWN as post:
            for _ in range(4):
                service.synthesize("Hello")
        self.assertEqual(piper.synthesize.call_count, 4)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(service.provider, "piper")

    def test_piper_only_when_elevenlabs_not_configured(self):
        service, piper = self._service(elevenlabs_api_key=None)
        with NETWORK_DOWN as post:
            service.synthesize("Hello")
        post.assert_not_called()
        piper.synthesize.assert_called_once_with("Hello")


class SessionFlowTests(unittest.TestCase):
    def _run(self, llm, demo_mode=True, utterances=(UTTERANCE_1, UTTERANCE_2)):
        s = LivelihoodSession(settings(demo_mode=demo_mode), KB, llm, LocationService(settings(demo_mode=True), KB))
        s.step_pacing_s = 0
        if not demo_mode:
            s.profile.location = SANGANER.model_copy()
        events, spoken = [], []
        with NETWORK_DOWN, NETWORK_DOWN_GET:
            for u in utterances:
                s.handle_turn(u, events.append, spoken.append)
        return s, events, spoken

    def assert_reaches_reference_pathway(self, events, spoken, demo_mode=True):
        types = [e["type"] for e in events]
        self.assertIn("profile_update", types)
        self.assertEqual(types.count("analysis_step"), 8)
        pathway = next(e for e in events if e["type"] == "pathway")
        self.assertEqual(pathway["best"]["pathway"], "Certified Tailoring")
        # Outside the registered demo case the age is unknown, so eligibility is "to verify".
        self.assertEqual(pathway["best"]["fit_score"], 93 if demo_mode else 90)
        first = "Your best-fit pathway is certified tailoring, followed by a nearby apparel opportunity."
        full = first + " It builds on your existing skills while keeping your travel requirement low."
        self.assertEqual(spoken[-1], first if demo_mode else full)

    def test_reference_demo_without_any_llm(self):
        s, events, spoken = self._run(NoLLM())
        self.assertEqual(spoken[0], "I understand. Do you have any formal tailoring training?")
        self.assertEqual(spoken[1], "Got it. I'll find a pathway that builds on your skills and keeps the opportunity local.")
        self.assert_reaches_reference_pathway(events, spoken)
        self.assertEqual(s.phase, "pathway")

    def test_demo_mode_ignores_contradicting_llm_extraction(self):
        wrong = {"facts": {"mobility": "can_relocate", "skills": [{"label": "tailoring", "level": "advanced"}]},
                 "reply": "Great! Where do you live?"}
        _, events, spoken = self._run(ScriptedLLM(wrong, wrong))
        self.assert_reaches_reference_pathway(events, spoken)

    def test_live_mode_uses_llm_phrasing_and_survives_malformed_turn(self):
        first = {"facts": {"skills": [{"label": "tailoring", "level": "basic"}], "aspiration": "stable income",
                           "aspiration_tags": ["stable_income"], "mobility": "within_village"},
                 "reply": "That's a useful skill. Did you ever get formal tailoring training?"}
        _, events, spoken = self._run(ScriptedLLM(first, None, None), demo_mode=False)
        self.assertEqual(spoken[0], "That's a useful skill. Did you ever get formal tailoring training?")
        pathway = next(e for e in events if e["type"] == "pathway")
        self.assertEqual(pathway["best"]["pathway"], "Certified Tailoring")

    def test_live_mode_without_llm_speaks_full_summary(self):
        _, events, spoken = self._run(NoLLM(), demo_mode=False)
        self.assert_reaches_reference_pathway(events, spoken, demo_mode=False)

    def test_demo_script_lines_match_the_live_demo(self):
        _, _, spoken = self._run(ScriptedLLM({"facts": {}, "reply": "x"}, {"facts": {}, "reply": "y"}))
        self.assertEqual(demo_script_lines(settings(demo_mode=True), KB, LocationService(settings(demo_mode=True), KB)), spoken)

    def test_follow_up_question_after_pathway_has_fallback(self):
        _, _, spoken = self._run(NoLLM(), utterances=(UTTERANCE_1, UTTERANCE_2, "What should I do first?"))
        self.assertEqual(spoken[-1], "Your next step is certified tailoring training. A local counsellor can help you enrol.")

    def test_unrecognised_skill_asks_again_instead_of_failing(self):
        _, events, spoken = self._run(NoLLM(), utterances=("I can juggle and I want stable income",))
        self.assertNotIn("pathway", [e["type"] for e in events])
        self.assertTrue(spoken[-1].endswith("?"))

    def test_reset_restores_registered_case(self):
        s, _, _ = self._run(NoLLM())
        s.reset()
        self.assertEqual(s.phase, "conversation")
        self.assertEqual(s.profile.location.name, "Sanganer, Jaipur")
        self.assertEqual(s.transcript, [])


if __name__ == "__main__":
    unittest.main()
