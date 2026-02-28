"""
agents/onboarding_agent.py
Agent 2: Onboarding Agent

Responsibilities:
  1. Ask 20 questions conversationally to build a complete worker profile
  2. Extract structured data from conversational answers (via Bedrock)
  3. Save each answer immediately to RDS (incremental persistence)
  4. Generate a PDF resume once all questions are answered

The 20 Questions (asked one at a time, conversationally):
  1.  What work do you do? (primary skill)
  2.  Do you do any other type of work? (secondary skills)
  3.  How many years have you been doing this work?
  4.  Which city do you currently live in?
  5.  Which district/area of the city?
  6.  Are you willing to travel or work in another city?
  7.  How far are you willing to travel? (km)
  8.  Are you currently working somewhere?
  9.  When can you start work? (availability)
  10. How much do you expect to earn per day? (wage)
  11. Do you prefer daily wage, contract, or permanent work?
  12. What hours do you prefer to work?
  13. What is your name? (optional)
  14. Do you have a phone number family can be reached at? (emergency)
  15. What is the biggest project you have worked on?
  16. Have you worked with any well-known company or contractor?
  17. Do you have any certificates or training? (e.g., ITI)
  18. What tools or equipment do you know how to use?
  19. Is there anything special about your work that employers should know?
  20. Would you like us to create a resume/profile for you right now?
"""

import json
import asyncio
from typing import Optional, Tuple
from core.config import get_bedrock_client, settings
from core.database import get_pool, save_conversation_turn, get_recent_conversation
from core.session import get_session, update_session_field, save_session


# ─── The 20 Questions ─────────────────────────────────────────────────────────
# Each question has:
#   key: the field name saved to the database
#   question_hi: what to ask in Hindi (default)
#   question_en: English fallback
#   extraction_hint: tells Bedrock what to extract from the answer

ONBOARDING_QUESTIONS = [
    {
        "index": 0,
        "key": "primary_skill",
        "question_hi": "आप कौन सा काम करते हैं? जैसे टाइल का काम, पेंटिंग, बिजली का काम, प्लंबिंग, ड्राइविंग?",
        "question_en": "What kind of work do you do? For example: tile work, painting, electrical, plumbing, driving?",
        "extraction_hint": "Extract the primary skill/trade as a short lowercase string like: tile_work, painting, electrical, plumbing, driving, masonry, carpentry, welding, domestic_work, security, factory_work"
    },
    {
        "index": 1,
        "key": "secondary_skills",
        "question_hi": "क्या आप कोई और काम भी करते हैं?",
        "question_en": "Do you do any other type of work as well?",
        "extraction_hint": "Extract a list of additional skills. Return as JSON array like: [\"whitewash\", \"waterproofing\"]. Return empty array [] if none."
    },
    {
        "index": 2,
        "key": "years_experience",
        "question_hi": "आप कितने सालों से यह काम कर रहे हैं?",
        "question_en": "How many years have you been doing this work?",
        "extraction_hint": "Extract a number (integer). If they say 'around 5' or 'about 3-4', use the middle value."
    },
    {
        "index": 3,
        "key": "city",
        "question_hi": "आप अभी किस शहर में रहते हैं?",
        "question_en": "Which city do you currently live in?",
        "extraction_hint": "Extract the city name in English, properly capitalized. E.g., Pune, Nagpur, Mumbai, Delhi, Bengaluru."
    },
    {
        "index": 4,
        "key": "district",
        "question_hi": "शहर का कौन सा इलाका या मोहल्ला?",
        "question_en": "Which area or neighborhood of the city?",
        "extraction_hint": "Extract the area/neighborhood/district name as a string."
    },
    {
        "index": 5,
        "key": "state",
        "question_hi": "आप किस राज्य में हैं?",
        "question_en": "Which state are you in?",
        "extraction_hint": "Extract the Indian state name in English. E.g., Maharashtra, Karnataka, Bihar, Uttar Pradesh."
    },
    {
        "index": 6,
        "key": "willing_to_relocate",
        "question_hi": "क्या आप दूसरे शहर में जाकर काम कर सकते हैं?",
        "question_en": "Are you willing to travel to or work in another city?",
        "extraction_hint": "Return true if yes/willing, false if no/not willing."
    },
    {
        "index": 7,
        "key": "max_travel_km",
        "question_hi": "आप कितने किलोमीटर तक जाने के लिए तैयार हैं?",
        "question_en": "How far are you willing to travel for work? In kilometers.",
        "extraction_hint": "Extract a number in kilometers. If they say 'nearby' or 'local', use 20. If 'city', use 50. If 'state', use 300. If 'anywhere', use 1000."
    },
    {
        "index": 8,
        "key": "availability",
        "question_hi": "आप अभी काम कर रहे हैं, या काम की तलाश में हैं?",
        "question_en": "Are you currently working somewhere, or are you looking for work?",
        "extraction_hint": "Return one of: 'immediate' (looking now), 'employed' (currently working), '1_week', '1_month'."
    },
    {
        "index": 9,
        "key": "expected_daily_wage",
        "question_hi": "आप रोज़ाना कितने रुपये की उम्मीद करते हैं?",
        "question_en": "How much do you expect to earn per day, in rupees?",
        "extraction_hint": "Extract a number in Indian Rupees (integer). If they give monthly, divide by 25."
    },
    {
        "index": 10,
        "key": "work_type",
        "question_hi": "आप किस तरह का काम पसंद करते हैं — रोज़ का काम, कॉन्ट्रैक्ट, या पक्की नौकरी?",
        "question_en": "Do you prefer daily wage work, contract work, or a permanent job?",
        "extraction_hint": "Return one of: 'daily_wage', 'contract', 'permanent', 'any'."
    },
    {
        "index": 11,
        "key": "preferred_hours",
        "question_hi": "आप कितने घंटे काम करना पसंद करते हैं और कौन सा समय?",
        "question_en": "How many hours do you prefer to work, and what time of day?",
        "extraction_hint": "Extract as a short string like: '8am-5pm', 'morning', 'flexible', 'full_day'. Include hours if mentioned."
    },
    {
        "index": 12,
        "key": "name",
        "question_hi": "आपका नाम क्या है? (यह वैकल्पिक है, आप चाहें तो बता सकते हैं)",
        "question_en": "What is your name? (This is optional — you don't have to share if you prefer not to)",
        "extraction_hint": "Extract the person's name as a string. If they say 'don't want to share' or similar, return null."
    },
    {
        "index": 13,
        "key": "biggest_project",
        "question_hi": "आपने अब तक का सबसे बड़ा काम कौन सा किया है?",
        "question_en": "What is the biggest or most important project you have worked on?",
        "extraction_hint": "Extract a brief description as a string. This goes into the resume work history."
    },
    {
        "index": 14,
        "key": "previous_employer",
        "question_hi": "क्या आपने किसी कंपनी या बड़े ठेकेदार के साथ काम किया है?",
        "question_en": "Have you worked with any company or well-known contractor?",
        "extraction_hint": "Extract employer/contractor name as a string, or null if none."
    },
    {
        "index": 15,
        "key": "certifications",
        "question_hi": "क्या आपके पास कोई सर्टिफिकेट या ट्रेनिंग है? जैसे आईटीआई?",
        "question_en": "Do you have any certificates or training? For example, ITI, skill development courses?",
        "extraction_hint": "Extract as a list of certifications. Return JSON array. Empty array [] if none."
    },
    {
        "index": 16,
        "key": "tools_equipment",
        "question_hi": "आप कौन से औज़ार या मशीन चलाना जानते हैं?",
        "question_en": "What tools or equipment do you know how to use?",
        "extraction_hint": "Extract as a list of tools/equipment. Return JSON array."
    },
    {
        "index": 17,
        "key": "special_skills",
        "question_hi": "आपके काम में कोई खास बात है जो नियोक्ता को पता होनी चाहिए?",
        "question_en": "Is there anything special about your work that employers should know?",
        "extraction_hint": "Extract as a brief descriptive string for the resume."
    },
    {
        "index": 18,
        "key": "skill_description",
        "question_hi": "अपने काम के बारे में दो-तीन वाक्य बोलें जो हम आपके रेज़्यूमे में लिख सकें।",
        "question_en": "Tell us two or three sentences about your work that we can write in your resume.",
        "extraction_hint": "Extract the description as a complete string, preserving their own words as much as possible."
    },
    {
        "index": 19,
        "key": "resume_consent",
        "question_hi": "क्या आप चाहते हैं कि हम अभी आपका रेज़्यूमे बनाएं और नौकरियां ढूंढें?",
        "question_en": "Would you like us to create your resume and start finding jobs for you right now?",
        "extraction_hint": "Return true if yes, false if no."
    },
]


# ─── Bedrock Extraction ───────────────────────────────────────────────────────

async def extract_data_from_answer(
    question: dict,
    answer_text: str,
    language: str
) -> any:
    """
    Uses Bedrock to extract structured data from a conversational answer.

    Example:
        Question: "How many years have you been doing this work?"
        Answer: "main kaafi saalon se kaam kar raha hoon, shayad 7-8 saal se"
        Extracted: 7  (integer)

    This is the key insight: workers don't give clean structured answers,
    but Bedrock can understand natural language and return the data we need.
    """
    bedrock = get_bedrock_client()

    extraction_prompt = f"""Extract specific information from this worker's answer.

Question that was asked: {question['question_en']}
Worker's answer: {answer_text}
Language of answer: {language}

Extraction instruction: {question['extraction_hint']}

Return ONLY the extracted value with no explanation, no extra text.
If you cannot extract a clear value, return null.
Examples of correct output format based on the extraction hint."""

    def call_bedrock():
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "temperature": 0.1,  # Low temperature = consistent, predictable extraction
            "messages": [
                {"role": "user", "content": extraction_prompt}
            ]
        })
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
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
    conversation_history: list
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
        messages.append({
            "role": turn["role"],
            "content": turn["content"]
        })

    next_question_text = question.get(f"question_{language}", question["question_en"])

    user_message = f"""The worker just answered. Now ask them this question naturally:
"{next_question_text}"

Information collected so far: {json.dumps(collected_so_far, ensure_ascii=False)}
Questions answered so far: {questions_answered} out of 20
Language to respond in: {language}

Generate a warm, natural response that acknowledges their last answer and then asks the next question."""

    messages.append({"role": "user", "content": user_message})

    def call_bedrock():
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "temperature": 0.7,
            "system": system_prompt,
            "messages": messages
        })
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
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

    Returns the resume as formatted text.
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
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        })
        response = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_bedrock)


async def generate_resume_pdf(profile_data: dict, worker_id: str, language: str) -> str:
    """
    Generates a PDF resume and saves it to S3.
    Returns the S3 key.

    Uses reportlab for PDF generation (pip install reportlab).
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
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch
    )

    styles = getSampleStyleSheet()
    story = []

    # Header
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=HexColor('#0F1B2D'),
        spaceAfter=6,
    )
    subheader_style = ParagraphStyle(
        'SubHeader',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor('#FF6B00'),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=HexColor('#0F1B2D'),
        spaceBefore=12,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4,
        leading=14,
    )

    name = profile_data.get("name", "Worker")
    skill = profile_data.get("primary_skill", "").replace("_", " ").title()
    city = profile_data.get("city", "")
    state = profile_data.get("state", "")

    story.append(Paragraph(name or "Blue-Collar Professional", header_style))
    story.append(Paragraph(f"{skill} | {city}, {state} | JobSathi Platform", subheader_style))
    story.append(Spacer(1, 0.1*inch))

    # Add resume sections from generated text
    for line in resume_text.split('\n'):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.05*inch))
        elif line.isupper() or line.endswith(':'):
            story.append(Paragraph(line, section_style))
        else:
            story.append(Paragraph(line, body_style))

    # Footer
    story.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8,
                                   textColor=HexColor('#6B7A8D'))
    story.append(Paragraph("Generated by JobSathi | Voice-First AI Job Platform | Built on AWS", footer_style))

    doc.build(story)

    # Upload to S3
    s3 = get_s3_client()  # noqa
    from core.config import get_s3_client as _s3
    s3 = _s3()
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

async def save_profile_field(worker_id: str, field_key: str, value):
    """
    Saves a single extracted field to worker_profiles in RDS.
    Called immediately after each question is answered.
    This is the incremental persistence — no data is lost if connection drops.
    """
    if value is None:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check if profile row exists
        exists = await conn.fetchval(
            "SELECT id FROM worker_profiles WHERE worker_id = $1", worker_id
        )

        if not exists:
            # Create the profile row first
            await conn.execute(
                "INSERT INTO worker_profiles (worker_id) VALUES ($1) ON CONFLICT DO NOTHING",
                worker_id
            )

        # Update the specific field
        # Note: We build the query dynamically — safe because field_key comes
        # from our own ONBOARDING_QUESTIONS list, not from user input
        if field_key == "secondary_skills" and isinstance(value, list):
            await conn.execute(
                f"UPDATE worker_profiles SET secondary_skills = $1, updated_at = NOW() WHERE worker_id = $2",
                value, worker_id
            )
        elif field_key == "certifications" and isinstance(value, list):
            await conn.execute(
                f"UPDATE worker_profiles SET certifications = $1::text[], updated_at = NOW() WHERE worker_id = $2",
                value, worker_id
            )
        else:
            # For simple fields, map the key to a column
            FIELD_COLUMN_MAP = {
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
                "name": "name",
                "skill_description": "skill_description",
                "questions_answered": "questions_answered",
                "profile_complete": "profile_complete",
            }
            column = FIELD_COLUMN_MAP.get(field_key)
            if column:
                await conn.execute(
                    f"UPDATE worker_profiles SET {column} = $1, updated_at = NOW() WHERE worker_id = $2",
                    value, worker_id
                )


# ─── Main function called by orchestrator ────────────────────────────────────

async def handle_onboarding_message(
    text: str,
    session: dict,
    worker_id: str,
    phone_number: str
) -> Tuple[str, dict]:
    """
    Main entry point called by the orchestrator for onboarding interactions.

    Flow:
        1. Get current question index from session
        2. Extract data from the worker's answer to the PREVIOUS question
        3. Save extracted data to RDS
        4. Update session with new data
        5. Generate the NEXT question
        6. Return response text + updated session

    Returns:
        (response_text, updated_session)
    """
    onboarding_state = session["onboarding"]
    current_index = onboarding_state["current_question_index"]
    language = session.get("language", "hi")

    # If this isn't the very first message, extract data from their answer
    if current_index > 0 and text:
        prev_question = ONBOARDING_QUESTIONS[current_index - 1]
        extracted_value = await extract_data_from_answer(prev_question, text, language)

        if extracted_value is not None:
            # Save to Redis session immediately
            session["onboarding"]["collected_data"][prev_question["key"]] = extracted_value
            # Save to RDS immediately (incremental persistence)
            await save_profile_field(worker_id, prev_question["key"], extracted_value)

    # Update questions answered count
    questions_answered = current_index
    session["onboarding"]["questions_answered"] = questions_answered
    await save_profile_field(worker_id, "questions_answered", questions_answered)

    # Check if all questions are done
    if current_index >= len(ONBOARDING_QUESTIONS):
        return await complete_onboarding(session, worker_id, language)

    # Get the next question to ask
    next_question = ONBOARDING_QUESTIONS[current_index]

    # Load conversation history for context
    conversation_history = await get_recent_conversation(
        worker_id, session["session_id"], limit=6
    )

    # Generate natural response with next question
    if current_index == 0:
        # First message — introduce and ask first question
        if language == "hi":
            response = f"नमस्ते! मैं JobSathi हूँ। मैं आपकी नौकरी ढूंढने में मदद करूँगा। बस कुछ सवाल पूछूँगा। {next_question['question_hi']}"
        else:
            response = f"Hello! I am JobSathi. I will help you find work. I'll ask you a few questions. {next_question['question_en']}"
    else:
        response = await generate_next_question(
            session, next_question, language, conversation_history
        )

    # Move to next question index
    session["onboarding"]["current_question_index"] = current_index + 1

    return response, session


async def complete_onboarding(session: dict, worker_id: str, language: str) -> Tuple[str, dict]:
    """Called when all 20 questions have been answered. Generates the resume."""

    profile_data = session["onboarding"]["collected_data"]

    # Mark profile as complete in DB
    await save_profile_field(worker_id, "profile_complete", True)

    # Generate PDF resume
    try:
        s3_key = await generate_resume_pdf(profile_data, worker_id, language)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE worker_profiles SET resume_s3_key = $1, resume_generated_at = NOW() WHERE worker_id = $2",
                s3_key, worker_id
            )
        resume_message = " आपका रेज़्यूमे बन गया है।" if language == "hi" else " Your resume has been created."
    except Exception as e:
        print(f"Resume generation error: {e}")
        resume_message = ""

    # Switch agent to job matching
    session["current_agent"] = "matching"
    session["onboarding"]["complete"] = True

    if language == "hi":
        response = f"बहुत बढ़िया! आपकी पूरी प्रोफाइल बन गई है।{resume_message} अब मैं आपके लिए नौकरियां ढूंढता हूँ। क्या आप तैयार हैं?"
    else:
        response = f"Excellent! Your complete profile has been created.{resume_message} Now let me find jobs for you. Are you ready?"

    return response, session
