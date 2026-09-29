from faster_whisper import WhisperModel
import os
from threading import Lock

from config import get_settings

# Biases decoding toward the vocabulary beneficiaries actually use.
DOMAIN_PROMPT = (
    "Livelihood guidance conversation. Tailoring, stitching, sewing, embroidery, "
    "village, stable income, training, certificate, experience, Jaipur, Sanganer."
)


class ASRModel:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    settings = get_settings()
                    instance.model_id = settings.whisper_model
                    print(f"[INFO] Loading ASR model: {instance.model_id} (first run downloads it)")
                    instance.model = WhisperModel(
                        instance.model_id,
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=min(8, os.cpu_count() or 4),
                        num_workers=1,
                        use_auth_token=settings.hf_token,
                    )
                    cls._instance = instance
        return cls._instance

    def transcribe(self, pcm: list[float]):
        english_only = self.model_id.endswith(".en")
        return self.model.transcribe(
            pcm,
            beam_size=5,
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
            language=None if english_only else "en",
            initial_prompt=DOMAIN_PROMPT,
        )
