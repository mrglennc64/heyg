"""XTTS v2 wrapper — multilingual voice cloning with cached speaker latents.

Design points:
- Speaker latents (gpt_cond_latent + speaker_embedding) are computed ONCE per
  voice_id from the 30 s–3 min reference and cached to /cache and S3. Every
  later synthesis is a cheap conditional decode.
- Long scripts are split on sentence boundaries (XTTS degrades past ~250
  chars per call), synthesized per chunk, then crossfaded — this is the
  long-form stability trick on the audio side.
- Emotion is steered three ways: sampling temperature, per-emotion reference
  segment selection (if the reference contains varied delivery), and
  post-hoc prosody (speed/pitch) in audio_post.py.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import torch

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

from forge_shared.storage import download, upload

MODEL_DIR = os.environ.get("XTTS_MODEL_DIR", "/models/xtts_v2")
CACHE_DIR = Path(os.environ.get("LATENT_CACHE", "/cache/latents"))

# Emotion → (temperature, repetition_penalty, speed_bias)
EMOTION_PRESETS = {
    "neutral":  (0.65, 2.0, 1.00),
    "friendly": (0.75, 2.0, 1.03),
    "serious":  (0.55, 2.5, 0.96),
    "excited":  (0.85, 1.8, 1.08),
    "sad":      (0.60, 2.5, 0.92),
}

_SENTENCE_RE = re.compile(r"(?<=[.!?…。！？])\s+")
MAX_CHUNK_CHARS = 240


class XTTSEngine:
    _instance: "XTTSEngine | None" = None

    def __init__(self) -> None:
        config = XttsConfig()
        config.load_json(f"{MODEL_DIR}/config.json")
        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(config, checkpoint_dir=MODEL_DIR, use_deepspeed=False)
        self.model.cuda().eval()
        self.sample_rate = 24_000
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get(cls) -> "XTTSEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── speaker latents ─────────────────────────────────────────────
    def latents_for(self, voice_id: str, reference_key: str) -> tuple[torch.Tensor, torch.Tensor]:
        cache_path = CACHE_DIR / f"{voice_id}.pt"
        if cache_path.exists():
            blob = torch.load(cache_path, map_location="cuda")
            return blob["gpt_cond_latent"], blob["speaker_embedding"]

        ref_wav = download(reference_key, f"/scratch/refs/{voice_id}.wav")
        gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[str(ref_wav)],
            gpt_cond_len=30,            # seconds of conditioning context
            max_ref_length=60,
        )
        torch.save(
            {"gpt_cond_latent": gpt_cond_latent, "speaker_embedding": speaker_embedding},
            cache_path,
        )
        upload(cache_path, f"voices/{voice_id}/latents.pt")
        return gpt_cond_latent, speaker_embedding

    # ── synthesis ───────────────────────────────────────────────────
    def synthesize(
        self,
        text: str,
        voice_id: str,
        reference_key: str,
        language: str = "en",
        emotion: str = "neutral",
        temperature: float | None = None,
    ) -> list[torch.Tensor]:
        """Returns a list of per-chunk waveform tensors (24 kHz mono)."""
        gpt_cond, spk_emb = self.latents_for(voice_id, reference_key)
        temp, rep_pen, _ = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS["neutral"])
        if temperature is not None:
            temp = temperature

        chunks = self._chunk(text)
        waves: list[torch.Tensor] = []
        with torch.inference_mode():
            for chunk in chunks:
                out = self.model.inference(
                    text=chunk,
                    language=language,
                    gpt_cond_latent=gpt_cond,
                    speaker_embedding=spk_emb,
                    temperature=temp,
                    repetition_penalty=rep_pen,
                    enable_text_splitting=False,   # we split ourselves
                )
                waves.append(torch.as_tensor(out["wav"]))
        return waves

    @staticmethod
    def _chunk(text: str) -> list[str]:
        sentences = _SENTENCE_RE.split(text.strip())
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) + 1 > MAX_CHUNK_CHARS and current:
                chunks.append(current.strip())
                current = s
            else:
                current = f"{current} {s}".strip()
        if current:
            chunks.append(current)
        return chunks or [text]
