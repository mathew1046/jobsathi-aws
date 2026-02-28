"""
agents/application_agent.py
Agent 4: Application Agent

Responsibilities:
  1. Record worker application to a specific job in the database
  2. Send structured notification to the employer (via SNS/SQS for async delivery)
  3. Confirm submission to the worker in their language
  4. Track application status changes (viewed, shortlisted, rejected, hired)
  5. Proactively notify worker when status changes
  6. Handle rejection gracefully and offer next opportunity
  7. Generate a human-friendly interview confirmation message

Design principle: This agent acts as the worker's representative.
Once they say "yes" to a job, the agent handles everything downstream
— employer contact, status tracking, notifications — without requiring
the worker to do anything else.

Called by: matching_agent.py when worker says "yes" to a job offer.
Also called by: background jobs / webhooks when employer updates status.
"""

import json
import asyncio
from datetime import datetime
from typing import Optional, Tuple
from core.config import settings, get_bedrock_client
from core.database import get_pool


# ─── Application Status Machine ───────────────────────────────────────────────

APPLICATION_STATUS = {
    "applied": "Application submitted — waiting for employer to view",
    "viewed": "Employer has viewed your profile",
    "shortlisted": "Employer has shortlisted you for interview",
    "interview": "Interview scheduled",
    "hired": "You got the job!",
    "rejected": "Not selected for this role",
}

# Worker-facing status messages in Hindi and English
STATUS_MESSAGES_HI = {
    "applied": "आपकी अर्जी जमा हो गई है। नियोक्ता को आपकी प्रोफाइल भेज दी गई है।",
    "viewed": "खुशखबरी! नियोक्ता ने आपकी प्रोफाइल देखी।",
    "shortlisted": "बधाई! आप शॉर्टलिस्ट हो गए हैं। जल्द ही इंटरव्यू की जानकारी मिलेगी।",
    "interview": "इंटरव्यू तय हो गया है। जानकारी नीचे है।",
    "hired": "बधाई हो! आपको नौकरी मिल गई।",
    "rejected": "इस बार आगे नहीं बढ़ पाए। कोई बात नहीं, आपके लिए और अच्छे विकल्प हैं।",
}

STATUS_MESSAGES_EN = {
    "applied": "Your application has been submitted. The employer has received your profile.",
    "viewed": "Good news! The employer has viewed your profile.",
    "shortlisted": "Congratulations! You have been shortlisted. Interview details will follow.",
    "interview": "An interview has been scheduled. Details below.",
    "hired": "Congratulations! You got the job!",
    "rejected": "Unfortunately you were not selected this time. Let me find you other opportunities.",
}


# ─── Database Operations ───────────────────────────────────────────────────────


async def create_application(
    worker_id: str,
    job_id: str,
    job_title: str,
    company: str,
    location: str,
) -> dict:
    """
    Creates the application record and returns it.
    ON CONFLICT DO NOTHING — safe to call multiple times for the same job.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO applications
                (worker_id, job_id, status, applied_at)
            VALUES ($1, $2::uuid, 'applied', NOW())
            ON CONFLICT (worker_id, job_id) DO UPDATE
                SET updated_at = NOW()
            RETURNING id, status, applied_at
        """,
            worker_id,
            job_id,
        )

        if row:
            return dict(row)

        # If ON CONFLICT fired, fetch existing record
        existing = await conn.fetchrow(
            "SELECT id, status, applied_at FROM applications WHERE worker_id = $1 AND job_id = $2",
            worker_id,
            job_id,
        )
        return dict(existing) if existing else {}


async def get_worker_applications(worker_id: str, limit: int = 10) -> list:
    """Returns the worker's recent applications with job details."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                a.id, a.status, a.applied_at, a.updated_at,
                j.title, j.company, j.location, j.salary_min, j.salary_max, j.url
            FROM applications a
            JOIN jobs_cache j ON a.job_id = j.id
            WHERE a.worker_id = $1
            ORDER BY a.applied_at DESC
            LIMIT $2
        """,
            worker_id,
            limit,
        )
        return [dict(r) for r in rows]


async def update_application_status(
    application_id: str, new_status: str, notes: str = None
) -> bool:
    """
    Updates application status. Called when employer takes action.
    Returns True if update succeeded.
    """
    if new_status not in APPLICATION_STATUS:
        return False

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE applications
            SET status = $1, updated_at = NOW()
            WHERE id = $2
        """,
            new_status,
            application_id,
        )
        return result == "UPDATE 1"


# ─── Employer Notification ─────────────────────────────────────────────────────


async def notify_employer_of_application(
    worker_id: str, job_id: str, job: dict, worker_profile: dict
) -> bool:
    """
    Sends an SNS notification to the employer when a worker applies.

    In production: SNS → SQS → Lambda/ECS → employer dashboard + email/SMS
    In development: logs the notification (SNS not configured locally)

    Returns True if notification sent (or queued successfully).
    """
    import boto3

    notification_payload = {
        "event": "new_application",
        "job_id": job_id,
        "worker_id": worker_id,
        "timestamp": datetime.utcnow().isoformat(),
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
        },
        "worker_summary": {
            "primary_skill": worker_profile.get("primary_skill"),
            "years_experience": worker_profile.get("years_experience"),
            "city": worker_profile.get("city"),
            "expected_daily_wage": worker_profile.get("expected_daily_wage"),
        },
    }

    sns_topic_arn = getattr(settings, "EMPLOYER_NOTIFICATIONS_SNS_ARN", None)

    if not sns_topic_arn:
        # Dev mode — just log
        print(
            f"[ApplicationAgent] Would notify employer: {json.dumps(notification_payload, indent=2)}"
        )
        return True

    loop = asyncio.get_event_loop()

    def publish():
        sns = boto3.client("sns", region_name=settings.AWS_REGION)
        sns.publish(
            TopicArn=sns_topic_arn,
            Message=json.dumps(notification_payload),
            Subject="New JobSathi Application",
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": "new_application"}
            },
        )

    try:
        await loop.run_in_executor(None, publish)
        return True
    except Exception as e:
        print(f"[ApplicationAgent] SNS publish failed (non-critical): {e}")
        return False


# ─── SMS / WhatsApp Confirmation ──────────────────────────────────────────────


async def send_worker_confirmation_sms(phone_number: str, message: str) -> bool:
    """
    Sends an SMS confirmation to the worker via Amazon SNS.
    This is a fallback/backup to the in-app voice notification.

    Workers who applied via voice call (no smartphone) especially benefit
    from receiving an SMS confirmation they can reference later.
    """
    import boto3

    loop = asyncio.get_event_loop()

    def send():
        sns = boto3.client("sns", region_name=settings.AWS_REGION)
        sns.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                },
                "AWS.SNS.SMS.SenderID": {
                    "DataType": "String",
                    "StringValue": "JOBSATH",
                },
            },
        )

    try:
        await loop.run_in_executor(None, send)
        return True
    except Exception as e:
        print(f"[ApplicationAgent] SMS send failed (non-critical): {e}")
        return False


# ─── Confirmation Message Generation ──────────────────────────────────────────


async def generate_application_confirmation(job: dict, language: str) -> str:
    """
    Generates a warm, natural-language confirmation message in the worker's
    language using Bedrock. This sounds like a friend confirming, not a system.

    Falls back to a template message if Bedrock call fails.
    """
    bedrock = get_bedrock_client()

    company = job.get("company") or "the company"
    title = job.get("title", "this job")
    location = job.get("location", "")
    salary_info = ""
    if job.get("salary_min"):
        salary_info = f"₹{job['salary_min']}/day"

    prompt = f"""You are confirming a job application for a blue-collar worker in India.
Generate a SHORT (2 sentence max), warm, friendly confirmation in {language} language.

Job details:
- Title: {title}
- Company: {company}
- Location: {location}
- Pay: {salary_info or "to be confirmed"}

The message should:
1. Confirm the application was submitted
2. Tell them the employer will contact them if interested
3. Sound like a friend confirming, not a corporate system
Language code: {language}
Keep it to 2 sentences maximum."""

    def call_bedrock():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 150,
                "temperature": 0.5,
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

    try:
        return await loop.run_in_executor(None, call_bedrock)
    except Exception as e:
        print(f"[ApplicationAgent] Bedrock confirmation failed, using template: {e}")
        # Template fallback
        if language == "hi":
            return f"बढ़िया! {company} को आपकी अर्जी और प्रोफाइल भेज दी गई है। अगर वे रुचि दिखाएं तो आपको जल्द खबर मिलेगी।"
        else:
            return f"Done! Your application and profile have been sent to {company}. You will hear back if they are interested."


async def generate_rejection_response(
    job: dict, language: str, has_more_jobs: bool = True
) -> str:
    """
    Generates a gentle rejection message that doesn't discourage the worker.
    Immediately pivots to next opportunity.
    """
    if language == "hi":
        if has_more_jobs:
            return "कोई बात नहीं, इस बार नहीं हुआ। मैं आपके लिए अगला विकल्प देखता हूँ।"
        else:
            return "कोई बात नहीं। जब नई नौकरियां आएंगी, मैं आपको बताऊँगा।"
    else:
        if has_more_jobs:
            return "No worries. Let me show you the next option."
        else:
            return "No worries. I'll notify you when new matching jobs are posted."


# ─── Main Public Functions ─────────────────────────────────────────────────────


async def handle_job_application(
    worker_id: str,
    phone_number: str,
    job: dict,
    worker_profile: dict,
    language: str = "hi",
) -> Tuple[str, str]:
    """
    Main entry point: worker said "yes" to a job.

    Flow:
      1. Create application record in DB
      2. Send employer notification (async, non-blocking)
      3. Send SMS confirmation to worker
      4. Generate and return voice confirmation message

    Returns:
        (voice_response_text, application_id)
    """
    job_id = str(job.get("id", ""))

    # ── Create application record ─────────────────────────────────────────
    application = await create_application(
        worker_id=worker_id,
        job_id=job_id,
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
    )

    application_id = str(application.get("id", ""))

    # ── Notify employer (fire and forget — don't block the voice response) ─
    asyncio.create_task(
        notify_employer_of_application(worker_id, job_id, job, worker_profile)
    )

    # ── Generate confirmation message ─────────────────────────────────────
    confirmation = await generate_application_confirmation(job, language)

    # ── Send SMS backup notification ──────────────────────────────────────
    # Non-blocking — SMS delivery is best-effort
    asyncio.create_task(send_worker_confirmation_sms(phone_number, confirmation))

    return confirmation, application_id


async def handle_status_update_notification(
    worker_id: str,
    phone_number: str,
    application_id: str,
    new_status: str,
    job: dict,
    language: str = "hi",
    interview_details: dict = None,
) -> str:
    """
    Called when an employer updates application status.
    Generates a natural-language notification for the worker.

    Returns the notification text (to be sent via WhatsApp/SMS/push).
    """
    # Get status message template
    if language == "hi":
        base_message = STATUS_MESSAGES_HI.get(new_status, "आपके आवेदन में कोई अपडेट है।")
    else:
        base_message = STATUS_MESSAGES_EN.get(
            new_status, "There is an update to your application."
        )

    # For interview scheduling, add the details
    if new_status == "interview" and interview_details:
        date = interview_details.get("date", "")
        time = interview_details.get("time", "")
        address = interview_details.get("address", "")
        contact = interview_details.get("contact_name", "")

        if language == "hi":
            details = f" {date} को {time} बजे। पता: {address}।"
            if contact:
                details += f" {contact} से मिलें।"
        else:
            details = f" On {date} at {time}. Address: {address}."
            if contact:
                details += f" Ask for {contact}."

        return base_message + details

    # For rejection, offer next step
    if new_status == "rejected":
        return await generate_rejection_response(job, language, has_more_jobs=True)

    return base_message


async def get_application_status_summary(worker_id: str, language: str = "hi") -> str:
    """
    Returns a voice-friendly summary of all active applications.
    Called when worker asks "what's the status of my applications?"
    """
    applications = await get_worker_applications(worker_id, limit=5)

    if not applications:
        if language == "hi":
            return "आपने अभी तक कोई नौकरी के लिए अर्जी नहीं दी है।"
        else:
            return "You haven't applied for any jobs yet."

    if language == "hi":
        lines = [f"आपकी {len(applications)} अर्जियाँ हैं:"]
        for app in applications:
            status_msg = STATUS_MESSAGES_HI.get(app["status"], app["status"])
            lines.append(f"{app['title']} — {app['company']}: {status_msg}")
    else:
        lines = [f"You have {len(applications)} application(s):"]
        for app in applications:
            status_msg = STATUS_MESSAGES_EN.get(app["status"], app["status"])
            lines.append(f"{app['title']} at {app['company']}: {status_msg}")

    return " ".join(lines)
