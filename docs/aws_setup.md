# JobSathi — AWS Setup Guide (Beginner-Friendly)
# Follow these steps IN ORDER. Each step builds on the previous.

---

## STEP 1: Create an S3 Bucket (for audio files + resume storage)

1. Go to AWS Console → S3 → "Create bucket"
2. Bucket name: `jobsathi-audio` (must be globally unique, add your name if needed)
3. Region: `ap-south-1` (Mumbai — closest to India)
4. Block all public access: **YES** (keep enabled — files accessed via pre-signed URLs only)
5. Click "Create bucket"

Create a second bucket for the React frontend:
1. Bucket name: `jobsathi-frontend`
2. Same region
3. **Uncheck** "Block all public access" (frontend needs to be public)
4. Enable "Static website hosting" in Properties tab
   - Index document: `index.html`
   - Error document: `index.html`

---

## STEP 2: Create RDS PostgreSQL Database

1. Go to AWS Console → RDS → "Create database"
2. Choose: **PostgreSQL**
3. Template: **Free tier** (for development) or **Production** (for launch)
4. Settings:
   - DB identifier: `jobsathi-db`
   - Master username: `jobsathi_admin`
   - Master password: (create a strong password, save it)
5. DB instance class: `db.t3.micro` (free tier eligible)
6. Storage: 20 GB gp2
7. Connectivity:
   - VPC: Default VPC
   - Public access: **No** (backend accesses via private network)
   - VPC security group: Create new → name it `jobsathi-rds-sg`
8. Additional configuration:
   - Initial database name: `jobsathi`
9. Click "Create database" (takes ~5 minutes)

**After creation**, copy the "Endpoint" URL — this is your `DB_HOST`.

---

## STEP 3: Create ElastiCache Redis (Session Storage)

1. Go to AWS Console → ElastiCache → "Create cluster"
2. Choose: **Redis OSS**
3. Cluster mode: **Disabled** (simpler for development)
4. Name: `jobsathi-sessions`
5. Node type: `cache.t3.micro`
6. Number of replicas: 0 (add later for production)
7. Subnet group: Create new, use the same VPC as RDS
8. Security group: Create new → name it `jobsathi-redis-sg`
9. Click "Create"

**After creation**, copy the "Primary endpoint" — this is your `REDIS_HOST`.
Remove the `:6379` port from the end (it's set separately in config).

---

## STEP 4: Set Up IAM Role for ECS (Permissions)

Your backend container needs permission to call Transcribe, Polly, Bedrock, S3.

1. Go to AWS Console → IAM → Roles → "Create role"
2. Trusted entity: **AWS service** → **Elastic Container Service** → **ECS Task**
3. Add these managed policies:
   - `AmazonTranscribeFullAccess`
   - `AmazonPollyFullAccess`
   - `AmazonBedrockFullAccess`
   - `AmazonS3FullAccess`
   - `AmazonRDSFullAccess` (only if connecting from ECS — usually not needed)
4. Role name: `jobsathi-ecs-task-role`
5. Click "Create role"

---

## STEP 5: Enable Amazon Bedrock Model Access

1. Go to AWS Console → Amazon Bedrock → "Model access" (left sidebar)
2. Click "Manage model access"
3. Find and enable: **Claude 3 Sonnet** (by Anthropic)
4. Submit request (usually approved instantly)

---

## STEP 6: Build and Push Docker Image to ECR

Amazon ECR = Amazon's private Docker registry. Your ECS task pulls the image from here.

```bash
# On your local machine (requires AWS CLI installed and configured)

# 1. Create ECR repository
aws ecr create-repository --repository-name jobsathi-backend --region ap-south-1

# 2. Get login command (replace ACCOUNT_ID with your AWS account ID)
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin \
  ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com

# 3. Build the image
cd jobsathi/backend
docker build -t jobsathi-backend .

# 4. Tag it for ECR
docker tag jobsathi-backend:latest \
  ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/jobsathi-backend:latest

# 5. Push to ECR
docker push ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/jobsathi-backend:latest
```

---

## STEP 7: Create ECS Fargate Cluster and Service

1. Go to AWS Console → ECS → "Create cluster"
2. Cluster name: `jobsathi-cluster`
3. Infrastructure: **AWS Fargate** (not EC2)
4. Click "Create"

Create a Task Definition:
1. ECS → Task Definitions → "Create new task definition"
2. Family name: `jobsathi-backend`
3. Launch type: **Fargate**
4. CPU: `0.5 vCPU`, Memory: `1 GB`
5. Task role: `jobsathi-ecs-task-role` (from Step 4)
6. Container:
   - Name: `jobsathi-backend`
   - Image URI: `ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/jobsathi-backend:latest`
   - Port mappings: `8000`
   - Environment variables (add all of these):
     ```
     AWS_REGION          = ap-south-1
     DB_HOST             = (your RDS endpoint)
     DB_PASSWORD         = (your RDS password)
     REDIS_HOST          = (your ElastiCache endpoint)
     S3_AUDIO_BUCKET     = jobsathi-audio
     ADZUNA_APP_ID       = (from adzuna developer portal)
     ADZUNA_API_KEY      = (from adzuna developer portal)
     JOOBLE_API_KEY      = (from jooble.org/api)
     ENVIRONMENT         = production
     SECRET_KEY          = (generate a random 32-char string)
     ```

Create a Service:
1. ECS → your cluster → "Create service"
2. Launch type: Fargate
3. Task definition: `jobsathi-backend`
4. Service name: `jobsathi-backend-service`
5. Desired tasks: `1`
6. Load balancer: Create Application Load Balancer
   - Name: `jobsathi-alb`
   - Target group health check path: `/health`
7. Click "Create"

---

## STEP 8: Create API Gateway

1. Go to AWS Console → API Gateway → "Create API"
2. Choose: **HTTP API** (simpler and cheaper than REST API)
3. Name: `jobsathi-api`
4. Integration: Add integration → **HTTP** → URL of your ALB
5. Routes:
   - `POST /api/message`
   - `GET /api/session/{phone_number}`
   - `GET /api/profile/{phone_number}`
   - `GET /api/resume/{phone_number}`
   - `GET /health`
6. CORS: Enable, allow origin `https://your-cloudfront-domain.cloudfront.net`
7. Deploy to stage: `$default`

Copy the API Gateway **Invoke URL** — this goes into your React app's `REACT_APP_API_URL`.

---

## STEP 9: Deploy React Frontend

```bash
cd jobsathi/frontend

# Set your API URL
echo "REACT_APP_API_URL=https://YOUR_API_GATEWAY_URL" > .env.production

# Build
npm run build

# Upload to S3
aws s3 sync build/ s3://jobsathi-frontend --delete
```

Create a CloudFront distribution:
1. Go to CloudFront → "Create distribution"
2. Origin domain: select `jobsathi-frontend.s3.ap-south-1.amazonaws.com`
3. Default root object: `index.html`
4. Error pages: Add custom error response:
   - HTTP error code: 403 → Response page: `/index.html` → Response code: 200
   - HTTP error code: 404 → Response page: `/index.html` → Response code: 200
5. Click "Create distribution"

---

## STEP 10: Security Groups (Networking)

Make sure the services can talk to each other:

**RDS Security Group (`jobsathi-rds-sg`)**:
- Inbound: PostgreSQL (5432) from ECS security group

**ElastiCache Security Group (`jobsathi-redis-sg`)**:
- Inbound: Redis (6379) from ECS security group

**ECS Security Group (`jobsathi-ecs-sg`)**:
- Inbound: HTTP (8000) from ALB security group
- Outbound: All (to reach Transcribe, Polly, Bedrock, S3 endpoints)

---

## Development: Run Locally

```bash
# Terminal 1: Backend
cd jobsathi/backend
pip install -r requirements.txt
cp .env.example .env  # fill in your values
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd jobsathi/frontend
npm install
echo "REACT_APP_API_URL=http://localhost:8000" > .env.local
npm start
```

For local dev, you can use:
- **PostgreSQL**: Install locally or use Docker: `docker run -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres`
- **Redis**: Install locally or Docker: `docker run -p 6379:6379 redis`
- **AWS services**: Still need real AWS credentials for Transcribe/Polly/Bedrock (no local emulator)

---

## Cost Estimate (at low volume)

| Service | Free Tier | After Free Tier |
|---|---|---|
| ECS Fargate | Not free | ~$15/month (0.5 vCPU, 1GB, 24/7) |
| RDS PostgreSQL | 750 hrs/month free (t3.micro) | ~$15/month |
| ElastiCache | Not free | ~$12/month (t3.micro) |
| Amazon Transcribe | 60 min/month free | $0.024/min |
| Amazon Polly | 5M chars/month free | $4/1M chars (neural) |
| Amazon Bedrock | Pay per token | ~$0.003 per 1K input tokens |
| S3 | 5 GB free | ~$0.023/GB |
| CloudFront | 1TB free | Minimal |

**Total for development/testing: ~$0-5/month if you use Free Tier wisely.**
**Total for small production: ~$50-80/month.**
