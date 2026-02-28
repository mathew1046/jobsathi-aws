# JobSathi — Onboarding Agent

Voice-first onboarding for India's blue-collar workers.  
Walks each worker through 20 questions, extracts structured data from free-form speech via Amazon Bedrock, stores the profile in PostgreSQL, and generates a PDF resume on S3.

---

## Prerequisites

| Dependency | Version |
|---|---|
| Python | 3.11+ |
| PostgreSQL | 14+ (RDS or local) |
| Redis | 6+ (ElastiCache or local) |
| AWS account | Bedrock, Polly, Transcribe, S3 enabled in `ap-south-1` |

Install Python dependencies:

```bash
pip install -r backend/requirements.txt
```

---

## Environment Variables

Create a `.env` file in `backend/` (or export as shell variables / ECS task definition):

```dotenv
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=jobsathi
DB_USER=jobsathi_admin
DB_PASSWORD=your_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# AWS (uses default credential chain: ~/.aws/credentials, IAM role, env vars)
AWS_REGION=ap-south-1

# S3 bucket for audio + resume PDFs
S3_AUDIO_BUCKET=jobsathi-audio

# Optional job search APIs
ADZUNA_APP_ID=
ADZUNA_API_KEY=
JOOBLE_API_KEY=
```

AWS credentials must allow: `bedrock-runtime:InvokeModel`, `polly:SynthesizeSpeech`,
`transcribe:StartTranscriptionJob`, `s3:PutObject`, `s3:GetObject`.

---

## 1. Database Setup

### Create the database and user

```sql
-- run as postgres superuser
CREATE USER jobsathi_admin WITH PASSWORD 'your_password';
CREATE DATABASE jobsathi OWNER jobsathi_admin;
GRANT ALL PRIVILEGES ON DATABASE jobsathi TO jobsathi_admin;
```

### Create all tables

Tables are created automatically on first server start via `create_all_tables()` in `main.py`.  
To create them manually without starting the server:

```bash
cd backend
python - <<'EOF'
import asyncio
from core.database import create_all_tables
asyncio.run(create_all_tables())
print("Tables created.")
EOF
```

### Seed onboarding questions

Inserts 20 questions × 10 language translations (200 rows) into `onboarding_questions` and
`question_translations`. **Idempotent** — safe to re-run at any time.

```bash
cd backend
python seed_questions.py
```

Expected output:

```
Connecting to PostgreSQL: jobsathi_admin@localhost:5432/jobsathi ...
✓ Seeded 20 questions
✓ Seeded 200 translations (10 languages × 20 questions)
Done. Run `python seed_questions.py` again anytime — it is idempotent.
```

Supported languages seeded: Hindi (`hi`), Tamil (`ta`), Telugu (`te`), Marathi (`mr`),
Bengali (`bn`), Gujarati (`gu`), Kannada (`kn`), Punjabi (`pa`), Malayalam (`ml`),
English (`en`).

---

## 2. Run the Server

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On startup the server will:
1. Call `create_all_tables()` — creates any missing tables (no-op if they exist)
2. Print `✓ JobSathi backend ready`

API docs available at `http://localhost:8000/docs`.

---

## 3. Run the Tests

Unit tests require no database, Redis, or AWS — everything is mocked.

```bash
cd backend
python -m pytest tests/test_onboarding_agent.py -v -m "not integration"
```

Expected: **37 passed**.

```
tests/test_onboarding_agent.py::TestQuestionsCatalogue::test_exactly_20_questions PASSED
tests/test_onboarding_agent.py::TestQuestionsCatalogue::test_indexes_are_0_to_19 PASSED
... (37 total)
======================= 37 passed, 6 deselected in ~1s =======================
```

### Integration tests (requires live DB + AWS)

```bash
cd backend
python -m pytest tests/test_onboarding_agent.py -v -m "integration"
```

---

## 4. Key API Endpoints

### `POST /api/message`

The main voice endpoint. Accepts audio + phone number, routes through the onboarding agent.

```bash
curl -X POST http://localhost:8000/api/message \
  -F "audio=@sample.wav" \
  -F "phone_number=+919876543210"
```

Response:
```json
{
  "text": "आप कौन सा काम करते हैं?",
  "audio_url": "https://...",
  "agent": "onboarding",
  "session_id": "abc123"
}
```

### `GET /api/session/{phone_number}`

Returns current onboarding progress.

```bash
curl http://localhost:8000/api/session/+919876543210
```

### `GET /api/profile/{phone_number}`

Returns the worker's completed profile.

### `GET /api/resume/{phone_number}`

Returns a pre-signed S3 URL for the PDF resume (valid 1 hour).

### `GET /health`

Health check for ECS/load balancer.

---

## 5. Onboarding Flow

The 20 questions asked (in the worker's detected language):

| # | Field | What it collects |
|---|---|---|
| 0 | `primary_skill` | Main trade (electrician, painter, driver, ...) |
| 1 | `secondary_skills` | Additional skills |
| 2 | `years_experience` | Years in the trade |
| 3 | `city` | Current city |
| 4 | `district` | Locality / neighbourhood |
| 5 | `state` | State |
| 6 | `willing_to_relocate` | Open to other cities? |
| 7 | `max_travel_km` | Max travel distance |
| 8 | `availability` | Looking now / currently employed |
| 9 | `expected_daily_wage` | Daily rate in rupees |
| 10 | `work_type` | Daily wage / contract / permanent |
| 11 | `preferred_hours` | Shift preference |
| 12 | `name` | Name (optional) |
| 13 | `biggest_project` | Biggest site / project |
| 14 | `previous_employer` | Company or contractor name |
| 15 | `certifications` | ITI, Skill India, NSDC, etc. |
| 16 | `tools_equipment` | Tools / machinery known |
| 17 | `special_skills` | Any standout qualities |
| 18 | `skill_description` | 2-3 sentences for the resume |
| 19 | `resume_consent` | Agree to create profile + match jobs |

After question 19, the agent generates a PDF resume, uploads it to S3, and hands off to the job-matching agent.

---

## 6. Architecture Notes

- **Question text lives in the database**, not in Python code. Update translations without redeploying by re-running `seed_questions.py`.
- Language is auto-detected from the worker's speech on the first turn (via Amazon Transcribe + Bedrock). All subsequent questions are asked in that language.
- `get_question_text(index, language_code)` fetches from DB with an English fallback.
- DB writes use a column whitelist (`_FIELD_COLUMN_MAP` in `onboarding_agent.py`) to prevent SQL injection from dynamic UPDATE statements.

---

## 7. File Map

```
backend/
├── main.py                         FastAPI app + all API routes
├── seed_questions.py               One-time seed script (re-runnable)
├── requirements.txt
├── agents/
│   └── onboarding_agent.py         Onboarding agent — main logic
├── core/
│   ├── config.py                   Env vars + AWS client singletons
│   ├── database.py                 asyncpg pool, table DDL, DB helpers
│   ├── orchestrator.py             Routes messages to the right agent
│   └── session.py                  Redis session management
└── tests/
    ├── conftest.py                 pytest markers
    ├── __init__.py
    └── test_onboarding_agent.py    37 unit tests (no DB/AWS required)
```
