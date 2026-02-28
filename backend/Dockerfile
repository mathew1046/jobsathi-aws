# Dockerfile
# Builds the JobSathi FastAPI backend for deployment on AWS ECS Fargate

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for reportlab (PDF generation) and asyncpg
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# ECS Fargate runs as non-root for security
RUN adduser --disabled-password --gecos '' appuser
USER appuser

# Port 8000 — API Gateway will route to this
EXPOSE 8000

# Start FastAPI with uvicorn
# --workers 1 because Fargate handles scaling at the container level
# --host 0.0.0.0 to accept connections from API Gateway
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
