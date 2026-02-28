"""
agents/voice_agent.py
Agent 1: Voice & Language Agent

Responsibilities:
  1. Convert incoming audio bytes → text  (Amazon Transcribe)
  2. Detect which Indian language is being spoken
  3. Normalize dialectal speech variations (Bhojpuri, Haryanvi, etc.)
  4. Convert outgoing text → audio bytes  (Amazon Polly)
  5. Save all audio to S3 for QA/replay

Supported languages:
  hi = Hindi       ta = Tamil      te = Telugu
  mr = Marathi     bn = Bengali    gu = Gujarati
  kn = Kannada     pa = Punjabi    ml = Malayalam
  en = Indian English

Architecture note:
  This agent is called on EVERY interaction, before any business agent.
  It is intentionally stateless — it does not know what a job is.
  It only converts audio ↔ text, reliably, in all Indian languages.
"""

import io
import uuid
import base64
import asyncio
import tempfile
import json
import re
from typing import Tuple, Optional
from core.config import get_transcribe_client, get_polly_client, get_s3_client, settings


# ─── Language Configuration ───────────────────────────────────────────────────

# Maps our short language codes → Amazon Transcribe language codes
TRANSCRIBE_LANGUAGE_CODES = {
    "hi": "hi-IN",  # Hindi
    "ta": "ta-IN",  # Tamil
    "te": "te-IN",  # Telugu
    "mr": "mr-IN",  # Marathi
    "bn": "bn-IN",  # Bengali
    "gu": "gu-IN",  # Gujarati
    "kn": "kn-IN",  # Kannada
    "pa": "pa-IN",  # Punjabi
    "ml": "ml-IN",  # Malayalam
    "en": "en-IN",  # Indian English
}

# Maps language codes → Amazon Polly voice IDs (neural voices only)
# Kajal is AWS's flagship Indian English/Hindi neural voice, also used for
# multi-lingual output across South Asian languages.
POLLY_VOICE_IDS = {
    "hi": "Kajal",  # Hindi — neural, natural
    "ta": "Kajal",  # Tamil — Kajal supports multiple Indian languages
    "te": "Kajal",  # Telugu
    "mr": "Kajal",  # Marathi
    "bn": "Kajal",  # Bengali
    "gu": "Kajal",  # Gujarati
    "kn": "Kajal",  # Kannada
    "pa": "Kajal",  # Punjabi
    "ml": "Kajal",  # Malayalam
    "en": "Kajal",  # Indian English
}

POLLY_ENGINE = "neural"  # "neural" sounds natural; "standard" sounds robotic

# All Indian language codes Transcribe supports — used for IdentifyLanguage
ALL_TRANSCRIBE_LANGUAGES = [
    "hi-IN",
    "ta-IN",
    "te-IN",
    "mr-IN",
    "bn-IN",
    "gu-IN",
    "kn-IN",
    "pa-IN",
    "ml-IN",
    "en-IN",
]

# ─── Dialect Normalization Patterns ──────────────────────────────────────────
#
# These are the most common dialectal substitutions that cause Transcribe errors.
# They map non-standard forms (as Transcribe might produce them) to
# standard Hindi words that downstream agents handle correctly.
#
# Bhojpuri: spoken by ~50M workers from Bihar/UP — biggest source of
#           construction labor in major Indian cities.
# Haryanvi: major in Delhi NCR construction market.

DIALECT_NORMALIZATIONS = {
    # Bhojpuri number words → standard Hindi
    "एक": "एक",  # same
    "दुई": "दो",
    "तीन": "तीन",
    "चार": "चार",
    "पाँच": "पाँच",
    # Bhojpuri verb forms
    "बाड़ी": "हूँ",  # "I am" (female, Bhojpuri)
    "बाड़ा": "हूँ",  # "I am" (male, Bhojpuri)
    "बा": "है",  # "is/am" in Bhojpuri
    "बाटे": "है",
    "रहनी": "रहती हूँ",
    "करनी": "करती हूँ",
    # Common Haryanvi
    "म्हारे": "मेरे",
    "थारे": "तुम्हारे",
    "कोनी": "नहीं",
    # Colloquial Hindi shortcuts
    "nahi": "नहीं",
    "haan": "हाँ",
    "kaam": "काम",
    "paisa": "पैसा",
}


def normalize_dialect(text: str) -> str:
    """
    Post-process Transcribe output to normalize dialectal variations.
    This runs AFTER transcription, BEFORE passing to agents.

    Approach: simple word-by-word substitution for known patterns.
    This is a living function — add new patterns as discovered through
    real-world testing.
    """
    if not text:
        return text

    normalized = text
    for dialectal_form, standard_form in DIALECT_NORMALIZATIONS.items():
        # Word boundary matching (handles Devanagari and Latin)
        normalized = re.sub(
            r"(?<!\w)" + re.escape(dialectal_form) + r"(?!\w)",
            standard_form,
            normalized,
        )

    return normalized


# ─── Speech to Text (Batch) ───────────────────────────────────────────────────


async def transcribe_audio(
    audio_bytes: bytes, language_hint: str = "hi", worker_id: str = None
) -> Tuple[str, str]:
    """
    Convert audio bytes to text using Amazon Transcribe (batch mode).

    We use batch (not streaming) because:
    - The browser captures a complete utterance (hold-to-record pattern)
    - Batch is simpler, cheaper, and has better accuracy than streaming
    - Streaming is only used for live phone calls via AWS Connect

    Flow:
      1. Upload audio to S3 (Transcribe requires S3 input)
      2. Start transcription job with multi-language auto-detection
      3. Poll for completion (~5–15s for 30s clips)
      4. Download and parse JSON transcript
      5. Normalize dialect variations
      6. Clean up temporary S3 object

    Returns:
        (transcribed_text, detected_language_code)  e.g. ("main painter hoon", "hi")
    """
    s3 = get_s3_client()
    transcribe = get_transcribe_client()

    job_name = f"js-{uuid.uuid4().hex[:16]}"  # short job name — Transcribe has a name length limit
    s3_key = f"audio/transcribe-temp/{job_name}.webm"

    # ── Step 1: Upload to S3 ──────────────────────────────────────────────
    def upload_audio():
        s3.put_object(
            Bucket=settings.S3_AUDIO_BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType="audio/webm",
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upload_audio)

    s3_uri = f"s3://{settings.S3_AUDIO_BUCKET}/{s3_key}"

    # ── Step 2: Start Transcription Job ───────────────────────────────────
    # IdentifyLanguage=True auto-detects from the audio.
    # LanguageOptions narrows the candidates to Indian languages only,
    # which significantly improves accuracy vs. open-ended detection.
    def start_job():
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": s3_uri},
            MediaFormat="webm",
            IdentifyLanguage=True,
            LanguageOptions=ALL_TRANSCRIBE_LANGUAGES,
            Settings={
                "ShowSpeakerLabels": False,
                "ChannelIdentification": False,
            },
        )

    await loop.run_in_executor(None, start_job)

    # ── Step 3: Poll for Completion ───────────────────────────────────────
    def poll_until_complete():
        import time

        for _ in range(120):  # max 2 minutes polling
            response = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            status = response["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                return response["TranscriptionJob"]
            elif status == "FAILED":
                reason = response["TranscriptionJob"].get(
                    "FailureReason", "Unknown error"
                )
                raise RuntimeError(f"Transcribe job failed: {reason}")

            time.sleep(1)

        raise TimeoutError("Transcribe job did not complete within 2 minutes")

    job_result = await loop.run_in_executor(None, poll_until_complete)

    # ── Step 4: Fetch and Parse Transcript ───────────────────────────────
    import urllib.request

    transcript_uri = job_result["Transcript"]["TranscriptFileUri"]

    def fetch_transcript():
        with urllib.request.urlopen(transcript_uri) as resp:
            data = json.loads(resp.read())
        return data

    transcript_data = await loop.run_in_executor(None, fetch_transcript)

    raw_text = transcript_data["results"]["transcripts"][0]["transcript"]

    # ── Step 5: Normalize dialect ─────────────────────────────────────────
    transcribed_text = normalize_dialect(raw_text)

    # ── Detect language ───────────────────────────────────────────────────
    detected_lang_code_full = job_result.get("LanguageCode", f"{language_hint}-IN")
    detected_language = detected_lang_code_full.split("-")[0]  # "hi-IN" → "hi"

    # ── Step 6: Cleanup ───────────────────────────────────────────────────
    def cleanup():
        try:
            s3.delete_object(Bucket=settings.S3_AUDIO_BUCKET, Key=s3_key)
        except Exception:
            pass
        try:
            transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:
            pass

    await loop.run_in_executor(None, cleanup)

    return transcribed_text, detected_language


# ─── Text to Speech ───────────────────────────────────────────────────────────


async def synthesize_speech(
    text: str, language: str = "hi", speaking_rate: str = "medium"
) -> bytes:
    """
    Convert text → audio using Amazon Polly (neural TTS).

    Returns:
        audio_bytes — MP3 that the browser plays directly via Web Audio API

    Why MP3? Universally supported across all browsers, Android, and iOS.
    The frontend receives this as base64 and plays it with AudioContext.

    SSML notes:
    - We wrap text in SSML <speak> tags to enable prosody control
    - <break> tags add natural pauses between sentences
    - Neural Kajal voice sounds indistinguishable from natural speech for
      most Hindi/Indian-English listeners
    """
    polly = get_polly_client()

    voice_id = POLLY_VOICE_IDS.get(language, "Kajal")
    polly_lang_code = TRANSCRIBE_LANGUAGE_CODES.get(language, "hi-IN")

    # Build SSML for more natural speech
    # Add sentence breaks and mild prosody adjustment for conversational tone
    ssml_text = f'<speak><prosody rate="95%">{_text_to_ssml(text)}</prosody></speak>'

    def call_polly():
        response = polly.synthesize_speech(
            TextType="ssml",
            Text=ssml_text,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine=POLLY_ENGINE,
            LanguageCode=polly_lang_code,
        )
        return response["AudioStream"].read()

    loop = asyncio.get_event_loop()
    try:
        audio_bytes = await loop.run_in_executor(None, call_polly)
    except Exception as e:
        # SSML may fail if text contains problematic characters — fall back to plain text
        def call_polly_plain():
            response = polly.synthesize_speech(
                Text=text[:2999],  # Polly 3000 char limit
                OutputFormat="mp3",
                VoiceId=voice_id,
                Engine=POLLY_ENGINE,
                LanguageCode=polly_lang_code,
            )
            return response["AudioStream"].read()

        audio_bytes = await loop.run_in_executor(None, call_polly_plain)

    return audio_bytes


def _text_to_ssml(text: str) -> str:
    """
    Converts plain text to SSML-safe format.
    - Escapes XML special characters
    - Converts sentence-ending punctuation to SSML <break> tags for natural pauses
    """
    # Escape XML chars first
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

    # Add natural pauses after sentences
    text = re.sub(r"([।\.!?])\s+", r'\1<break time="300ms"/> ', text)

    # Limit length for Polly (SSML overhead + text must be < 6000 chars)
    return text[:3500]


# ─── Audio Storage ────────────────────────────────────────────────────────────


async def save_audio_to_s3(
    audio_bytes: bytes,
    worker_id: str,
    direction: str = "user",  # "user" or "agent"
    metadata: dict = None,
) -> str:
    """
    Saves audio to S3 for:
    - QA: replay real conversations to improve prompts and dialect handling
    - Worker records: audit trail of work history discussions
    - Debugging transcription errors

    Lifecycle: configure an S3 lifecycle rule to expire objects in
    audio/workers/ after 90 days to control storage costs.

    Returns:
        s3_key — stored in the conversations table for lookup
    """
    s3 = get_s3_client()
    ext = "webm" if direction == "user" else "mp3"
    s3_key = f"audio/workers/{worker_id}/{direction}/{uuid.uuid4()}.{ext}"

    def upload():
        kwargs = dict(
            Bucket=settings.S3_AUDIO_BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType="audio/webm" if direction == "user" else "audio/mpeg",
        )
        if metadata:
            kwargs["Metadata"] = {k: str(v) for k, v in metadata.items()}
        s3.put_object(**kwargs)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upload)

    return s3_key


# ─── Waveform / Audio Level Detection ────────────────────────────────────────


def estimate_audio_level(audio_bytes: bytes) -> float:
    """
    Estimate the RMS audio level of a WebM audio blob.
    Used to detect silence (very short or empty recordings).

    Returns a float 0.0–1.0. Values below 0.02 are likely silence.
    This is a heuristic — works well enough for our use case.
    """
    if len(audio_bytes) < 200:
        return 0.0
    # Use the last 20% of bytes as a rough energy proxy
    # (WebM header takes up the first chunk; payload is at the end)
    sample = audio_bytes[int(len(audio_bytes) * 0.8) :]
    rms = (sum(b**2 for b in sample) / len(sample)) ** 0.5
    return min(1.0, rms / 128.0)


# ─── Public API (called by orchestrator) ─────────────────────────────────────


async def process_voice_input(
    audio_bytes: bytes, language_hint: str, worker_id: str
) -> Tuple[str, str, str]:
    """
    Full input pipeline: audio bytes → (text, detected_language, s3_key).

    Runs transcription and S3 upload concurrently to minimize latency.
    The S3 upload for the user's audio happens in the background while
    Transcribe is processing — saves ~500ms per request.

    Returns:
        (transcribed_text, detected_language, user_audio_s3_key)
    """
    # Check for silence before hitting Transcribe
    level = estimate_audio_level(audio_bytes)
    if level < 0.015:
        # Audio is likely silence — skip API call, return empty
        return "", language_hint, None

    # Run transcription and S3 upload concurrently
    transcription_task = transcribe_audio(audio_bytes, language_hint, worker_id)
    s3_task = save_audio_to_s3(audio_bytes, worker_id, "user")

    results = await asyncio.gather(transcription_task, s3_task, return_exceptions=True)

    # Handle transcription result
    if isinstance(results[0], Exception):
        print(f"[VoiceAgent] Transcription error: {results[0]}")
        text, detected_lang = "", language_hint
    else:
        text, detected_lang = results[0]

    # Handle S3 result
    s3_key = results[1] if not isinstance(results[1], Exception) else None

    return text, detected_lang, s3_key


async def generate_voice_response(
    text: str, language: str, worker_id: str
) -> Tuple[str, str]:
    """
    Full output pipeline: text → (audio_base64, s3_key).

    audio_base64 goes directly to the frontend for immediate playback.
    s3_key is stored in the conversations table.

    Returns:
        (audio_base64, s3_key)
    """
    if not text or not text.strip():
        return "", None

    audio_bytes = await synthesize_speech(text, language)

    # Encode for frontend and save to S3 concurrently
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    s3_key = await save_audio_to_s3(audio_bytes, worker_id, "agent")

    return audio_base64, s3_key


# ─── Language Utilities ───────────────────────────────────────────────────────


def get_language_name(code: str) -> str:
    """Human-readable language name for a language code."""
    names = {
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "mr": "Marathi",
        "bn": "Bengali",
        "gu": "Gujarati",
        "kn": "Kannada",
        "pa": "Punjabi",
        "ml": "Malayalam",
        "en": "English",
    }
    return names.get(code, "Hindi")


def get_polly_language_code(language: str) -> str:
    """Returns the Polly LanguageCode for a given short language code."""
    return TRANSCRIBE_LANGUAGE_CODES.get(language, "hi-IN")
