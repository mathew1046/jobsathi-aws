"""
core/database.py
PostgreSQL connection using asyncpg (async driver).
All tables defined here. Run create_all_tables() once on startup.
"""

import asyncpg
import asyncio
from typing import Optional
from core.config import settings


# ─── Connection Pool ──────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Returns the shared connection pool. Creates it on first call."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            min_size=2,
            max_size=10,
        )
    return _pool


async def get_connection():
    """Context manager for a single DB connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


# ─── Table Definitions ────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """

-- Workers: one row per user, phone number is the primary identifier
CREATE TABLE IF NOT EXISTS workers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number    VARCHAR(20) UNIQUE NOT NULL,  -- "+919876543210"
    created_at      TIMESTAMP DEFAULT NOW(),
    last_active     TIMESTAMP DEFAULT NOW()
);

-- Worker profiles: built up through the onboarding conversation
CREATE TABLE IF NOT EXISTS worker_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id           UUID REFERENCES workers(id) ON DELETE CASCADE,
    
    -- Personal
    name                VARCHAR(100),              -- optional
    preferred_language  VARCHAR(30) DEFAULT 'hi',  -- hi, ta, te, mr, bn, ...
    
    -- Skills (PostgreSQL array — fast for filtering)
    primary_skill       VARCHAR(100),              -- "tile_work", "painting", "electrical"
    secondary_skills    TEXT[],                    -- ["whitewash", "waterproofing"]
    
    -- Experience
    years_experience    INTEGER,
    skill_description   TEXT,                      -- free text from their own words
    
    -- Location
    city                VARCHAR(100),
    district            VARCHAR(100),
    state               VARCHAR(100),
    willing_to_relocate BOOLEAN DEFAULT FALSE,
    max_travel_km       INTEGER DEFAULT 20,
    
    -- Work preferences
    expected_daily_wage INTEGER,                   -- in rupees
    availability        VARCHAR(50),               -- "immediate", "1_week", "1_month"
    work_type           VARCHAR(50),               -- "daily_wage", "contract", "permanent"
    
    -- Onboarding state
    profile_complete    BOOLEAN DEFAULT FALSE,
    questions_answered  INTEGER DEFAULT 0,         -- out of 20
    
    -- Resume
    resume_s3_key       VARCHAR(255),              -- path in S3 bucket
    resume_generated_at TIMESTAMP,
    
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- Conversation history: every single turn stored for session recovery
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id       UUID REFERENCES workers(id) ON DELETE CASCADE,
    session_id      VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL,          -- "user" or "assistant"
    content         TEXT NOT NULL,                 -- the actual text
    agent_name      VARCHAR(50),                   -- which agent produced this turn
    audio_s3_key    VARCHAR(255),                  -- S3 path of the audio file
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Jobs cache: results from Jooble/Adzuna/SerpAPI saved locally to avoid repeated API calls
CREATE TABLE IF NOT EXISTS jobs_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id     VARCHAR(255),                  -- ID from the source API
    source          VARCHAR(50) NOT NULL,           -- "adzuna", "jooble", "serp"
    title           VARCHAR(255) NOT NULL,
    company         VARCHAR(255),
    location        VARCHAR(255),
    city            VARCHAR(100),
    state           VARCHAR(100),
    salary_min      INTEGER,                       -- daily rate in INR
    salary_max      INTEGER,                       -- daily rate in INR
    description     TEXT,
    url             VARCHAR(500),
    skills_required TEXT[],
    job_type        VARCHAR(50),                   -- "full_time", "contract", "daily"
    search_skill    VARCHAR(100),                  -- the skill term used to find this job
    fetched_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP,                     -- cache for 24 hours
    -- Unique constraint prevents duplicate jobs across re-fetches
    CONSTRAINT uq_jobs_source_external UNIQUE (source, external_id)
);

-- Matched jobs: persistent record of which jobs were shown/applied to by each worker
-- This survives Redis session expiry and is the source of truth for the employer side
CREATE TABLE IF NOT EXISTS matched_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id       UUID REFERENCES workers(id) ON DELETE CASCADE,
    job_id          UUID REFERENCES jobs_cache(id) ON DELETE CASCADE,
    match_score     SMALLINT DEFAULT 0,            -- 0-100, higher = better match
    status          VARCHAR(50) DEFAULT 'shown',   -- shown, interested, applied, rejected, hired
    shown_at        TIMESTAMP DEFAULT NOW(),
    acted_at        TIMESTAMP,                     -- when worker said yes/no
    notes           TEXT,
    CONSTRAINT uq_matched_worker_job UNIQUE (worker_id, job_id)
);

-- Applications: worker formally applied to a job (subset of matched_jobs with status=applied)
CREATE TABLE IF NOT EXISTS applications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id       UUID REFERENCES workers(id) ON DELETE CASCADE,
    job_id          UUID REFERENCES jobs_cache(id),
    matched_job_id  UUID REFERENCES matched_jobs(id),
    status          VARCHAR(50) DEFAULT 'applied', -- applied, viewed, shortlisted, rejected, hired
    applied_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_applications_worker_job UNIQUE (worker_id, job_id)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_workers_phone ON workers(phone_number);
CREATE INDEX IF NOT EXISTS idx_profiles_worker ON worker_profiles(worker_id);
CREATE INDEX IF NOT EXISTS idx_profiles_skill ON worker_profiles(primary_skill);
CREATE INDEX IF NOT EXISTS idx_profiles_city ON worker_profiles(city);
CREATE INDEX IF NOT EXISTS idx_conversations_worker ON conversations(worker_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs_cache(city);
CREATE INDEX IF NOT EXISTS idx_jobs_skill ON jobs_cache(search_skill);
CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_matched_worker ON matched_jobs(worker_id);
CREATE INDEX IF NOT EXISTS idx_matched_status ON matched_jobs(status);
CREATE INDEX IF NOT EXISTS idx_applications_worker ON applications(worker_id);
"""


async def create_all_tables():
    """Run once on app startup to create all tables if they don't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
    print("✓ Database tables ready")


# ─── Helper Queries ───────────────────────────────────────────────────────────


async def get_or_create_worker(phone_number: str) -> dict:
    """
    Returns existing worker or creates new one.
    This is called on every message — phone number is the identity.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try to get existing worker
        row = await conn.fetchrow(
            "SELECT id, phone_number, created_at FROM workers WHERE phone_number = $1",
            phone_number,
        )
        if row:
            # Update last_active
            await conn.execute(
                "UPDATE workers SET last_active = NOW() WHERE phone_number = $1",
                phone_number,
            )
            return dict(row)

        # Create new worker
        row = await conn.fetchrow(
            "INSERT INTO workers (phone_number) VALUES ($1) RETURNING id, phone_number, created_at",
            phone_number,
        )
        return dict(row)


async def get_worker_profile(worker_id: str) -> Optional[dict]:
    """Returns the worker's profile, or None if not started yet."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM worker_profiles WHERE worker_id = $1", worker_id
        )
        return dict(row) if row else None


async def save_conversation_turn(
    worker_id: str,
    session_id: str,
    role: str,
    content: str,
    agent_name: str,
    audio_s3_key: str = None,
):
    """
    Saves every single turn to the DB immediately.
    This is the incremental persistence that survives dropped connections.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversations
                (worker_id, session_id, role, content, agent_name, audio_s3_key)
            VALUES ($1, $2, $3, $4, $5, $6)
        """,
            worker_id,
            session_id,
            role,
            content,
            agent_name,
            audio_s3_key,
        )


async def get_recent_conversation(
    worker_id: str, session_id: str, limit: int = 10
) -> list:
    """
    Loads the last N turns of a conversation for context.
    Bedrock needs conversation history to maintain context.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, agent_name, created_at
            FROM conversations
            WHERE worker_id = $1 AND session_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """,
            worker_id,
            session_id,
            limit,
        )
        # Return in chronological order (oldest first)
        return [dict(r) for r in reversed(rows)]


# ─── Matched Jobs Helpers ─────────────────────────────────────────────────────


async def upsert_matched_job(
    worker_id: str,
    job_id: str,
    match_score: int = 0,
    status: str = "shown",
) -> str:
    """
    Insert or update a worker-job match record.
    Returns the matched_jobs row id.

    Uses ON CONFLICT so it is safe to call repeatedly:
    - If the worker has already been shown this job, the score is refreshed
      but the status is NOT downgraded (applied/hired status is preserved).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO matched_jobs (worker_id, job_id, match_score, status)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (worker_id, job_id) DO UPDATE
                SET match_score = EXCLUDED.match_score,
                    status = CASE
                        WHEN matched_jobs.status IN ('applied', 'hired') THEN matched_jobs.status
                        ELSE EXCLUDED.status
                    END
            RETURNING id
            """,
            worker_id,
            job_id,
            match_score,
            status,
        )
        return str(row["id"])


async def update_matched_job_status(worker_id: str, job_id: str, status: str):
    """Update the status of a worker-job match (e.g., 'interested', 'applied', 'rejected')."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE matched_jobs
            SET status = $1, acted_at = NOW()
            WHERE worker_id = $2 AND job_id = $3
            """,
            status,
            worker_id,
            job_id,
        )


async def save_application_record(
    worker_id: str,
    job_id: str,
    matched_job_id: str = None,
):
    """
    Records a formal application in the applications table.
    Also updates matched_jobs.status → 'applied'.
    Idempotent — safe to call multiple times for the same worker+job.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO applications (worker_id, job_id, matched_job_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (worker_id, job_id) DO NOTHING
            """,
            worker_id,
            job_id,
            matched_job_id,
        )
        # Keep matched_jobs in sync
        await conn.execute(
            """
            UPDATE matched_jobs
            SET status = 'applied', acted_at = NOW()
            WHERE worker_id = $1 AND job_id = $2
            """,
            worker_id,
            job_id,
        )


async def get_matched_jobs_for_worker(
    worker_id: str,
    status_filter: str = None,
    limit: int = 20,
) -> list:
    """
    Returns a worker's matched/shown jobs with full job details joined in.
    Used by the /api/jobs/{phone} endpoint so the frontend can display matches.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status_filter:
            rows = await conn.fetch(
                """
                SELECT mj.id            AS match_id,
                       mj.match_score,
                       mj.status        AS match_status,
                       mj.shown_at,
                       mj.acted_at,
                       jc.id            AS job_id,
                       jc.title,
                       jc.company,
                       jc.location,
                       jc.city,
                       jc.state,
                       jc.salary_min,
                       jc.salary_max,
                       jc.description,
                       jc.url,
                       jc.source,
                       jc.job_type
                FROM   matched_jobs mj
                JOIN   jobs_cache   jc ON jc.id = mj.job_id
                WHERE  mj.worker_id = $1
                  AND  mj.status    = $2
                ORDER  BY mj.match_score DESC, mj.shown_at DESC
                LIMIT  $3
                """,
                worker_id,
                status_filter,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT mj.id            AS match_id,
                       mj.match_score,
                       mj.status        AS match_status,
                       mj.shown_at,
                       mj.acted_at,
                       jc.id            AS job_id,
                       jc.title,
                       jc.company,
                       jc.location,
                       jc.city,
                       jc.state,
                       jc.salary_min,
                       jc.salary_max,
                       jc.description,
                       jc.url,
                       jc.source,
                       jc.job_type
                FROM   matched_jobs mj
                JOIN   jobs_cache   jc ON jc.id = mj.job_id
                WHERE  mj.worker_id = $1
                ORDER  BY mj.match_score DESC, mj.shown_at DESC
                LIMIT  $2
                """,
                worker_id,
                limit,
            )
        return [dict(r) for r in rows]
