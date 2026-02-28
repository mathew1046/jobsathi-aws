"""
core/session.py
ElastiCache Redis session manager.

Why Redis for sessions?
- Every message needs to know: which agent is active, how many questions answered,
  what language the user speaks. Loading this from PostgreSQL on every request
  adds 20-50ms. Redis loads it in < 1ms.
- Sessions survive dropped connections — worker picks up where they left off.
- TTL of 30 days means long-inactive users start fresh automatically.
"""

import json
import redis.asyncio as aioredis
from typing import Optional
from core.config import settings


# ─── Redis Client ─────────────────────────────────────────────────────────────

_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


# ─── Session Schema ───────────────────────────────────────────────────────────
#
# Every session stored in Redis looks like this:
#
# {
#   "worker_id": "uuid",
#   "phone_number": "+919876543210",
#   "session_id": "uuid",
#   "current_agent": "onboarding",       ← which agent is handling this user right now
#   "language": "hi",                    ← detected language code
#   "onboarding": {
#     "questions_answered": 5,
#     "current_question_index": 5,
#     "collected_data": {                ← what we've learned so far
#       "primary_skill": "tile_work",
#       "city": "Pune",
#       ...
#     }
#   },
#   "matching": {
#     "last_results": [...],             ← last job results shown
#     "current_job_index": 0
#   }
# }

SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def session_key(phone_number: str) -> str:
    """Redis key format: session:+919876543210"""
    return f"session:{phone_number}"


async def get_session(phone_number: str) -> Optional[dict]:
    """Load session for a worker. Returns None if no session exists."""
    redis = await get_redis()
    data = await redis.get(session_key(phone_number))
    if data:
        return json.loads(data)
    return None


async def save_session(phone_number: str, session_data: dict):
    """Save/update session. Resets the TTL on every save."""
    redis = await get_redis()
    await redis.setex(
        session_key(phone_number),
        SESSION_TTL_SECONDS,
        json.dumps(session_data)
    )


async def create_new_session(worker_id: str, phone_number: str, session_id: str) -> dict:
    """
    Called when a new worker is detected (no session in Redis).
    Creates the default session state.
    """
    session = {
        "worker_id": worker_id,
        "phone_number": phone_number,
        "session_id": session_id,
        "current_agent": "onboarding",  # always start with onboarding
        "language": "hi",               # default Hindi, updated after first message
        "onboarding": {
            "questions_answered": 0,
            "current_question_index": 0,
            "collected_data": {},
            "complete": False
        },
        "matching": {
            "last_results": [],
            "current_job_index": 0,
            "active_search": None
        }
    }
    await save_session(phone_number, session)
    return session


async def update_session_field(phone_number: str, path: list, value):
    """
    Update a nested field in the session.

    Examples:
        update_session_field(phone, ["language"], "ta")
        update_session_field(phone, ["onboarding", "questions_answered"], 6)
        update_session_field(phone, ["onboarding", "collected_data", "city"], "Pune")
    """
    session = await get_session(phone_number)
    if not session:
        return

    # Navigate to the right nested level
    target = session
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    await save_session(phone_number, session)
    return session


async def delete_session(phone_number: str):
    """Delete session (logout or reset)."""
    redis = await get_redis()
    await redis.delete(session_key(phone_number))
