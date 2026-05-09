"""ElevenLabs text-to-speech integration.

Design constraints:
  - No hardcoded API keys. Reads ELEVENLABS_API_KEY from the environment.
  - Caches audio on disk by sha1(text|voice_id) to avoid duplicate cost.
  - Returns a clear "voice_disabled" sentinel when the key is missing so the
    API layer can respond with HTTP 503 and the frontend hide the player.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default voice. Sarah ("Mature, Reassuring, Confident") is a premade voice
# available on every ElevenLabs account tier, and works well with the
# multilingual model for Spanish narratives. Override via ELEVENLABS_VOICE_ID.
DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
DEFAULT_MODEL = "eleven_multilingual_v2"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"


class VoiceDisabledError(Exception):
    """Raised when ELEVENLABS_API_KEY is not configured."""


@dataclass
class VoiceResult:
    audio_path: Path
    cached: bool
    voice_id: str


def _cache_key(text: str, voice_id: str) -> str:
    h = hashlib.sha1()
    h.update(voice_id.encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


# Accept both the canonical name and the lowercase alias used by some
# externally-managed credential files.
_API_KEY_ENV_NAMES = ("ELEVENLABS_API_KEY", "key_elevenlabs")


def _api_key() -> str:
    for name in _API_KEY_ENV_NAMES:
        val = os.getenv(name, "").strip()
        if val:
            return val
    raise VoiceDisabledError(
        "ELEVENLABS_API_KEY (or key_elevenlabs) env var not set; "
        "voice briefing is disabled."
    )


def is_enabled() -> bool:
    return any(os.getenv(name, "").strip() for name in _API_KEY_ENV_NAMES)


def synthesize(text: str, voice_id: Optional[str] = None) -> VoiceResult:
    """Synthesize `text` with ElevenLabs, returning a path to a cached MP3.

    Raises VoiceDisabledError if the API key is missing. Network errors are
    propagated as `requests.HTTPError`; callers must translate them to
    appropriate HTTP responses.
    """
    voice = (voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID).strip()
    text = (text or "").strip()
    if not text:
        raise ValueError("voice.synthesize requires non-empty text.")

    cache_path = CACHE_DIR / f"{_cache_key(text, voice)}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        log.info("voice cache hit: %s", cache_path.name)
        return VoiceResult(audio_path=cache_path, cached=True, voice_id=voice)

    api_key = _api_key()  # raises VoiceDisabledError if missing
    url = ELEVENLABS_URL.format(voice_id=voice)
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": DEFAULT_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    log.info("Calling ElevenLabs (voice=%s, %d chars)", voice, len(text))
    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    # If the configured voice isn't in this account (402/404), retry once with
    # the first premade voice the key actually has access to. This makes the
    # demo robust against API key / voice mismatches without hardcoding a
    # specific account's voice list.
    if resp.status_code in (402, 404):
        fallback = _first_available_premade(api_key)
        if fallback and fallback != voice:
            log.warning(
                "voice %s rejected (HTTP %d); retrying with first premade voice %s",
                voice, resp.status_code, fallback,
            )
            voice = fallback
            url = ELEVENLABS_URL.format(voice_id=voice)
            cache_path = CACHE_DIR / f"{_cache_key(text, voice)}.mp3"
            if cache_path.exists() and cache_path.stat().st_size > 0:
                return VoiceResult(audio_path=cache_path, cached=True, voice_id=voice)
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

    resp.raise_for_status()
    cache_path.write_bytes(resp.content)
    return VoiceResult(audio_path=cache_path, cached=False, voice_id=voice)


def _first_available_premade(api_key: str) -> Optional[str]:
    """Return the first 'premade' voice ID the API key has access to."""
    try:
        r = requests.get(
            ELEVENLABS_VOICES_URL,
            headers={"xi-api-key": api_key, "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        for v in r.json().get("voices", []):
            if v.get("category") == "premade" and v.get("voice_id"):
                return v["voice_id"]
    except Exception as e:  # pragma: no cover - network errors
        log.warning("voice listing failed: %s", e)
    return None
