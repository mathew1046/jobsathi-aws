"""
core/orchestrator.py
The Orchestrator — routes every incoming message to the correct agent.

This is the brain. Every single message from every channel arrives here first.
It answers three questions:
  1. Who is this? (load session)
  2. What do they need? (check agent state)
  3. Which agent handles this? (route)

The orchestrator does NOT call Bedrock for routing — it uses simple state
machine logic based on the session. This keeps routing fast and deterministic.
Bedrock is only called inside the individual agent modules.
"""

import uuid
from typing import Tuple
from core.session import get_session, create_new_session, save_session
from core.database import (
    get_or_create_worker,
    get_worker_profile,
    save_conversation_turn
)
from agents.voice_agent import process_voice_input, generate_voice_response
from agents.onboarding_agent import handle_onboarding_message
from agents.matching_agent import handle_matching_message


async def process_message(
    audio_bytes: bytes,
    phone_number: str,
    session_id: str = None
) -> dict:
    """
    The single entry point for ALL user messages.

    Input:
        audio_bytes   — raw audio from the browser mic
        phone_number  — worker's phone number (their identity)
        session_id    — optional, for session continuity across browser refreshes

    Output dict:
        {
          "text": "response text",
          "audio_base64": "base64 mp3 audio",
          "session_id": "uuid",
          "agent": "onboarding",
          "progress": { "questions_answered": 5, "total": 20 },
          "profile_complete": false,
          "jobs": []  ← populated when matching agent returns results
        }
    """

    # ── Step 1: Identify the worker ───────────────────────────────────────────
    worker = await get_or_create_worker(phone_number)
    worker_id = str(worker["id"])

    # ── Step 2: Load or create session ───────────────────────────────────────
    session = await get_session(phone_number)

    if not session:
        # New worker — create fresh session
        new_session_id = session_id or str(uuid.uuid4())
        session = await create_new_session(worker_id, phone_number, new_session_id)

        # Check if they have a profile from a previous session (e.g., Redis expired)
        existing_profile = await get_worker_profile(worker_id)
        if existing_profile and existing_profile.get("questions_answered", 0) > 0:
            # Resume from where they left off
            session["onboarding"]["questions_answered"] = existing_profile["questions_answered"]
            session["onboarding"]["current_question_index"] = existing_profile["questions_answered"]

            # Restore collected data from DB into session
            profile_fields = [
                "primary_skill", "secondary_skills", "years_experience",
                "city", "district", "state", "willing_to_relocate",
                "max_travel_km", "availability", "expected_daily_wage",
                "work_type", "name", "skill_description"
            ]
            for field in profile_fields:
                if existing_profile.get(field) is not None:
                    session["onboarding"]["collected_data"][field] = existing_profile[field]

            if existing_profile.get("profile_complete"):
                session["current_agent"] = "matching"
                session["onboarding"]["complete"] = True

        await save_session(phone_number, session)

    session_id = session["session_id"]
    language = session.get("language", "hi")

    # ── Step 3: Process voice input ───────────────────────────────────────────
    transcribed_text = ""
    user_audio_s3_key = None

    if audio_bytes and len(audio_bytes) > 100:  # ignore empty audio
        transcribed_text, detected_language, user_audio_s3_key = await process_voice_input(
            audio_bytes, language, worker_id
        )

        # Update language in session if detected language changed
        if detected_language and detected_language != language:
            session["language"] = detected_language
            language = detected_language
            await save_session(phone_number, session)

    # Save the user's turn to DB immediately
    if transcribed_text:
        await save_conversation_turn(
            worker_id, session_id, "user", transcribed_text,
            session["current_agent"], user_audio_s3_key
        )

    # ── Step 4: Route to correct agent ───────────────────────────────────────
    current_agent = session.get("current_agent", "onboarding")

    if current_agent == "onboarding":
        response_text, session = await handle_onboarding_message(
            transcribed_text, session, worker_id, phone_number
        )
    elif current_agent == "matching":
        response_text, session = await handle_matching_message(
            transcribed_text, session, worker_id, phone_number
        )
    else:
        response_text = "Namaste! Main JobSathi hoon. Aapki kya madad kar sakta hoon?"
        if language == "hi":
            response_text = "नमस्ते! मैं JobSathi हूँ। आपकी क्या मदद कर सकता हूँ?"

    # ── Step 5: Generate voice response ──────────────────────────────────────
    agent_audio_base64, agent_audio_s3_key = await generate_voice_response(
        response_text, language, worker_id
    )

    # ── Step 6: Save agent's response to DB ──────────────────────────────────
    await save_conversation_turn(
        worker_id, session_id, "assistant", response_text,
        current_agent, agent_audio_s3_key
    )

    # ── Step 7: Save updated session to Redis ─────────────────────────────────
    await save_session(phone_number, session)

    # ── Step 8: Build response ────────────────────────────────────────────────
    onboarding_state = session["onboarding"]
    questions_answered = onboarding_state.get("questions_answered", 0)

    return {
        "text": response_text,
        "audio_base64": agent_audio_base64,
        "session_id": session_id,
        "agent": current_agent,
        "language": language,
        "progress": {
            "questions_answered": questions_answered,
            "total": 20,
            "percent": int((questions_answered / 20) * 100)
        },
        "profile_complete": onboarding_state.get("complete", False),
        "transcribed_input": transcribed_text,  # helpful for debugging
    }
