# JobSathi — Complete Technical Architecture

## Directory Structure

```
jobsathi/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── core/
│   │   ├── config.py            # All env vars & AWS clients
│   │   ├── database.py          # RDS PostgreSQL connection
│   │   ├── session.py           # ElastiCache Redis session manager
│   │   └── orchestrator.py      # Routes messages to correct agent
│   ├── agents/
│   │   ├── voice_agent.py       # Agent 1: Transcribe + Polly
│   │   ├── onboarding_agent.py  # Agent 2: 20 questions + resume
│   │   └── matching_agent.py    # Agent 3: Jooble/Adzuna APIs
│   ├── models/
│   │   └── schemas.py           # Pydantic models
│   └── api/
│       └── routes.py            # All HTTP + WebSocket endpoints
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── MicButton.jsx    # The big record button
│   │   │   ├── ChatBubble.jsx   # Conversation display
│   │   │   └── JobCard.jsx      # Job result cards
│   │   ├── hooks/
│   │   │   └── useVoice.js      # Audio capture + WebSocket
│   │   └── pages/
│   │       ├── Onboarding.jsx
│   │       └── Jobs.jsx
│   └── package.json
│
└── infrastructure/
    ├── rds_schema.sql            # Full PostgreSQL schema
    └── aws_setup.md              # Step-by-step AWS console guide
```

## AWS Services Map

| Service | What it does in JobSathi | Where in code |
|---|---|---|
| ECS Fargate | Runs the FastAPI backend container | Dockerfile + ECS task definition |
| API Gateway | Single HTTPS entry point for frontend | routes.py endpoints |
| Amazon Transcribe | Converts worker voice → text | voice_agent.py |
| Amazon Polly | Converts agent text → voice audio | voice_agent.py |
| Amazon Bedrock (Claude) | Powers onboarding conversation + resume | onboarding_agent.py |
| RDS PostgreSQL | Stores worker profiles, jobs, applications | database.py |
| ElastiCache Redis | Holds session state between requests | session.py |
| S3 | Hosts React frontend + stores audio files | CloudFront origin |
| CloudFront | CDN serving the React app globally | S3 bucket policy |
| Cognito | OTP login via phone number | auth middleware |
| SNS | SMS/WhatsApp notifications | application_agent.py |

## Request Flow (every single user message)

```
User speaks into browser mic
    ↓
useVoice.js captures audio blob
    ↓
POST /api/message (audio + phone_number + session_id)
    ↓
API Gateway → ECS Fargate (FastAPI)
    ↓
voice_agent.py → Amazon Transcribe → text
    ↓
orchestrator.py → loads session from Redis → detects intent
    ↓
correct agent module runs → calls Bedrock if needed
    ↓
agent returns text response
    ↓
voice_agent.py → Amazon Polly → audio bytes
    ↓
response: { text, audio_base64, session_id, agent_state }
    ↓
frontend plays audio, shows text bubble
```
