"""
main.py + api/routes.py combined
FastAPI application — the single entry point for all frontend requests.

Endpoints:
  POST /api/message       — main voice message endpoint
  GET  /api/session/{phone}  — get current session state
  GET  /api/profile/{phone}  — get worker profile
  GET  /api/resume/{phone}   — get resume download URL
  GET  /health               — health check for ECS
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import base64

from core.config import settings
from core.database import (
    create_all_tables,
    get_or_create_worker,
    get_worker_profile,
    get_matched_jobs_for_worker,
)
from core.session import get_session
from core.orchestrator import process_message


# ─── App Startup ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # Create DB tables on startup (safe to run multiple times — uses IF NOT EXISTS)
    await create_all_tables()
    print("✓ JobSathi backend ready")
    yield
    # Cleanup on shutdown (if needed)


app = FastAPI(
    title="JobSathi API",
    description="Voice-first AI job platform for India's blue-collar workers",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allow requests from your CloudFront domain and localhost for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "https://your-cloudfront-domain.cloudfront.net",  # replace with yours
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Main Voice Message Endpoint ──────────────────────────────────────────────


@app.post("/api/message")
async def handle_message(
    audio: UploadFile = File(...),  # The audio blob from the browser mic
    phone_number: str = Form(...),  # e.g., "+919876543210"
    session_id: str = Form(None),  # optional, for session continuity
):
    """
    The single most important endpoint in the entire application.

    The React frontend:
    1. Captures audio from the microphone
    2. Sends it as a multipart form with the worker's phone number
    3. Receives text + audio back

    Everything else — language detection, agent routing, DB writes — happens here.
    """
    # Validate phone number format
    if not phone_number.startswith("+"):
        phone_number = "+91" + phone_number.lstrip("0")  # normalize Indian numbers

    # Read audio bytes
    audio_bytes = await audio.read()

    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small or empty")

    # Process through the full pipeline
    result = await process_message(
        audio_bytes=audio_bytes, phone_number=phone_number, session_id=session_id
    )

    return JSONResponse(content=result)


# ─── Session State Endpoint ───────────────────────────────────────────────────


@app.get("/api/session/{phone_number}")
async def get_session_state(phone_number: str):
    """
    Returns current session state for a worker.
    Frontend uses this to restore UI state on page reload.
    """
    session = await get_session(phone_number)
    if not session:
        return {"exists": False}

    return {
        "exists": True,
        "current_agent": session.get("current_agent"),
        "language": session.get("language"),
        "progress": {
            "questions_answered": session["onboarding"].get("questions_answered", 0),
            "total": 20,
            "percent": int(
                (session["onboarding"].get("questions_answered", 0) / 20) * 100
            ),
        },
        "profile_complete": session["onboarding"].get("complete", False),
    }


# ─── Profile Endpoint ─────────────────────────────────────────────────────────


@app.get("/api/profile/{phone_number}")
async def get_profile(phone_number: str):
    """Returns a worker's profile. Used by the frontend to show profile page."""
    if not phone_number.startswith("+"):
        phone_number = "+91" + phone_number.lstrip("0")

    worker = await get_or_create_worker(phone_number)
    profile = await get_worker_profile(str(worker["id"]))

    if not profile:
        return {"profile_exists": False}

    # Don't expose internal IDs
    safe_profile = {
        "name": profile.get("name"),
        "primary_skill": profile.get("primary_skill"),
        "secondary_skills": profile.get("secondary_skills", []),
        "years_experience": profile.get("years_experience"),
        "city": profile.get("city"),
        "state": profile.get("state"),
        "expected_daily_wage": profile.get("expected_daily_wage"),
        "availability": profile.get("availability"),
        "profile_complete": profile.get("profile_complete", False),
        "questions_answered": profile.get("questions_answered", 0),
        "has_resume": profile.get("resume_s3_key") is not None,
    }

    return safe_profile


# ─── Resume Download URL ──────────────────────────────────────────────────────


@app.get("/api/resume/{phone_number}")
async def get_resume_url(phone_number: str):
    """
    Returns a pre-signed S3 URL for the worker's resume PDF.
    Pre-signed URLs expire after 1 hour for security.
    """
    import boto3
    from core.config import settings

    if not phone_number.startswith("+"):
        phone_number = "+91" + phone_number.lstrip("0")

    worker = await get_or_create_worker(phone_number)
    profile = await get_worker_profile(str(worker["id"]))

    if not profile or not profile.get("resume_s3_key"):
        raise HTTPException(
            status_code=404, detail="Resume not found. Complete your profile first."
        )

    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_AUDIO_BUCKET, "Key": profile["resume_s3_key"]},
        ExpiresIn=3600,  # 1 hour
    )

    return {"url": url, "expires_in": 3600}


# ─── Matched Jobs Endpoint ────────────────────────────────────────────────────


VALID_JOB_STATUSES = {"shown", "interested", "applied", "rejected", "hired"}


@app.get("/api/jobs/{phone_number}")
async def get_matched_jobs(phone_number: str, status: str = None):
    """
    Returns the jobs that have been matched/shown to this worker.

    Query params:
        status — filter by match status: shown | interested | applied | rejected | hired
                 Omit to return all.

    This endpoint is used by:
    - The frontend to show the worker their job history / active matches
    - The employer panel to see which workers have applied to their postings

    The matched_jobs table is the permanent record — it survives Redis session
    expiry, so workers can always see their job history even after a browser refresh.
    """
    if status is not None and status not in VALID_JOB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_JOB_STATUSES))}",
        )

    if not phone_number.startswith("+"):
        phone_number = "+91" + phone_number.lstrip("0")

    worker = await get_or_create_worker(phone_number)
    worker_id = str(worker["id"])

    jobs = await get_matched_jobs_for_worker(worker_id, status_filter=status)

    if not jobs:
        return {"jobs": [], "total": 0, "message": "No matched jobs found yet."}

    # Convert UUIDs / datetimes to JSON-serialisable types
    safe_jobs = []
    for j in jobs:
        safe_jobs.append(
            {
                "match_id": str(j["match_id"]),
                "job_id": str(j["job_id"]),
                "match_score": j["match_score"],
                "match_status": j["match_status"],
                "shown_at": j["shown_at"].isoformat() if j["shown_at"] else None,
                "acted_at": j["acted_at"].isoformat() if j["acted_at"] else None,
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "city": j["city"],
                "state": j["state"],
                "salary_min": j["salary_min"],
                "salary_max": j["salary_max"],
                "description": j["description"],
                "url": j["url"],
                "source": j["source"],
                "job_type": j["job_type"],
            }
        )

    return {"jobs": safe_jobs, "total": len(safe_jobs)}


# ─── Health Check ─────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """
    ECS health check endpoint.
    ECS calls this every 30 seconds. If it returns non-200, the container is replaced.
    """
    return {"status": "healthy", "service": "jobsathi-backend"}
