"""
agents/onboarding_agent.py
Agent 2: Onboarding Agent

Responsibilities:
  1. Ask 20 questions conversationally to build a complete worker profile
  2. Extract structured data from conversational answers (via Bedrock)
  3. Save each answer immediately to RDS (incremental persistence)
  4. Generate a PDF resume once all questions are answered

The 20 Questions are stored in the `onboarding_questions` and
`question_translations` database tables, seeded by `seed_questions.py`.
They are fetched at runtime so translations can be updated without a deploy.

At runtime the agent calls `get_question_text(index, language_code)` from
`core.database` to get the right question in the worker's language.

Profile fields collected (question index → DB column):
  0  primary_skill         — tile_work / painting / electrical / …
  1  secondary_skills      — list of additional skills
  2  years_experience      — integer
  3  city                  — e.g. Pune
  4  district              — neighbourhood / locality
  5  state                 — e.g. Maharashtra
  6  willing_to_relocate   — bool
  7  max_travel_km         — integer
  8  availability          — immediate / employed / 1_week / 1_month
  9  expected_daily_wage   — integer (INR per day)
  10 work_type             — daily_wage / contract / permanent / any
  11 preferred_hours       — e.g. "8am-5pm" / "flexible"
  12 name                  — optional string
  13 biggest_project       — free text for resume work history
  14 previous_employer     — company / contractor name
  15 certifications        — list of strings
  16 tools_equipment       — list of strings
  17 special_skills        — free text
  18 skill_description     — 2-3 sentences for resume summary
  19 resume_consent        — bool
"""

import json
import asyncio
from typing import Optional, Tuple
from core.config import get_bedrock_client, settings
from core.database import (
    get_pool,
    save_conversation_turn,
    get_recent_conversation,
    get_question_text,
)
from core.session import get_session, update_session_field, save_session


# ─── Static question metadata (no translations here — those live in DB) ───────
# Each entry carries only:
#   index           — conversation position (0-based)
#   key             — DB column the extracted value is written to
#   extraction_hint — instruction to Bedrock for structured extraction
#
# The actual question text is fetched from `question_translations` at runtime
# via `get_question_text(index, language_code)`.

ONBOARDING_QUESTIONS = [
    {
        "index": 0,
        "key": "primary_skill",
        "extraction_hint": (
            "Extract the primary skill/trade as a short lowercase English string. "
            "Examples: tile_work, painting, electrical, plumbing, driving, masonry, "
            "carpentry, welding, domestic_work, security, factory_work, whitewash, "
            "waterproofing. Return a single string."
        ),
    },
    {
        "index": 1,
        "key": "secondary_skills",
        "extraction_hint": (
            "Extract a list of additional skills beyond the primary skill. "
            "Return as a JSON array of short lowercase strings. "
            'Example: ["whitewash", "waterproofing"]. Return [] if none mentioned.'
        ),
    },
    {
        "index": 2,
        "key": "years_experience",
        "extraction_hint": (
            "Extract the total years of experience as an integer. "
            "If the person says 'around 5' or '3-4 years', use the midpoint. "
            "If they say 'many years' without a number, return 5 as a default."
        ),
    },
    {
        "index": 3,
        "key": "city",
        "extraction_hint": (
            "Extract the city name in English, properly capitalized. "
            "Examples: Pune, Nagpur, Mumbai, Delhi, Bengaluru, Chennai, Hyderabad."
        ),
    },
    {
        "index": 4,
        "key": "district",
        "extraction_hint": (
            "Extract the area, neighborhood, locality, or district name as a string. "
            "Keep it as the person said it — do not translate or normalize."
        ),
    },
    {
        "index": 5,
        "key": "state",
        "extraction_hint": (
            "Extract the Indian state name in English, properly capitalized. "
            "Examples: Maharashtra, Karnataka, Bihar, Uttar Pradesh, Tamil Nadu."
        ),
    },
    {
        "index": 6,
        "key": "willing_to_relocate",
        "extraction_hint": (
            "Return true if the person is willing to travel to or work in another city. "
            "Return false if they want to stay local only."
        ),
    },
    {
        "index": 7,
        "key": "max_travel_km",
        "extraction_hint": (
            "Extract the maximum distance the person is willing to travel, as an integer in kilometers. "
            "If they say 'nearby' or 'local area', return 20. "
            "If they say 'within the city', return 50. "
            "If they say 'same state', return 300. "
            "If they say 'anywhere in India' or similar, return 2000."
        ),
    },
    {
        "index": 8,
        "key": "availability",
        "extraction_hint": (
            "Return one of these exact values based on their answer: "
            "'immediate' if they are available now or looking for work now, "
            "'employed' if they are currently working, "
            "'1_week' if they can start within a week, "
            "'1_month' if they can start within a month."
        ),
    },
    {
        "index": 9,
        "key": "expected_daily_wage",
        "extraction_hint": (
            "Extract the expected daily wage as an integer in Indian Rupees. "
            "If they give a monthly figure, divide by 25 to get daily. "
            "If they say 'market rate' or are unsure, return 500 as a reasonable default."
        ),
    },
    {
        "index": 10,
        "key": "work_type",
        "extraction_hint": (
            "Return exactly one of: 'daily_wage', 'contract', 'permanent', or 'any'. "
            "Map their answer: daily/rozana → daily_wage, contract/theka → contract, "
            "permanent/pakki naukri → permanent, no preference/any → any."
        ),
    },
    {
        "index": 11,
        "key": "preferred_hours",
        "extraction_hint": (
            "Extract preferred working hours as a short string. "
            "Examples: '8am-5pm', 'morning shift', 'flexible', 'full_day', '6am-2pm'. "
            "If no preference, return 'flexible'."
        ),
    },
    {
        "index": 12,
        "key": "name",
        "extraction_hint": (
            "Extract the person's name as a string. "
            "If they say they don't want to share, or give a refusal, return null."
        ),
    },
    {
        "index": 13,
        "key": "biggest_project",
        "extraction_hint": (
            "Extract a brief description of the biggest or most significant project "
            "they have worked on. Return as a string. This goes into the resume work history."
        ),
    },
    {
        "index": 14,
        "key": "previous_employer",
        "extraction_hint": (
            "Extract the name of any company, contractor, or employer they have worked for. "
            "Return as a string. Return null if they have only worked informally or cannot name one."
        ),
    },
    {
        "index": 15,
        "key": "certifications",
        "extraction_hint": (
            "Extract any certificates or formal training programs as a JSON array of strings. "
            'Examples: ["ITI", "Skill India", "NSDC"]. Return [] if none.'
        ),
    },
    {
        "index": 16,
        "key": "tools_equipment",
        "extraction_hint": (
            "Extract a list of tools or equipment the person knows how to use. "
            "Return as a JSON array of strings. "
            'Examples: ["drill machine", "angle grinder", "welding machine"]. Return [] if none.'
        ),
    },
    {
        "index": 17,
        "key": "special_skills",
        "extraction_hint": (
            "Extract any special or unique skills, strengths, or qualities that would "
            "make this worker stand out to an employer. Return as a short descriptive string. "
            "Return null if they say nothing notable."
        ),
    },
    {
        "index": 18,
        "key": "skill_description",
        "extraction_hint": (
            "Extract 2-3 sentences the worker said describing their work, preserving their "
            "own words and style as much as possible. This goes directly into the resume. "
            "Return as a single string."
        ),
    },
    {
        "index": 19,
        "key": "resume_consent",
        "extraction_hint": (
            "Return true if the person agrees to create a profile/resume and start job matching. "
            "Return false if they decline or want to wait."
        ),
    },
]

# Quick lookup by index
_Q_BY_INDEX = {q["index"]: q for q in ONBOARDING_QUESTIONS}


# ─── Bedrock Extraction ───────────────────────────────────────────────────────


async def extract_data_from_answer(
    question: dict,
    answer_text: str,
    language: str,
    question_text: str = "",
) -> any:
    """
    Uses Bedrock to extract structured data from a conversational answer.

    Example:
        Question: "How many years have you been doing this work?"
        Answer: "main kaafi saalon se kaam kar raha hoon, shayad 7-8 saal se"
        Extracted: 7  (integer)

    Workers don't give clean structured answers, but Bedrock can understand
    natural language and return the data we need.

    Args:
        question      — ONBOARDING_QUESTIONS entry
        answer_text   — worker's spoken/transcribed response
        language      — two-letter language code ("hi", "ta", etc.)
        question_text — the actual question as asked (used for context)
    """
    bedrock = get_bedrock_client()

    extraction_prompt = f"""Extract specific information from this worker's answer.

Question that was asked: {question_text or "(see extraction instruction)"}
Worker's answer: {answer_text}
Language of answer: {language}

Extraction instruction: {question["extraction_hint"]}

Return ONLY the extracted value with no explanation, no extra text.
If you cannot extract a clear value, return null.
Examples of correct output format based on the extraction hint."""

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "temperature": 0.1,  # Low temperature = consistent, predictable extraction
                "messages": [{"role": "user", "content": extraction_prompt}],
            }
        )
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()

    loop = asyncio.get_event_loop()
    raw_value = await loop.run_in_executor(None, call_bedrock)

    # Parse the extracted value based on what type we expect
    try:
        # Try JSON first (for arrays and booleans)
        parsed = json.loads(raw_value)
        return parsed
    except (json.JSONDecodeError, TypeError):
        # Return as string (for names, cities, descriptions)
        if raw_value.lower() == "null":
            return None
        return raw_value


# ─── Conversation Response Generation ────────────────────────────────────────


async def generate_next_question(
    session: dict,
    question: dict,
    language: str,
    conversation_history: list,
    question_text: str,
) -> str:
    """
    Generates the next question using Bedrock.
    The question is phrased naturally based on what the worker has already said.

    Instead of asking the same scripted question every time, Bedrock adapts:
    - If the worker mentioned their city in passing, don't ask for city again
    - Acknowledge what they just said before asking the next question
    - Keep the tone friendly and local
    """
    bedrock = get_bedrock_client()

    collected_so_far = session["onboarding"]["collected_data"]
    questions_answered = session["onboarding"]["questions_answered"]

    system_prompt = """You are a friendly local person helping a blue-collar worker in India find work.
You are asking them questions to build their job profile.

Rules:
- Ask ONLY ONE question at a time
- Speak in the worker's language naturally — if they spoke Hindi, respond in Hindi
- Acknowledge what they said before asking the next question
- Be warm and encouraging — these workers may never have used a job app before
- Keep responses SHORT — 2-3 sentences maximum
- Do not use formal or corporate language
- Do not mention that you are an AI or a software system"""

    # Build conversation history for context
    messages = []
    for turn in conversation_history[-6:]:  # last 6 turns for context
        messages.append(
            {
                "role": turn["role"],
                "content": turn["content"],
            }
        )

    user_message = f"""The worker just answered. Now ask them this question naturally:
"{question_text}"

Information collected so far: {json.dumps(collected_so_far, ensure_ascii=False)}
Questions answered so far: {questions_answered} out of {len(ONBOARDING_QUESTIONS)}
Language to respond in: {language}

Generate a warm, natural response that acknowledges their last answer and then asks the next question."""

    messages.append({"role": "user", "content": user_message})

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0.7,
                "system": system_prompt,
                "messages": messages,
            }
        )
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_bedrock)


# ─── Resume Generation ────────────────────────────────────────────────────────


async def generate_resume_text(profile_data: dict, language: str) -> str:
    """
    Generates a professional resume text from the collected profile data.
    This text is then formatted into a PDF.
    """
    bedrock = get_bedrock_client()

    prompt = f"""Create a professional resume for a blue-collar worker in India.

Worker's Profile Data:
{json.dumps(profile_data, ensure_ascii=False, indent=2)}

Create a clean, professional resume with these sections:
1. WORKER PROFILE (name if provided, contact via JobSathi platform, location)
2. SKILLS (primary skill prominently, secondary skills listed)
3. EXPERIENCE (years of experience, biggest project, previous employers)
4. CERTIFICATIONS & TRAINING (if any)
5. ADDITIONAL INFORMATION (tools, special skills, availability, expected wage)

Important:
- Write in simple, clear English suitable for Indian employers
- Emphasize practical skills and hands-on experience
- Do not make up any information — only use what is provided
- Keep it to one page
- Make it look professional — this may be the worker's first ever resume

Return only the resume text, formatted with clear sections."""

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_bedrock)


async def generate_resume_pdf(profile_data: dict, worker_id: str, language: str) -> str:
    """
    Generates a PDF resume and saves it to S3.
    Returns the S3 key.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.colors import HexColor
    import io

    # Generate the resume text via Bedrock
    resume_text = await generate_resume_text(profile_data, language)

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    header_style = ParagraphStyle(
        "Header",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=HexColor("#0F1B2D"),
        spaceAfter=6,
    )
    subheader_style = ParagraphStyle(
        "SubHeader",
        parent=styles["Normal"],
        fontSize=11,
        textColor=HexColor("#FF6B00"),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=HexColor("#0F1B2D"),
        spaceBefore=12,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=4,
        leading=14,
    )

    name = profile_data.get("name", "Worker")
    skill = profile_data.get("primary_skill", "").replace("_", " ").title()
    city = profile_data.get("city", "")
    state = profile_data.get("state", "")

    story.append(Paragraph(name or "Blue-Collar Professional", header_style))
    story.append(
        Paragraph(f"{skill} | {city}, {state} | JobSathi Platform", subheader_style)
    )
    story.append(Spacer(1, 0.1 * inch))

    for line in resume_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.05 * inch))
        elif line.isupper() or line.endswith(":"):
            story.append(Paragraph(line, section_style))
        else:
            story.append(Paragraph(line, body_style))

    story.append(Spacer(1, 0.3 * inch))
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=8, textColor=HexColor("#6B7A8D")
    )
    story.append(
        Paragraph(
            "Generated by JobSathi | Voice-First AI Job Platform | Built on AWS",
            footer_style,
        )
    )

    doc.build(story)

    from core.config import get_s3_client

    s3 = get_s3_client()
    s3_key = f"profiles/resumes/{worker_id}/resume.pdf"
    pdf_bytes = buffer.getvalue()

    def upload():
        s3.put_object(
            Bucket=settings.S3_AUDIO_BUCKET,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upload)

    return s3_key


# ─── Save Profile Field to DB ─────────────────────────────────────────────────

# Columns that accept a direct scalar UPDATE
_FIELD_COLUMN_MAP = {
    "primary_skill": "primary_skill",
    "years_experience": "years_experience",
    "city": "city",
    "district": "district",
    "state": "state",
    "willing_to_relocate": "willing_to_relocate",
    "max_travel_km": "max_travel_km",
    "availability": "availability",
    "expected_daily_wage": "expected_daily_wage",
    "work_type": "work_type",
    "preferred_hours": "preferred_hours",
    "name": "name",
    "biggest_project": "biggest_project",
    "previous_employer": "previous_employer",
    "special_skills": "special_skills",
    "skill_description": "skill_description",
    "questions_answered": "questions_answered",
    "profile_complete": "profile_complete",
}


async def save_profile_field(worker_id: str, field_key: str, value):
    """
    Saves a single extracted field to worker_profiles in RDS.
    Called immediately after each question is answered (incremental persistence).
    If the connection drops mid-conversation, nothing is lost.
    """
    if value is None:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure the profile row exists
        await conn.execute(
            "INSERT INTO worker_profiles (worker_id) VALUES ($1) ON CONFLICT DO NOTHING",
            worker_id,
        )

        if field_key == "secondary_skills" and isinstance(value, list):
            await conn.execute(
                "UPDATE worker_profiles SET secondary_skills = $1, updated_at = NOW() WHERE worker_id = $2",
                value,
                worker_id,
            )
        elif field_key == "certifications" and isinstance(value, list):
            await conn.execute(
                "UPDATE worker_profiles SET certifications = $1::text[], updated_at = NOW() WHERE worker_id = $2",
                value,
                worker_id,
            )
        elif field_key == "tools_equipment" and isinstance(value, list):
            # tools_equipment is stored in the JSON skill_description field or as text[]
            # We serialise to JSON string for simplicity (no schema change needed)
            await conn.execute(
                "UPDATE worker_profiles SET skill_description = COALESCE(skill_description, '') || $1, updated_at = NOW() WHERE worker_id = $2",
                f"\nTools: {', '.join(value)}",
                worker_id,
            )
        else:
            column = _FIELD_COLUMN_MAP.get(field_key)
            if column:
                await conn.execute(
                    f"UPDATE worker_profiles SET {column} = $1, updated_at = NOW() WHERE worker_id = $2",
                    value,
                    worker_id,
                )


# ─── Main function called by orchestrator ────────────────────────────────────


async def handle_onboarding_message(
    text: str,
    session: dict,
    worker_id: str,
    phone_number: str,
) -> Tuple[str, dict]:
    """
    Main entry point called by the orchestrator for onboarding interactions.

    Flow:
        1. Get current question index from session
        2. Extract data from the worker's answer to the PREVIOUS question
        3. Save extracted data to RDS immediately
        4. Update session with new data
        5. Fetch next question text from DB (in worker's language)
        6. Generate a natural response via Bedrock
        7. Return (response_text, updated_session)
    """
    onboarding_state = session["onboarding"]
    current_index = onboarding_state["current_question_index"]
    language = session.get("language", "hi")

    # ── Step 1: Extract data from the PREVIOUS answer ─────────────────────────
    if current_index > 0 and text:
        prev_q = _Q_BY_INDEX[current_index - 1]
        prev_q_text = await get_question_text(current_index - 1, language) or ""
        extracted_value = await extract_data_from_answer(
            prev_q, text, language, prev_q_text
        )

        if extracted_value is not None:
            session["onboarding"]["collected_data"][prev_q["key"]] = extracted_value
            await save_profile_field(worker_id, prev_q["key"], extracted_value)

    # ── Step 2: Update questions-answered counter ─────────────────────────────
    session["onboarding"]["questions_answered"] = current_index
    await save_profile_field(worker_id, "questions_answered", current_index)

    # ── Step 3: Check if all 20 questions are done ────────────────────────────
    if current_index >= len(ONBOARDING_QUESTIONS):
        return await complete_onboarding(session, worker_id, language)

    # ── Step 4: Fetch question text for worker's language ─────────────────────
    next_q = _Q_BY_INDEX[current_index]
    next_q_text = await get_question_text(current_index, language)
    if not next_q_text:
        # Hard fallback — should never happen after seed_questions.py is run
        next_q_text = (
            await get_question_text(current_index, "en") or "Next question unavailable."
        )

    # ── Step 5: Load conversation history for context ─────────────────────────
    conversation_history = await get_recent_conversation(
        worker_id, session["session_id"], limit=6
    )

    # ── Step 6: Generate the natural response ─────────────────────────────────
    if current_index == 0:
        # First message — warm introduction + first question
        if language == "hi":
            response = (
                "नमस्ते! मैं JobSathi हूँ। मैं आपकी नौकरी ढूंढने में मदद करूँगा। "
                f"बस कुछ सवाल पूछूँगा। {next_q_text}"
            )
        else:
            response = (
                f"Hello! I am JobSathi. I will help you find work. "
                f"I'll ask you a few questions. {next_q_text}"
            )
    else:
        response = await generate_next_question(
            session, next_q, language, conversation_history, next_q_text
        )

    # ── Step 7: Advance question index ────────────────────────────────────────
    session["onboarding"]["current_question_index"] = current_index + 1

    return response, session


async def complete_onboarding(
    session: dict, worker_id: str, language: str
) -> Tuple[str, dict]:
    """Called when all 20 questions have been answered. Generates the resume."""

    profile_data = session["onboarding"]["collected_data"]

    # Mark profile as complete
    await save_profile_field(worker_id, "profile_complete", True)

    # Generate PDF resume (non-blocking — failure doesn't break onboarding)
    try:
        s3_key = await generate_resume_pdf(profile_data, worker_id, language)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE worker_profiles SET resume_s3_key = $1, resume_generated_at = NOW() WHERE worker_id = $2",
                s3_key,
                worker_id,
            )
        resume_message = (
            " आपका रेज़्यूमे बन गया है।"
            if language == "hi"
            else " Your resume has been created."
        )
    except Exception as e:
        print(f"Resume generation error (non-fatal): {e}")
        resume_message = ""

    # Hand off to job matching agent
    session["current_agent"] = "matching"
    session["onboarding"]["complete"] = True

    if language == "hi":
        response = (
            f"बहुत बढ़िया! आपकी पूरी प्रोफाइल बन गई है।{resume_message} "
            "अब मैं आपके लिए नौकरियां ढूंढता हूँ। क्या आप तैयार हैं?"
        )
    else:
        response = (
            f"Excellent! Your complete profile has been created.{resume_message} "
            "Now let me find jobs for you. Are you ready?"
        )

    return response, session
