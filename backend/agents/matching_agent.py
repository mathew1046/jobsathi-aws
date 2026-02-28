"""
agents/matching_agent.py
Agent 3: Job Matching Agent

Responsibilities:
  1. Fetch live jobs from three external APIs concurrently:
       - Adzuna   (https://developer.adzuna.com)
       - Jooble   (https://jooble.org/api/about)
       - SerpAPI  (https://serpapi.com/google-jobs-api)
  2. Normalize all salary figures to daily INR rate (consistent comparison)
  3. Deduplicate across sources using title+company fingerprint
  4. Score each job 0-100 against the worker's profile
  5. Cache results in jobs_cache table (24 h TTL) to avoid re-fetching
  6. Persist every shown/applied job in matched_jobs table (permanent record)
  7. Present jobs one at a time as spoken descriptions via Bedrock
  8. Handle yes / no / details / stop / other responses from worker
  9. Expand search radius to state when city returns < MIN_RESULTS jobs

Salary normalization rules (all stored as daily INR):
  - Annual figure  → ÷ 300 working days
  - Monthly figure → ÷ 25 working days
  - Already daily  → used as-is

Match scoring (0-100):
  +40  primary skill keyword found in job title
  +20  city matches job location
  +15  salary in range (worker's expected wage within 20% of job min)
  +15  experience meets job's implied requirement
  +10  job type matches worker preference
"""

import json
import re
import asyncio
import hashlib
import httpx
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from core.config import settings, get_bedrock_client
from core.database import (
    get_pool,
    upsert_matched_job,
    update_matched_job_status,
    save_application_record,
    get_worker_profile
)
from core.session import save_session
from agents.application_agent import handle_job_application


# ─── Constants ────────────────────────────────────────────────────────────────

MIN_RESULTS = 5  # expand to state search if fewer than this many city results
CACHE_TTL_HOURS = 24  # how long to cache fetched jobs
MAX_JOBS_PER_SOURCE = 10  # cap per API call to stay within free-tier limits


# ─── Skill → Search Query Mapping ────────────────────────────────────────────
# Maps our internal skill codes to search terms that job APIs understand.
# Multiple synonyms improve recall on Jooble/SerpAPI which are keyword-based.

SKILL_TO_SEARCH_TERMS: dict = {
    "tile_work": ["tile worker", "tile fitter", "flooring worker", "tiler"],
    "painting": ["painter", "house painter", "commercial painter", "paint worker"],
    "electrical": ["electrician", "electrical worker", "wiring technician", "wireman"],
    "plumbing": ["plumber", "plumbing technician", "pipe fitter"],
    "masonry": ["mason", "bricklayer", "construction worker", "civil worker"],
    "carpentry": ["carpenter", "furniture maker", "woodworker", "joiner"],
    "welding": ["welder", "fabricator", "metal worker", "arc welder"],
    "driving": ["driver", "delivery driver", "truck driver", "LMV driver"],
    "domestic_work": ["domestic helper", "housekeeper", "maid", "household worker"],
    "security": ["security guard", "watchman", "security officer"],
    "factory_work": [
        "factory worker",
        "production worker",
        "assembly worker",
        "machine operator",
    ],
    "civil_construction": [
        "construction worker",
        "site worker",
        "civil worker",
        "labourer",
    ],
}

# Adzuna maps Indian state names to its location parameter
STATE_TO_ADZUNA_LOCATION: dict = {
    "Maharashtra": "Maharashtra",
    "Karnataka": "Karnataka",
    "Tamil Nadu": "Tamil Nadu",
    "Delhi": "New Delhi",
    "Uttar Pradesh": "Uttar Pradesh",
    "Gujarat": "Gujarat",
    "Rajasthan": "Rajasthan",
    "West Bengal": "West Bengal",
    "Bihar": "Bihar",
    "Madhya Pradesh": "Madhya Pradesh",
    "Andhra Pradesh": "Andhra Pradesh",
    "Telangana": "Telangana",
    "Kerala": "Kerala",
    "Punjab": "Punjab",
    "Haryana": "Haryana",
    "Odisha": "Odisha",
    "Jharkhand": "Jharkhand",
    "Chhattisgarh": "Chhattisgarh",
    "Uttarakhand": "Uttarakhand",
}


# ─── Salary Normalization ─────────────────────────────────────────────────────


def normalize_to_daily_wage(
    amount: Optional[float], period: str = "annual"
) -> Optional[int]:
    """
    Convert any salary figure to a daily wage in INR.

    period values: "annual", "monthly", "daily"
    - Annual figures from Adzuna are divided by 300 working days
    - Monthly figures from Jooble/SERP are divided by 25 working days
    - Daily figures (from explicitly tagged blue-collar jobs) are kept as-is

    Returns None if amount is None or 0.
    """
    if not amount or amount <= 0:
        return None
    amount = float(amount)
    if period == "annual":
        return int(amount / 300)
    if period == "monthly":
        return int(amount / 25)
    return int(amount)  # already daily


def parse_salary_string(salary_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse free-text salary strings from Jooble/SERP into (daily_min, daily_max).

    Handles formats like:
        "₹15,000 - ₹25,000"     → monthly → (600, 1000)
        "Rs 500 per day"         → daily   → (500, 500)
        "12000 monthly"          → monthly → (480, 480)
        "2,00,000 per year"      → annual  → (667, 667)
        "500-700"                → ambiguous → treat as daily for small values
    """
    if not salary_str:
        return None, None

    text = (
        salary_str.lower().replace(",", "").replace("₹", "").replace("rs", "").strip()
    )

    # Detect period
    period = "monthly"  # default for Indian job boards
    if any(w in text for w in ["per day", "/day", "daily", "p.d.", "pd"]):
        period = "daily"
    elif any(
        w in text for w in ["per year", "/year", "annual", "p.a.", "pa", "lpa", "lakh"]
    ):
        period = "annual"

    # Extract numbers
    numbers = re.findall(r"\d+\.?\d*", text)
    if not numbers:
        return None, None

    if "lakh" in text or "lpa" in text:
        # Convert lakh to actual amount (e.g., "3 lpa" → 300000)
        values = [float(n) * 100000 for n in numbers[:2]]
    else:
        values = [float(n) for n in numbers[:2]]

    if len(values) >= 2:
        raw_min, raw_max = values[0], values[1]
    else:
        raw_min = raw_max = values[0]

    # Heuristic: if a "monthly" figure looks like a daily wage (< 2000), keep as daily
    if period == "monthly" and raw_min < 2000:
        period = "daily"

    return (
        normalize_to_daily_wage(raw_min, period),
        normalize_to_daily_wage(raw_max, period),
    )


# ─── Job Fingerprinting (deduplication) ──────────────────────────────────────


def job_fingerprint(title: str, company: str) -> str:
    """
    Creates a stable, short hash for a title+company pair.
    Used to deduplicate jobs that appear in multiple API responses.

    We hash the first 30 chars of each (lowercased, stripped) so that minor
    variations like "Electrician - Urgent" vs "Electrician" still match.
    """
    raw = f"{title.lower().strip()[:30]}|{company.lower().strip()[:20]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ─── Match Scoring ────────────────────────────────────────────────────────────


def score_job(job: dict, profile: dict) -> int:
    """
    Score a job against a worker's profile on a 0-100 scale.

    Higher score = better match. Jobs are presented in descending score order.
    The scoring is intentionally generous — we'd rather show a slightly
    weak match than miss a relevant one.
    """
    score = 0

    # +40: primary skill keyword in job title
    skill = profile.get("primary_skill", "").lower()
    title_lower = job.get("title", "").lower()
    skill_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    if any(term.lower() in title_lower for term in skill_terms):
        score += 40

    # +20: city match (case-insensitive partial match)
    worker_city = profile.get("city", "").lower()
    job_location = (job.get("location", "") + " " + job.get("city", "")).lower()
    if worker_city and worker_city in job_location:
        score += 20

    # +15: salary compatibility (worker's expected wage within 20 % of job minimum)
    expected_wage = profile.get("expected_daily_wage")
    job_salary_min = job.get("salary_min")
    if expected_wage and job_salary_min:
        if (
            job_salary_min >= expected_wage * 0.8
        ):  # job pays at least 80% of expectation
            score += 15

    # +15: experience level match
    years_exp = profile.get("years_experience", 0) or 0
    desc_lower = job.get("description", "").lower()
    # Very rough heuristic: if no experience requirement mentioned, assume entry-level → match
    if "experience" not in desc_lower:
        score += 15
    elif years_exp >= 3:
        score += 15  # experienced worker is always a candidate
    elif (
        years_exp >= 1
        and "fresher" not in desc_lower
        and "no experience" not in desc_lower
    ):
        score += 8

    # +10: work type match
    pref_type = profile.get("work_type", "any")
    job_type = job.get("job_type", "")
    if pref_type == "any" or pref_type in job_type or job_type == "":
        score += 10

    return min(score, 100)


# ─── Adzuna API ───────────────────────────────────────────────────────────────


async def fetch_jobs_adzuna(
    skill: str,
    city: str,
    state: str,
    min_salary: Optional[int] = None,
    limit: int = MAX_JOBS_PER_SOURCE,
) -> List[dict]:
    """
    Fetch jobs from Adzuna India.
    Endpoint: https://api.adzuna.com/v1/api/jobs/in/search/1

    Free tier: 250 API calls/month.
    Sign up: https://developer.adzuna.com/signup

    Adzuna returns annual salaries — we normalize to daily on ingest.
    """
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_API_KEY:
        print("⚠ Adzuna credentials not configured — skipping")
        return []

    search_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    # Use top 2 terms joined with OR for broader recall
    query = " OR ".join(f'"{t}"' for t in search_terms[:2])
    location = city or STATE_TO_ADZUNA_LOCATION.get(state, state) or "India"

    params: dict = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_API_KEY,
        "results_per_page": limit,
        "what": query,
        "where": location,
        "content-type": "application/json",
        "sort_by": "relevance",
    }
    if min_salary:
        # Adzuna expects annual salary; convert from daily
        params["salary_min"] = min_salary * 300

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

    jobs = []
    for job in data.get("results", []):
        salary_min_daily = normalize_to_daily_wage(job.get("salary_min"), "annual")
        salary_max_daily = normalize_to_daily_wage(job.get("salary_max"), "annual")

        jobs.append(
            {
                "source": "adzuna",
                "external_id": str(job.get("id")) if job.get("id") else _fallback_external_id(
                    job.get("title", ""),
                    job.get("company", {}).get("display_name", ""),
                    job.get("location", {}).get("display_name", ""),
                ),
                "title": job.get("title", ""),
                "company": job.get("company", {}).get("display_name", ""),
                "location": job.get("location", {}).get("display_name", ""),
                "city": city,
                "state": state,
                "salary_min": salary_min_daily,
                "salary_max": salary_max_daily,
                "description": (job.get("description") or "")[:500],
                "url": job.get("redirect_url", ""),
                "job_type": "full_time",
                "search_skill": skill,
                "fetched_at": datetime.utcnow().isoformat(),
            }
        )
    return jobs


# ─── Jooble API ───────────────────────────────────────────────────────────────


async def fetch_jobs_jooble(
    skill: str,
    city: str,
    state: str,
    limit: int = MAX_JOBS_PER_SOURCE,
) -> List[dict]:
    """
    Fetch jobs from Jooble (aggregates Naukri, Monster, LinkedIn, Indian boards).
    Endpoint: https://jooble.org/api/{key}
    Apply: https://jooble.org/api/about

    Jooble returns salary as a free-text string — we parse it with parse_salary_string().
    """
    if not settings.JOOBLE_API_KEY:
        print("⚠ Jooble API key not configured — skipping")
        return []

    search_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    keywords = " ".join(search_terms[:2])
    location = f"{city}, {state}, India" if city else f"{state}, India"

    payload = {
        "keywords": keywords,
        "location": location,
        "page": 1,
        "ResultOnPage": limit,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
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

    jobs = []
    for job in data.get("jobs", []):
        sal_min, sal_max = parse_salary_string(job.get("salary", ""))
        jobs.append(
            {
                "source": "jooble",
                "external_id": str(job.get("id")) if job.get("id") else _fallback_external_id(
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                ),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "city": city,
                "state": state,
                "salary_min": sal_min,
                "salary_max": sal_max,
                "description": (job.get("snippet") or "")[:500],
                "url": job.get("link", ""),
                "job_type": job.get("type", "full_time"),
                "search_skill": skill,
                "fetched_at": datetime.utcnow().isoformat(),
            }
        )
    return jobs


# ─── SerpAPI — Google Jobs ────────────────────────────────────────────────────


async def fetch_jobs_serp(
    skill: str,
    city: str,
    state: str,
    limit: int = MAX_JOBS_PER_SOURCE,
) -> List[dict]:
    """
    Fetch jobs from Google Jobs via SerpAPI.
    Endpoint: https://serpapi.com/search?engine=google_jobs
    Docs: https://serpapi.com/google-jobs-api

    Free tier: 100 searches/month.
    Sign up: https://serpapi.com/users/sign_up

    SerpAPI is especially useful for:
    - Picking up jobs from smaller regional Indian boards not indexed by Adzuna/Jooble
    - Government/PSU job listings that appear in Google Jobs
    - Very recent postings (Google indexes fast)

    Salary comes back as a parsed object with min/max/period — cleaner than Jooble.
    """
    if not settings.SERP_API_KEY:
        print("⚠ SerpAPI key not configured — skipping")
        return []

    search_terms = SKILL_TO_SEARCH_TERMS.get(skill, [skill.replace("_", " ")])
    # Build a natural Google Jobs query
    query = f"{search_terms[0]} job"
    location_str = f"{city}, {state}, India" if city else f"{state}, India"

    params: dict = {
        "engine": "google_jobs",
        "q": query,
        "location": location_str,
        "hl": "en",
        "gl": "in",  # country = India
        "api_key": settings.SERP_API_KEY,
        "num": limit,
        "chips": "date_posted:week",  # recent jobs only
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            print(f"SerpAPI error: {e}")
            return []

    jobs = []
    for job in data.get("jobs_results", [])[:limit]:
        # Salary: SerpAPI returns a parsed salary object when available
        sal_obj = job.get("detected_extensions", {})
        sal_min: Optional[int] = None
        sal_max: Optional[int] = None

        salary_raw = sal_obj.get("salary")
        if salary_raw:
            # salary_raw example: "$500 a day" or "₹25,000 a month"
            sal_min, sal_max = parse_salary_string(str(salary_raw))
        else:
            # Try salary from highlights
            for highlight in job.get("job_highlights", []):
                if highlight.get("title", "").lower() in (
                    "qualifications",
                    "salary",
                    "compensation",
                ):
                    for item in highlight.get("items", []):
                        if any(c in item for c in ("₹", "Rs", "INR", "salary", "pay")):
                            sal_min, sal_max = parse_salary_string(item)
                            break

        # Determine job type from extensions
        schedule = sal_obj.get("schedule_type", "").lower()
        job_type = (
            "contract"
            if "contract" in schedule
            else ("part_time" if "part" in schedule else "full_time")
        )

        jobs.append(
            {
                "source": "serp",
                "external_id": _serp_job_id(job),
                "title": job.get("title", ""),
                "company": job.get("company_name", ""),
                "location": job.get("location", ""),
                "city": city,
                "state": state,
                "salary_min": sal_min,
                "salary_max": sal_max,
                "description": _serp_description(job)[:500],
                "url": job.get("related_links", [{}])[0].get("link", "")
                if job.get("related_links")
                else "",
                "job_type": job_type,
                "search_skill": skill,
                "fetched_at": datetime.utcnow().isoformat(),
            }
        )
    return jobs


def _serp_job_id(job: dict) -> str:
    """Generate a stable ID for a SerpAPI job result (no native ID field)."""
    raw = f"{job.get('title', '')}|{job.get('company_name', '')}|{job.get('location', '')}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]


def _fallback_external_id(title: str, company: str, location: str) -> str:
    """Generate a stable fingerprint ID when the upstream API provides no job ID."""
    raw = f"{title}|{company}|{location}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]


def _serp_description(job: dict) -> str:
    """Assemble a description string from SerpAPI's highlights structure."""
    parts = []
    for highlight in job.get("job_highlights", []):
        title = highlight.get("title", "")
        items = highlight.get("items", [])
        if items:
            parts.append(f"{title}: " + "; ".join(items[:3]))
    return " | ".join(parts) or job.get("description", "")
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


async def cache_jobs(jobs: List[dict]) -> List[dict]:
    """
    Upsert fetched jobs to jobs_cache.
    Returns the jobs list enriched with the database UUID ('id' field).
    The UNIQUE constraint on (source, external_id) ensures no duplicates.
    """
    if not jobs:
        return []

    pool = await get_pool()
    expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)
    enriched = []

    async with pool.acquire() as conn:
        for job in jobs:
            # Generate a stable fingerprint when the upstream API provides no id,
            # so different jobs from the same source don't collide on external_id="".
            external_id = job.get("external_id") or ""
            if not external_id:
                raw = json.dumps([
                    job.get("source", ""),
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                ], sort_keys=True)
                external_id = hashlib.sha256(raw.encode()).hexdigest()[:24]
            row = await conn.fetchrow(
                """
                INSERT INTO jobs_cache
                    (external_id, source, title, company, location, city, state,
                     salary_min, salary_max, description, url, job_type, search_skill,
                     fetched_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW(), $14)
                ON CONFLICT (source, external_id)
                DO UPDATE SET
                    title       = EXCLUDED.title,
                    salary_min  = COALESCE(EXCLUDED.salary_min, jobs_cache.salary_min),
                    salary_max  = COALESCE(EXCLUDED.salary_max, jobs_cache.salary_max),
                    description = EXCLUDED.description,
                    expires_at  = EXCLUDED.expires_at,
                    fetched_at  = NOW()
                RETURNING id
                """,
                external_id,
                job["source"],
                job["title"],
                job.get("company", ""),
                job.get("location", ""),
                job.get("city", ""),
                job.get("state", ""),
                job.get("salary_min"),
                job.get("salary_max"),
                job.get("description", ""),
                job.get("url", ""),
                job.get("job_type", "full_time"),
                job.get("search_skill", ""),
                expires_at,
            )
            enriched_job = dict(job)
            enriched_job["id"] = str(row["id"])
            enriched.append(enriched_job)

    return enriched


async def get_cached_jobs(skill: str, city: str, state: str = "") -> List[dict]:
    """
    Returns non-expired cached jobs for this skill+city (or skill+state) combination.
    Ordered by most recently fetched so the freshest results come first.
    """
    location_clause = city or state
    if not location_clause:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        skill_term = skill.replace("_", " ")
        alt_term = SKILL_TO_SEARCH_TERMS.get(skill, [skill_term])[0]

        if not location_clause:
            print(f"get_cached_jobs: skipping query for skill='{skill}' — no city or state provided")
            return []

        rows = await conn.fetch(
            """
            SELECT *
            FROM   jobs_cache
            WHERE  (city ILIKE $1 OR state ILIKE $1)
              AND  (search_skill = $2 OR title ILIKE $3 OR title ILIKE $4)
              AND  (expires_at IS NULL OR expires_at > NOW())
            ORDER  BY fetched_at DESC
            LIMIT  20
            """,
            f"%{location_clause}%",
            skill,
            f"%{skill_term}%",
            f"%{alt_term}%",
        )
    return [dict(r) for r in rows]


# ─── Job Fetching with Radius Expansion ──────────────────────────────────────


async def fetch_all_jobs(
    skill: str,
    city: str,
    state: str,
    min_wage: Optional[int] = None,
) -> List[dict]:
    """
    Fetch jobs from all three APIs concurrently.
    If city returns fewer than MIN_RESULTS, automatically re-runs at state level.

    Returns a deduplicated list of jobs from all sources (order not guaranteed).
    """
    # ── City-level fetch ──
    adzuna_t = fetch_jobs_adzuna(skill, city, state, min_wage)
    jooble_t = fetch_jobs_jooble(skill, city, state)
    serp_t = fetch_jobs_serp(skill, city, state)
    results = await asyncio.gather(adzuna_t, jooble_t, serp_t)

    all_jobs = results[0] + results[1] + results[2]

    # ── Radius expansion: if city results are thin, search at state level ──
    if len(all_jobs) < MIN_RESULTS and state and state != city:
        print(
            f"↩ Expanding search from '{city}' to '{state}' (only {len(all_jobs)} city results)"
        )
        adzuna_t2 = fetch_jobs_adzuna(skill, "", state, min_wage)
        jooble_t2 = fetch_jobs_jooble(skill, "", state)
        serp_t2 = fetch_jobs_serp(skill, "", state)
        results2 = await asyncio.gather(adzuna_t2, jooble_t2, serp_t2)
        all_jobs += results2[0] + results2[1] + results2[2]

    # ── Deduplication using title+company fingerprint ──
    seen_fingerprints: set = set()
    unique_jobs: List[dict] = []
    for job in all_jobs:
        fp = job_fingerprint(job.get("title", ""), job.get("company", ""))
        if fp not in seen_fingerprints:
            seen_fingerprints.add(fp)
            unique_jobs.append(job)

    return unique_jobs


# ─── Spoken Job Description via Bedrock ──────────────────────────────────────



async def describe_job_in_language(job: dict, language: str, position: int) -> str:
    """
    Uses Bedrock (Claude) to describe a job naturally in the worker's language.

    The output sounds like advice from a helpful local friend, NOT a job portal
    listing. This is the key UX difference — workers respond to warmth, not
    corporate copy.
    """
    salary_info = ""
    if job.get("salary_min"):
        if job.get("salary_max") and job["salary_max"] != job["salary_min"]:
            salary_info = (
                f"Salary: ₹{job['salary_min']} to ₹{job['salary_max']} per day"
            )
        else:
            salary_info = f"Salary: ₹{job['salary_min']} per day"
    else:
        salary_info = "Salary: not mentioned (ask when you connect)"

    prompt = (
        f"Describe this job opportunity naturally and warmly in {language} language.\n"
        f"Keep it under 3 sentences. Sound like a helpful friend, not a job portal.\n"
        f"Do NOT start with 'Option {position}' or any numbering.\n\n"
        f"Job details:\n"
        f"- Title: {job.get('title', '')}\n"
        f"- Company: {job.get('company', '') or 'a company in the area'}\n"
        f"- Location: {job.get('location', '')}\n"
        f"- {salary_info}\n"
        f"- Type: {job.get('job_type', 'regular work')}\n"
        f"- Brief: {(job.get('description') or '')[:200]}\n\n"
        f"Language code: {language}\n"
        f"End by asking: 'Kya aap is kaam mein interested hain?' "
        f"(or the equivalent in their language)"
    )

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0.6,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        resp = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
        return result["content"][0]["text"].strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_bedrock)


# ─── Intent Detection ─────────────────────────────────────────────────────────



async def detect_job_response_intent(text: str, language: str) -> str:
    """
    Classifies the worker's response after hearing a job description.

    Returns one of: yes | no | details | stop | other

      yes     — interested in this job, apply
      no      — not interested, show next
      details — wants more information about the current job
      stop    — done looking for now
      other   — question or unclear (will be handled gracefully)
    """
    bedrock = get_bedrock_client()

    prompt = (
        f"A worker was just told about a job opportunity and responded.\n"
        f"Classify their intent.\n\n"
        f'Worker\'s response: "{text}"\n'
        f"Language: {language}\n\n"
        f"Return ONLY one word: yes, no, details, stop, or other\n"
        f"- yes     = interested / want this job\n"
        f"- no      = not interested, show next\n"
        f"- details = asking more about this specific job\n"
        f"- stop    = done, don't want to see more\n"
        f"- other   = unrelated question or unclear"
    )

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        resp = bedrock.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
        return result["content"][0]["text"].strip().lower()

    loop = asyncio.get_event_loop()
    intent = await loop.run_in_executor(None, call_bedrock)
    valid = {"yes", "no", "details", "stop", "other"}
    return intent if intent in valid else "other"


# ─── Application Recording ────────────────────────────────────────────────────


async def record_application(worker_id: str, job: dict) -> str:
    """
    Saves a formal application for a job.
    Returns the matched_job record id.

    Steps:
      1. The job must already be in jobs_cache (it is, because we cached on fetch)
      2. Update matched_jobs status → 'applied'
      3. Insert into applications table
    """
    job_id = job.get("id")
    if not job_id:
        print(f"⚠ Cannot record application — job has no DB id: {job.get('title')}")
        return ""

    matched_job_id = await upsert_matched_job(
        worker_id, job_id, job.get("_score", 0), "applied"
    )
    await save_application_record(worker_id, job_id, matched_job_id)
    return matched_job_id


# ─── Session helpers ──────────────────────────────────────────────────────────


def _lang_response(language: str, hi_text: str, en_text: str) -> str:
    """Return the Hindi string for 'hi', English otherwise."""
    return hi_text if language == "hi" else en_text
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
    text: str,
    session: dict,
    worker_id: str,
    phone_number: str,
) -> Tuple[str, dict]:
    """
    Main entry point for the Job Matching Agent, called by the orchestrator.

    State machine:
        (A) No active search results in session
            → fetch from all three APIs, deduplicate, score, cache, persist in matched_jobs
            → present first job as spoken description

        (B) Active results, process worker response
            "yes"     → record application, confirm, offer next job
            "no"      → present next job
            "details" → give more info about current job, ask again
            "stop"    → clear results, sign off
            "other"   → answer gracefully, repeat current job

        (C) All jobs exhausted
            → offer fresh search

    The session holds job results in memory (Redis) for the duration of the
    conversation. The matched_jobs table holds the permanent record.
    """
    language = session.get("language", "hi")
    matching_state = session["matching"]
    profile_data = session["onboarding"]["collected_data"]

    skill = profile_data.get("primary_skill", "")
    city = profile_data.get("city", "")
    state = profile_data.get("state", "")
    min_wage = profile_data.get("expected_daily_wage")

    # ── (A) No active search ─────────────────────────────────────────────────
    if not matching_state.get("last_results"):
        # Try cache before hitting external APIs
        cached = await get_cached_jobs(skill, city, state)

        if len(cached) >= MIN_RESULTS:
            jobs = cached
            print(f"✓ Cache hit: {len(jobs)} jobs for {skill} in {city or state}")
        else:
            # Live fetch from all three APIs
            raw_jobs = await fetch_all_jobs(skill, city, state, min_wage)

            if not raw_jobs:
                return (
                    _lang_response(
                        language,
                        f"मुझे अभी {city or state} में {skill.replace('_', ' ')} के लिए कोई नौकरी नहीं मिली। "
                        f"मैं कल फिर कोशिश करूँगा।",
                        f"I couldn't find {skill.replace('_', ' ')} jobs in {city or state} right now. "
                        f"I'll try again tomorrow.",
                    ),
                    session,
                )

            # Cache to DB — also adds 'id' field from jobs_cache UUID
            jobs = await cache_jobs(raw_jobs)
            print(
                f"✓ Fetched and cached {len(jobs)} jobs for {skill} in {city or state}"
            )

        # Score each job against this worker's profile
        for job in jobs:
            job["_score"] = score_job(job, profile_data)

        # Sort best matches first
        jobs.sort(key=lambda j: j["_score"], reverse=True)

        # Persist all jobs as 'shown' in matched_jobs for this worker
        persist_tasks = [
            upsert_matched_job(worker_id, job["id"], job["_score"], "shown")
            for job in jobs
            if job.get("id")
        ]
        if persist_tasks:
            await asyncio.gather(*persist_tasks)

        # Store in session (Redis)
        session["matching"]["last_results"] = jobs
        session["matching"]["current_job_index"] = 0

        # Present the first job
        first_job = jobs[0]
        session["matching"]["current_job_index"] = 1

        description = await describe_job_in_language(first_job, language, 1)

        total = len(jobs)
        intro = _lang_response(
            language,
            f"मुझे आपके लिए {total} नौकरियां मिली हैं। पहला विकल्प सुनिए:\n\n",
            f"I found {total} jobs for you. Here is the first option:\n\n",
        )
        await save_session(phone_number, session)
        return intro + description, session

    # ── (B) Active search — process worker's response ────────────────────────
    intent = await detect_job_response_intent(text, language)
    current_index = matching_state["current_job_index"]  # index of NEXT job to show
    all_jobs = matching_state["last_results"]
    shown_job = all_jobs[current_index - 1] if current_index > 0 else all_jobs[0]

    if intent == "yes":
        # Worker wants to apply
        await record_application(worker_id, shown_job)

        response = _lang_response(
            language,
            "बढ़िया! आपकी अर्जी डाल दी गई है। नियोक्ता को आपकी प्रोफाइल भेज दी है। "
            "क्या आप और नौकरियां देखना चाहते हैं?",
            "Great! Your application has been submitted. The employer has been sent your profile. "
            "Would you like to see more jobs?",
        )
        # Don't advance index — the "yes" was for the job already shown

    elif intent == "no":
        # Worker is not interested — update status and show next
        if shown_job.get("id"):
            await update_matched_job_status(worker_id, shown_job["id"], "rejected")

        if current_index >= len(all_jobs):
            # ── (C) Exhausted ──────────────────────────────────────────────
            session["matching"]["last_results"] = []
            session["matching"]["current_job_index"] = 0
            response = _lang_response(
                language,
                "आपने सभी उपलब्ध नौकरियां देख ली हैं। क्या मैं नई नौकरियां ढूंढूँ?",
                "You've seen all available jobs. Should I search for new ones?",
            )
        else:
            next_job = all_jobs[current_index]
            session["matching"]["current_job_index"] = current_index + 1
            response = await describe_job_in_language(
                next_job, language, current_index + 1
            )

    elif intent == "details":
        # Give more detail about the current job, then ask again
        desc = shown_job.get("description", "")
        company = shown_job.get("company", "")
        sal_min = shown_job.get("salary_min")
        sal_max = shown_job.get("salary_max")

        salary_detail = ""
        if sal_min:
            salary_detail = (
                f" वेतन ₹{sal_min}–₹{sal_max} प्रति दिन है।"
                if language == "hi"
                else f" Salary is ₹{sal_min}–₹{sal_max} per day."
            )

        if language == "hi":
            response = (
                f"इस काम के बारे में: {desc or 'विवरण उपलब्ध नहीं है'}।"
                f" कंपनी: {company or 'स्थानीय कंपनी'}।"
                f"{salary_detail}"
                f" क्या आप यह काम करना चाहते हैं?"
            )
        else:
            response = (
                f"About this job: {desc or 'No details available'}."
                f" Company: {company or 'Local company'}."
                f"{salary_detail}"
                f" Would you like to apply?"
            )

    elif intent == "stop":
        session["matching"]["last_results"] = []
        session["matching"]["current_job_index"] = 0
        response = _lang_response(
            language,
            "ठीक है। जब भी नौकरी देखनी हो, बस बोलें।",
            "Okay. Whenever you want to look for jobs again, just ask.",
        )

    else:
        # "other" — worker asked an unrelated question or was unclear
        # Repeat the current job description so they can respond properly
        description = await describe_job_in_language(shown_job, language, current_index)
        if language == "hi":
            response = f"ठीक है। अभी के लिए, यह नौकरी देखें:\n\n{description}"
        else:
            response = f"Sure. For now, here's the current job option:\n\n{description}"

    await save_session(phone_number, session)
    return response, session
