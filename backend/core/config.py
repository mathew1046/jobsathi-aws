"""
core/config.py
All environment variables and AWS client initialization.
Every other module imports clients from here — never create boto3 clients elsewhere.
"""

import os
import boto3
from functools import lru_cache


# ─── Environment Variables ────────────────────────────────────────────────────
# Set these in your ECS task definition as environment variables,
# or in a .env file locally for development.

class Settings:
    # AWS region — keep everything in the same region to avoid data transfer costs
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")  # Mumbai — closest to India

    # RDS PostgreSQL
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "jobsathi")
    DB_USER: str = os.getenv("DB_USER", "jobsathi_admin")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # ElastiCache Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    # Amazon Bedrock model
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # S3 bucket for audio file storage
    S3_AUDIO_BUCKET: str = os.getenv("S3_AUDIO_BUCKET", "jobsathi-audio")

    # Job API keys (set these after getting API access)
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_API_KEY: str = os.getenv("ADZUNA_API_KEY", "")
    JOOBLE_API_KEY: str = os.getenv("JOOBLE_API_KEY", "")

    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ─── AWS Clients ─────────────────────────────────────────────────────────────
# Created once at startup. lru_cache ensures they are singletons.

@lru_cache()
def get_transcribe_client():
    """Amazon Transcribe — speech to text."""
    return boto3.client("transcribe", region_name=get_settings().AWS_REGION)


@lru_cache()
def get_transcribe_streaming_client():
    """
    Amazon Transcribe Streaming — for real-time audio.
    Uses a different client than batch transcribe.
    Requires: pip install amazon-transcribe
    """
    from amazon_transcribe.client import TranscribeStreamingClient
    return TranscribeStreamingClient(region=get_settings().AWS_REGION)


@lru_cache()
def get_polly_client():
    """Amazon Polly — text to speech."""
    return boto3.client("polly", region_name=get_settings().AWS_REGION)


@lru_cache()
def get_bedrock_client():
    """
    Amazon Bedrock — LLM calls for all agents.
    Uses bedrock-runtime (not bedrock) for inference.
    """
    return boto3.client("bedrock-runtime", region_name=get_settings().AWS_REGION)


@lru_cache()
def get_s3_client():
    """Amazon S3 — audio file storage."""
    return boto3.client("s3", region_name=get_settings().AWS_REGION)


settings = get_settings()
