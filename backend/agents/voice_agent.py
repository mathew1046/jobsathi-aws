"""
agents/voice_agent.py
Agent 1: Voice & Language Agent

Responsibilities:
  1. Convert incoming audio bytes → text  (Amazon Transcribe)
  2. Detect which Indian language is being spoken
  3. Convert outgoing text → audio bytes  (Amazon Polly)

This agent is called FIRST on every single interaction, before any other agent.
It does not make business decisions. It only translates: audio↔text, both directions.

Supported languages:
  hi = Hindi       ta = Tamil      te = Telugu
  mr = Marathi     bn = Bengali    gu = Gujarati
  kn = Kannada     pa = Punjabi    ml = Malayalam
"""

import io
import uuid
import boto3
import base64
import asyncio
import tempfile
from typing import Tuple, Optional
from core.config import get_transcribe_client, get_polly_client, get_s3_client, settings


# ─── Language Configuration ───────────────────────────────────────────────────

# Maps our language codes → Amazon Transcribe language codes
TRANSCRIBE_LANGUAGE_CODES = {
    "hi": "hi-IN",   # Hindi
    "ta": "ta-IN",   # Tamil
    "te": "te-IN",   # Telugu
    "mr": "mr-IN",   # Marathi
    "bn": "bn-IN",   # Bengali
    "gu": "gu-IN",   # Gujarati
    "kn": "kn-IN",   # Kannada
    "pa": "pa-IN",   # Punjabi
    "ml": "ml-IN",   # Malayalam
    "en": "en-IN",   # Indian English
}

# Maps our language codes → Amazon Polly voice IDs (neural voices)
POLLY_VOICE_IDS = {
    "hi": "Kajal",    # Hindi — neural voice, natural sounding
    "ta": "Kajal",    # Tamil — Kajal supports multiple Indian languages
    "te": "Kajal",    # Telugu
    "mr": "Kajal",    # Marathi
    "bn": "Kajal",    # Bengali
    "gu": "Kajal",    # Gujarati
    "kn": "Kajal",    # Kannada
    "pa": "Kajal",    # Punjabi
    "ml": "Kajal",    # Malayalam
    "en": "Kajal",    # Indian English
}

# Polly engine — "neural" sounds natural, "standard" is robotic
POLLY_ENGINE = "neural"


# ─── Speech to Text ───────────────────────────────────────────────────────────

async def transcribe_audio(
    audio_bytes: bytes,
    language_hint: str = "hi",
    worker_id: str = None
) -> Tuple[str, str]:
    """
    Convert audio bytes to text using Amazon Transcribe.

    We use the batch (non-streaming) approach here because:
    - The frontend captures a complete voice clip (user holds mic, then releases)
    - Batch is simpler and cheaper than streaming for complete utterances
    - Streaming Transcribe is only needed for live phone calls (AWS Connect)

    Returns:
        (transcribed_text, detected_language_code)

    How it works:
        1. Upload audio to S3 (Transcribe reads from S3, not direct bytes)
        2. Start a transcription job
        3. Poll until complete (usually 5-15 seconds for short clips)
        4. Read transcript
        5. Clean up S3 object
    """
    s3 = get_s3_client()
    transcribe = get_transcribe_client()

    # Step 1: Upload audio to S3 with a unique key
    job_name = f"transcribe-{uuid.uuid4()}"
    s3_key = f"audio/transcribe-temp/{job_name}.webm"

    s3.put_object(
        Bucket=settings.S3_AUDIO_BUCKET,
        Key=s3_key,
        Body=audio_bytes,
        ContentType="audio/webm"
    )

    s3_uri = f"s3://{settings.S3_AUDIO_BUCKET}/{s3_key}"

    # Step 2: Start transcription job
    # We pass the language as a hint (LanguageCode) but also enable
    # IdentifyLanguage so Transcribe can correct us if we're wrong
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat="webm",
        # LanguageCode=TRANSCRIBE_LANGUAGE_CODES.get(language_hint, "hi-IN"),
        # Use auto-detection instead of hardcoding — more robust
        IdentifyLanguage=True,
        LanguageOptions=[
            "hi-IN", "ta-IN", "te-IN", "mr-IN",
            "bn-IN", "gu-IN", "kn-IN", "pa-IN", "ml-IN", "en-IN"
        ],
    )

    # Step 3: Poll for completion (runs in thread pool to not block async loop)
    def poll_transcription():
        import time
        while True:
            response = transcribe.get_transcription_job(
                TranscriptionJobName=job_name
            )
            status = response["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                return response["TranscriptionJob"]
            elif status == "FAILED":
                raise Exception(f"Transcription failed: {response['TranscriptionJob'].get('FailureReason')}")

            time.sleep(1)  # poll every second

    loop = asyncio.get_event_loop()
    job_result = await loop.run_in_executor(None, poll_transcription)

    # Step 4: Download and parse the transcript JSON
    import urllib.request
    transcript_uri = job_result["Transcript"]["TranscriptFileUri"]
    with urllib.request.urlopen(transcript_uri) as response:
        import json
        transcript_data = json.loads(response.read())

    transcribed_text = transcript_data["results"]["transcripts"][0]["transcript"]

    # Get the detected language
    detected_language_full = job_result.get("IdentifiedLanguageScore", {})
    detected_lang_code_full = job_result.get("LanguageCode", "hi-IN")

    # Convert "hi-IN" back to our short code "hi"
    detected_language = detected_lang_code_full.split("-")[0]

    # Step 5: Clean up temp S3 object
    s3.delete_object(Bucket=settings.S3_AUDIO_BUCKET, Key=s3_key)

    # Clean up transcription job (optional, but keeps your job list clean)
    try:
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception:
        pass  # not critical if this fails

    return transcribed_text, detected_language


# ─── Text to Speech ───────────────────────────────────────────────────────────

async def synthesize_speech(
    text: str,
    language: str = "hi"
) -> bytes:
    """
    Convert text to audio using Amazon Polly.

    Returns:
        audio_bytes — MP3 audio that the browser can play directly

    Why MP3? It's universally supported in all browsers and on mobile.
    The frontend receives this as base64 and plays it with the Web Audio API.
    """
    polly = get_polly_client()

    voice_id = POLLY_VOICE_IDS.get(language, "Kajal")

    def call_polly():
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine=POLLY_ENGINE,
            # LanguageCode is needed for Kajal since it supports multiple languages
            LanguageCode=TRANSCRIBE_LANGUAGE_CODES.get(language, "hi-IN"),
        )
        return response["AudioStream"].read()

    loop = asyncio.get_event_loop()
    audio_bytes = await loop.run_in_executor(None, call_polly)

    return audio_bytes


# ─── Save Audio to S3 (permanent storage) ────────────────────────────────────

async def save_audio_to_s3(
    audio_bytes: bytes,
    worker_id: str,
    direction: str = "user"  # "user" or "agent"
) -> str:
    """
    Saves audio to S3 for:
    - QA/review: listen to real conversations to improve prompts
    - Worker records: evidence of work history discussions
    - Debugging transcription errors

    Returns:
        s3_key — the path in S3 (stored in conversations table)
    """
    s3 = get_s3_client()
    s3_key = f"audio/workers/{worker_id}/{direction}/{uuid.uuid4()}.mp3"

    def upload():
        s3.put_object(
            Bucket=settings.S3_AUDIO_BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType="audio/mpeg",
            # Keep audio files for 90 days, then auto-delete
            # (configure this as an S3 lifecycle rule in the console)
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upload)

    return s3_key


# ─── Main function called by orchestrator ────────────────────────────────────

async def process_voice_input(
    audio_bytes: bytes,
    language_hint: str,
    worker_id: str
) -> Tuple[str, str, str]:
    """
    Full pipeline: audio in → text + detected language out.
    Also saves the audio to S3.

    Returns:
        (transcribed_text, detected_language, audio_s3_key)
    """
    # Run transcription and S3 save concurrently
    transcription_task = transcribe_audio(audio_bytes, language_hint, worker_id)
    s3_task = save_audio_to_s3(audio_bytes, worker_id, "user")

    (text, detected_lang), s3_key = await asyncio.gather(transcription_task, s3_task)

    return text, detected_lang, s3_key


async def generate_voice_response(
    text: str,
    language: str,
    worker_id: str
) -> Tuple[str, str]:
    """
    Full pipeline: text in → audio base64 + S3 key out.
    The base64 goes directly to the frontend to play.
    The S3 key gets stored in the conversations table.

    Returns:
        (audio_base64, s3_key)
    """
    audio_bytes = await synthesize_speech(text, language)

    # Save to S3 and encode for frontend concurrently
    s3_task = save_audio_to_s3(audio_bytes, worker_id, "agent")
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    s3_key = await s3_task

    return audio_base64, s3_key
