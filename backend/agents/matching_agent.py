"""
agents/matching_agent.py
Agent 3: Job Matching Agent

Responsibilities:
  1. Take the worker's completed profile
  2. Query Jooble and Adzuna APIs for real job listings
  3. Cache results in RDS to avoid re-fetching
  4. Present jobs one at a time as spoken descriptions
  5. Handle "yes/no/next/more details" responses from worker

Job APIs used:
  - Adzuna: https://developer.adzuna.com  (free tier: 250 calls/month)
  - Jooble: https://jooble.org/api/  (free tier available, apply at jooble.org/api)

Adzuna covers India well for formal jobs.
Jooble aggregates from many sources including Indian job boards.
"""

import json
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from core.config import settings, get_bedrock_client
from core.database import get_pool, get_worker_profile
from core.session import save_session
from agents.application_agent import handle_job_application


# ─── Skill → Search Query Mapping ────────────────────────────────────────────
# Maps our internal skill codes to search terms that job APIs understand

SKILL_TO_SEARCH_TERMS = {
    "tile_work": ["tile worker", "tile fitter", "flooring worker"],
    "painting": ["painter", "house painter", "commercial painter"],
    "electrical": ["electrician", "electrical worker", "wiring technician"],
    "plumbing": ["plumber", "plumbing technician"],
    "masonry": ["mason", "bricklayer", "construction worker"],
    "carpentry": ["carpenter", "furniture maker", "woodworker"],
    "welding": ["welder", "fabricator", "metal worker"],
    "driving": ["driver", "delivery driver", "truck driver"],
    "domestic_work": ["domestic helper", "housekeeper", "maid"],
    "security": ["security guard", "watchman"],
    "factory_work": ["factory worker", "production worker", "assembly worker"],
    "civil_construction": ["construction worker", "site worker", "civil worker"],
}

# Maps Indian state names to Adzuna location parameters
STATE_TO_ADZUNA_LOCATION = {
    "Maharashtra": "Maharashtra",
    "Karnataka": "Karnataka",
    "Tamil Nadu": "Tamil Nadu",
    "Delhi": "New Delhi",
    "Uttar Pradesh": "Uttar Pradesh",
    "Gujarat": "Gujarat",
    "Rajasthan": "Rajasthan",
    "West Bengal": "West Bengal",
    "Bihar": "Bihar",
    # Add more as needed
}


# ─── Adzuna API ───────────────────────────────────────────────────────────────


async def fetch_jobs_adzuna(
    skill: str, city: str, state: str, min_salary: int = None, limit: int = 10
) -> List[dict]:
    """
    Fetch jobs from Adzuna API.

    Adzuna India endpoint: https://api.adzuna.com/v1/api/jobs/in/search/1

    Free tier: 250 API calls/month
    Sign up at: https://developer.adzuna.com/signup
    """
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_API_KEY:
        print("⚠ Adzuna credentials not set. Skipping Adzuna.")
        return []

    search_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    query = " OR ".join(f'"{term}"' for term in search_terms[:2])

    params = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_API_KEY,
        "results_per_page": limit,
        "what": query,
        "where": city or state or "India",
        "content-type": "application/json",
        "sort_by": "relevance",
    }

    if min_salary:
        params["salary_min"] = min_salary

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                "https://api.adzuna.com/v1/api/jobs/in/search/1", params=params
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for job in data.get("results", []):
                # Parse salary
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")

                # Convert annual salary to daily (÷ 300 working days)
                daily_min = int(salary_min / 300) if salary_min else None
                daily_max = int(salary_max / 300) if salary_max else None

                jobs.append(
                    {
                        "source": "adzuna",
                        "external_id": job.get("id", ""),
                        "title": job.get("title", ""),
                        "company": job.get("company", {}).get("display_name", ""),
                        "location": job.get("location", {}).get("display_name", ""),
                        "city": city,
                        "state": state,
                        "salary_min": daily_min,
                        "salary_max": daily_max,
                        "description": job.get("description", "")[:500],  # truncate
                        "url": job.get("redirect_url", ""),
                        "job_type": "full_time",
                        "fetched_at": datetime.utcnow().isoformat(),
                    }
                )
            return jobs

        except httpx.HTTPError as e:
            print(f"Adzuna API error: {e}")
            return []


# ─── Jooble API ───────────────────────────────────────────────────────────────


async def fetch_jobs_jooble(
    skill: str, city: str, state: str, limit: int = 10
) -> List[dict]:
    """
    Fetch jobs from Jooble API.

    Jooble endpoint: https://jooble.org/api/{your_api_key}
    Apply for access: https://jooble.org/api/about

    Jooble is a job aggregator — it pulls from Naukri, Monster, LinkedIn, and
    hundreds of Indian job boards. Good coverage for blue-collar roles.
    """
    if not settings.JOOBLE_API_KEY:
        print("⚠ Jooble API key not set. Skipping Jooble.")
        return []

    search_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    keywords = " ".join(search_terms[:2])

    payload = {
        "keywords": keywords,
        "location": f"{city}, {state}, India",
        "page": 1,
        "ResultOnPage": limit,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"https://jooble.org/api/{settings.JOOBLE_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for job in data.get("jobs", []):
                # Jooble salary is usually a string like "₹15,000 - ₹25,000"
                salary_str = job.get("salary", "")
                salary_min, salary_max = parse_salary_string(salary_str)

                jobs.append(
                    {
                        "source": "jooble",
                        "external_id": job.get("id", ""),
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "location": job.get("location", ""),
                        "city": city,
                        "state": state,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "description": job.get("snippet", "")[:500],
                        "url": job.get("link", ""),
                        "job_type": job.get("type", "full_time"),
                        "fetched_at": datetime.utcnow().isoformat(),
                    }
                )
            return jobs

        except httpx.HTTPError as e:
            print(f"Jooble API error: {e}")
            return []


def parse_salary_string(salary_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse salary strings like '₹15,000 - ₹25,000' into (15000, 25000)."""
    import re

    numbers = re.findall(r"[\d,]+", salary_str.replace(",", ""))
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    elif len(numbers) == 1:
        val = int(numbers[0])
        return val, val
    return None, None


# ─── Cache Jobs in RDS ────────────────────────────────────────────────────────


async def cache_jobs(jobs: List[dict]):
    """
    Save fetched jobs to the jobs_cache table in RDS.
    Cache expires after 24 hours.
    Next worker searching for the same skill+city gets results instantly.
    """
    if not jobs:
        return

    pool = await get_pool()
    expires_at = datetime.utcnow() + timedelta(hours=24)

    async with pool.acquire() as conn:
        for job in jobs:
            await conn.execute(
                """
                INSERT INTO jobs_cache
                    (external_id, source, title, company, location, city, state,
                     salary_min, salary_max, description, url, job_type, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT DO NOTHING
            """,
                job["external_id"],
                job["source"],
                job["title"],
                job["company"],
                job["location"],
                job["city"],
                job["state"],
                job["salary_min"],
                job["salary_max"],
                job["description"],
                job["url"],
                job["job_type"],
                expires_at,
            )


async def get_cached_jobs(skill: str, city: str) -> List[dict]:
    """Returns non-expired cached jobs for this skill+city combination."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM jobs_cache
            WHERE city ILIKE $1
            AND (title ILIKE $2 OR title ILIKE $3)
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY fetched_at DESC
            LIMIT 15
        """,
            f"%{city}%",
            f"%{skill.replace('_', ' ')}%",
            f"%{SKILL_TO_SEARCH_TERMS.get(skill, [skill])[0]}%",
        )
        return [dict(r) for r in rows]


# ─── Job Description for Voice ────────────────────────────────────────────────


async def describe_job_in_language(job: dict, language: str, position: int) -> str:
    """
    Uses Bedrock to describe a job naturally in the worker's language.

    Instead of reading out raw job data, Bedrock creates a natural,
    warm description that a friend would give you about a job opportunity.
    """
    bedrock = get_bedrock_client()

    salary_info = ""
    if job.get("salary_min"):
        if job.get("salary_max") and job["salary_max"] != job["salary_min"]:
            salary_info = (
                f"Salary: ₹{job['salary_min']} to ₹{job['salary_max']} per day"
            )
        else:
            salary_info = f"Salary: ₹{job['salary_min']} per day"

    prompt = f"""Describe this job opportunity naturally and warmly in {language} language.
Keep it under 3 sentences. Sound like a helpful friend, not a job portal.

Job details:
- Title: {job.get("title", "")}
- Company: {job.get("company", "") or "a local company"}
- Location: {job.get("location", "")}
- {salary_info}
- Type: {job.get("job_type", "regular work")}
- Brief: {job.get("description", "")[:200]}

This is option number {position} for the worker.
End by asking: "Kya aap is kaam mein interested hain?" (or equivalent in their language)
Language code: {language}"""

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0.6,
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


# ─── Intent Detection for Matching Agent ─────────────────────────────────────


async def detect_job_response_intent(text: str, language: str) -> str:
    """
    Detects what the worker means in response to a job presentation.

    Returns one of:
        "yes"       — interested in this job
        "no"        — not interested, show next
        "details"   — wants more information
        "stop"      — done looking for now
        "other"     — something else (will be handled as a question)
    """
    bedrock = get_bedrock_client()

    prompt = f"""The worker was just presented with a job opportunity and responded.
Classify their response intent.

Worker's response: "{text}"
Language: {language}

Return ONLY one of these words: yes, no, details, stop, other
- "yes" = they want this job / are interested
- "no" = not interested, want to see next option
- "details" = asking for more information about this specific job
- "stop" = done looking, want to stop
- "other" = asking an unrelated question or unclear"""

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "temperature": 0.0,
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
        return result["content"][0]["text"].strip().lower()

    loop = asyncio.get_event_loop()
    intent = await loop.run_in_executor(None, call_bedrock)
    return intent if intent in ["yes", "no", "details", "stop", "other"] else "other"


# ─── Save Application ─────────────────────────────────────────────────────────


async def save_application(worker_id: str, job_id: str):
    """Records that a worker applied to a job."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO applications (worker_id, job_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """,
            worker_id,
            job_id,
        )


# ─── Main function called by orchestrator ────────────────────────────────────


async def handle_matching_message(
    text: str, session: dict, worker_id: str, phone_number: str
) -> Tuple[str, dict]:
    """
    Main entry point for the job matching agent.

    State machine:
        - If no active search: fetch jobs, present first one
        - If active search: detect yes/no/details, act accordingly
        - If "yes": record application, confirm, present next
        - If "no": present next job
        - If "details": answer question about current job
        - If no more jobs: offer to search again
    """
    language = session.get("language", "hi")
    matching_state = session["matching"]
    profile_data = session["onboarding"]["collected_data"]

    skill = profile_data.get("primary_skill", "")
    city = profile_data.get("city", "")
    state = profile_data.get("state", "")
    min_wage = profile_data.get("expected_daily_wage")

    # ── Case 1: No active search yet, fetch jobs ──
    if not matching_state.get("last_results"):
        # Try cache first
        cached = await get_cached_jobs(skill, city)

        if cached:
            jobs = cached
        else:
            # Fetch from both APIs concurrently
            adzuna_task = fetch_jobs_adzuna(skill, city, state, min_wage)
            jooble_task = fetch_jobs_jooble(skill, city, state)
            adzuna_jobs, jooble_jobs = await asyncio.gather(adzuna_task, jooble_task)

            # Combine and deduplicate by title+company
            all_jobs = adzuna_jobs + jooble_jobs
            seen = set()
            jobs = []
            for job in all_jobs:
                key = (job["title"].lower()[:30], job.get("company", "").lower()[:20])
                if key not in seen:
                    seen.add(key)
                    jobs.append(job)

            # Cache results
            await cache_jobs(jobs)

        if not jobs:
            if language == "hi":
                response = f"मुझे {city} में {skill.replace('_', ' ')} के लिए अभी कोई जॉब नहीं मिली। मैं कल फिर कोशिश करूँगा।"
            else:
                response = f"I couldn't find {skill.replace('_', ' ')} jobs in {city} right now. I will try again tomorrow."
            return response, session

        # Save to session
        session["matching"]["last_results"] = jobs
        session["matching"]["current_job_index"] = 0

        # Present first job
        first_job = jobs[0]
        session["matching"]["current_job_index"] = 1

        description = await describe_job_in_language(first_job, language, 1)

        total = len(jobs)
        if language == "hi":
            intro = f"मुझे आपके लिए {total} नौकरियां मिली हैं। पहला विकल्प सुनिए:\n\n"
        else:
            intro = f"I found {total} jobs for you. Here is the first option:\n\n"

        return intro + description, session

    # ── Case 2: Active search, detect intent ──
    intent = await detect_job_response_intent(text, language)
    current_index = matching_state["current_job_index"]
    all_jobs = matching_state["last_results"]

    if intent == "yes":
        # Worker wants this job — delegate to Application Agent
        selected_job = all_jobs[current_index - 1]
        worker_profile_data = await get_worker_profile(worker_id) or profile_data

        confirmation, application_id = await handle_job_application(
            worker_id=worker_id,
            phone_number=phone_number,
            job=selected_job,
            worker_profile=worker_profile_data,
            language=language,
        )

        # Offer to continue looking at more jobs
        if language == "hi":
            response = f"{confirmation} क्या आप और भी नौकरियां देखना चाहते हैं?"
        else:
            response = f"{confirmation} Would you like to see more jobs?"

        # Advance index so next "no" shows the job after the one just applied to
        session["matching"]["current_job_index"] = current_index

    elif intent == "no" or intent == "other":
        # Show next job
        if current_index >= len(all_jobs):
            if language == "hi":
                response = "आपने सभी उपलब्ध नौकरियां देख ली हैं। क्या मैं नई नौकरियां ढूंढूँ?"
            else:
                response = (
                    "You've seen all available jobs. Should I search for new ones?"
                )
        else:
            next_job = all_jobs[current_index]
            session["matching"]["current_job_index"] = current_index + 1
            response = await describe_job_in_language(
                next_job, language, current_index + 1
            )

    elif intent == "details":
        # Answer question about current job
        current_job = all_jobs[current_index - 1]
        if language == "hi":
            response = f"इस काम के बारे में: {current_job.get('description', 'विवरण उपलब्ध नहीं है')}. कंपनी का नाम {current_job.get('company', 'अज्ञात')} है। क्या आप यह काम करना चाहते हैं?"
        else:
            response = f"About this job: {current_job.get('description', 'No details available')}. Company: {current_job.get('company', 'Unknown')}. Would you like to apply?"

    elif intent == "stop":
        if language == "hi":
            response = "ठीक है। जब भी आप नौकरी देखना चाहें, बस बोलें।"
        else:
            response = "Okay. Whenever you want to look for jobs again, just ask."
        session["matching"]["last_results"] = []

    else:
        response = "मुझे समझ नहीं आया। क्या आप यह नौकरी करना चाहते हैं? हाँ या ना बोलें।"

    await save_session(phone_number, session)
    return response, session
