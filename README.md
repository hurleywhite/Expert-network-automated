# Expert Outreach System

A production-oriented FastAPI backend for expert outreach with LLM-assisted message drafting and strict anti-hallucination guardrails.

## Features

- **Project Briefs**: Define structured criteria for expert sourcing
- **Candidate Management**: Store and track expert candidates
- **LLM Message Drafting**: AI-assisted personalized outreach with Claude
- **Anti-Hallucination Guardrails**: Strict validation to prevent fabricated claims
- **Human Approval Workflow**: Review and approve before sending
- **Email Integration**: SendGrid for reliable delivery
- **Reply Ingestion**: Webhook for inbound replies with intent classification
- **Do-Not-Contact**: Global suppression list with automatic enforcement
- **Audit Logs**: Track all actions for compliance
- **Background Jobs**: RQ worker for async processing

## Tech Stack

- **Python 3.11** + **FastAPI**
- **PostgreSQL** for persistence
- **Redis** + **RQ** for background jobs
- **SQLAlchemy 2.x** + **Alembic** migrations
- **SendGrid** for email delivery
- **Anthropic Claude** for LLM drafting
- **Docker Compose** for local development

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) SendGrid API key for real email sending
- (Optional) Anthropic API key for real LLM drafting

### 1. Clone and Setup

```bash
cd expert-outreach
cp .env.example .env
```

Edit `.env` and add your API keys (optional for development):

```env
API_KEY=my-secure-api-key
WEBHOOK_SECRET=my-webhook-secret
SENDGRID_API_KEY=SG.your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

### 2. Start Services

```bash
docker compose up -d
```

This will start:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Backend API (port 8000)
- RQ Worker

### 3. Verify

```bash
curl http://localhost:8000/health
```

Should return: `{"status":"healthy"}`

### 4. View API Docs

Open http://localhost:8000/docs for interactive OpenAPI documentation.

## API Examples

All non-webhook endpoints require the `X-API-Key` header.

### Create a Project

```bash
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "name": "AI Safety Consultants",
    "industry": "Technology",
    "subvertical": "Artificial Intelligence",
    "company_size_min": 50,
    "regions": ["US-West", "US-East"],
    "titles_include": ["Director", "VP", "Head of AI", "Chief AI Officer"],
    "titles_exclude": ["Intern", "Junior"],
    "keywords": ["machine learning", "AI safety", "alignment"],
    "exclusions": ["competitor-name"]
  }'
```

Response:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "AI Safety Consultants",
  ...
}
```

### Bulk Ingest Candidates

```bash
curl -X POST http://localhost:8000/candidates/bulk \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "candidates": [
      {
        "full_name": "Jane Smith",
        "first_name": "Jane",
        "last_name": "Smith",
        "title": "VP of Engineering",
        "company": "TechCorp",
        "company_employee_count": 500,
        "region": "US-West",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "email": "jane.smith@techcorp.com",
        "source_name": "linkedin",
        "source_url": "https://linkedin.com/in/janesmith"
      }
    ]
  }'
```

### Score a Candidate

```bash
PROJECT_ID="123e4567-e89b-12d3-a456-426614174000"
CANDIDATE_ID="987e6543-e21b-34d5-b678-123456789abc"

curl -X POST "http://localhost:8000/projects/$PROJECT_ID/candidates/$CANDIDATE_ID/score" \
  -H "X-API-Key: dev-api-key-change-in-production"
```

Response:
```json
{
  "job_id": "abc123",
  "message": "Scoring job enqueued for candidate ..."
}
```

### Draft a Message

```bash
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/candidates/$CANDIDATE_ID/draft" \
  -H "X-API-Key: dev-api-key-change-in-production"
```

Response:
```json
{
  "job_id": "def456",
  "message": "Drafting job enqueued for candidate ..."
}
```

### Approve a Draft

```bash
DRAFT_ID="456e7890-f12b-34c5-d678-901234567def"

curl -X POST "http://localhost:8000/drafts/$DRAFT_ID/approve" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "approved_by": "alice@company.com"
  }'
```

### Send an Approved Draft

```bash
curl -X POST "http://localhost:8000/drafts/$DRAFT_ID/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "actor": "alice@company.com"
  }'
```

### Inbound Reply Webhook

This endpoint receives inbound emails from SendGrid Inbound Parse (multipart/form-data).

```bash
curl -X POST http://localhost:8000/webhooks/inbound-email \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -F "to=outreach@example.com" \
  -F "from=jane.smith@techcorp.com" \
  -F "subject=Re: Quick question about your AI work" \
  -F "text=Yes, I would be happy to chat. I am available next week."
```

Response:
```json
{
  "status": "processed",
  "candidate_id": "987e6543-e21b-34d5-b678-123456789abc",
  "conversation_id": "111e2222-f33b-44c5-d678-555666777888",
  "classification": "interested"
}
```

### SendGrid Event Webhook

This endpoint handles SendGrid event notifications for bounces, spam reports, and unsubscribes.

**Event Name Normalization:** The webhook handles both `spamreport` (no underscore) and `spam_report` (with underscore) identically, as SendGrid may send either variant. All event names are normalized to lowercase for consistent processing.

**Suppression Events:** The following events trigger automatic do-not-contact suppression:
- `bounce` - Hard bounces
- `dropped` - Dropped by SendGrid
- `blocked` - Blocked by spam filter
- `spamreport` / `spam_report` - User marked as spam
- `unsubscribe` - User unsubscribed

```bash
curl -X POST http://localhost:8000/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[
    {
      "event": "spamreport",
      "email": "bounce@example.com",
      "sg_message_id": "abc123",
      "reason": "User marked as spam"
    }
  ]'
```

Response:
```json
{
  "processed": 1,
  "results": [
    {"email": "bounce@example.com", "event": "spamreport", "status": "processed"}
  ]
}
```

## Anti-Hallucination Guardrails

The system implements strict validation to prevent LLM hallucinations:

### How It Works

1. **Facts-Only Prompting**: The LLM receives only verified facts about the candidate
2. **Fact Usage Tracking**: The LLM must declare which facts it used
3. **Pattern Detection**: Validates against risk patterns like:
   - "I saw your recent post..."
   - "Congratulations on your funding..."
   - "Your keynote at [event]..."
4. **Blocking**: Drafts with risk flags cannot be sent until reviewed

### Example: Blocked Draft

```json
{
  "subject": "Loved your NeurIPS talk",
  "body": "I saw your keynote at NeurIPS...",
  "facts_used": ["candidate.name", "candidate.title"],
  "risk_flags": [
    "body contains 'your keynote at' but no supporting fact found"
  ]
}
```

This draft **cannot be sent** because it mentions a specific event not in the provided facts.

## Testing

### Run Unit Tests

```bash
docker compose exec backend pytest
```

### Test Validator

```bash
docker compose exec backend pytest tests/test_validator.py -v
```

### Test Unsubscribe Flow

```bash
docker compose exec backend pytest tests/test_unsubscribe.py -v
```

## Database Migrations

### Create a New Migration

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
```

### Apply Migrations

```bash
docker compose exec backend alembic upgrade head
```

### Rollback

```bash
docker compose exec backend alembic downgrade -1
```

## Monitoring

### View Logs

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Worker only
docker compose logs -f worker
```

### Check Worker Status

```bash
docker compose exec worker rq info
```

## Architecture

### Data Flow

1. **Ingestion**: Candidates bulk imported via API
2. **Enrichment**: Background job finds/verifies emails (mock in dev)
3. **Scoring**: Background job scores candidate against project criteria
4. **Drafting**: Background job calls Claude API to generate personalized message
5. **Validation**: Anti-hallucination validator checks draft
6. **Approval**: Human reviews and approves draft
7. **Sending**: Background job sends via SendGrid with idempotency
8. **Reply**: Webhook ingests replies, classifies intent, updates status

### Security

- **API Key**: All endpoints require `X-API-Key` header
- **Webhook Secret**: Webhook endpoint requires `X-Webhook-Secret`
- **Idempotency**: Send operations use idempotency keys to prevent duplicates
- **Do-Not-Contact**: Enforced at send time, blocks all communication

### Idempotency

The send operation is idempotent using the key: `draft:{draft_id}`

**Key Format:** The idempotency key is stable per draft and does not include the actor. This ensures:
- Only one email is sent per draft, regardless of which actor initiates the send
- Multiple send attempts with different actors are properly deduplicated
- Retrying a send won't duplicate emails
- Multiple workers can safely process the same job
- Network failures can be safely retried

The actor is still recorded in the outbound event metadata for audit purposes.

## Hardening Features

### Rate Limiting

The system implements Redis-based per-domain rate limiting to prevent overwhelming recipient servers:

- **Per-domain hourly cap**: Configurable limit (default: 10 emails/hour per domain)
- **Random jitter delays**: Random delays (5-30 seconds) before sending to spread load
- **Redis-backed**: Distributed rate limiting across multiple workers

Configuration:
```env
RATE_LIMIT_PER_DOMAIN_PER_HOUR=10
RATE_LIMIT_JITTER_MIN_SECONDS=5
RATE_LIMIT_JITTER_MAX_SECONDS=30
```

### Approval Integrity

SHA256 hash verification prevents post-approval tampering:

- Hash computed at approval time from subject, body, approver, and timestamp
- Hash verified before sending
- Modified drafts automatically blocked

### Bounce Handling

SendGrid Event Webhook automatically processes delivery failures:

- **Events handled**: bounce, dropped, spam_report, unsubscribe
- **Automatic do-not-contact**: Failed deliveries added to suppression list
- **OutboundEvent tracking**: Status updates for audit trail

### Worker Observability

Monitor worker health and queue status:

```bash
curl -H "X-API-Key: dev-api-key-change-in-production" \
  http://localhost:8000/admin/workers
```

Response:
```json
{
  "workers": [
    {
      "name": "worker-1",
      "state": "busy",
      "current_job": "abc123",
      "successful_job_count": 45,
      "failed_job_count": 2
    }
  ],
  "queue": {
    "name": "default",
    "length": 5,
    "finished_count": 100,
    "failed_count": 2
  },
  "failed_jobs": [...]
}
```

### SendGrid Configuration

**Inbound Parse Webhook:**
1. Go to SendGrid dashboard > Settings > Inbound Parse
2. Add hostname and URL: `https://yourdomain.com/webhooks/inbound-email`
3. Add HTTP header: `X-Webhook-Secret: your-secret`

**Event Webhook:**
1. Go to SendGrid dashboard > Settings > Mail Settings > Event Webhook
2. Set HTTP Post URL: `https://yourdomain.com/webhooks/sendgrid-events`
3. Enable events: bounce, dropped, spam_report, unsubscribe
4. Add HTTP header: `X-Webhook-Secret: your-secret`

### Smoke Testing

Run comprehensive integration tests:

```bash
cd backend
./smoke-test.sh
```

## Production Considerations

### Before Deploying to Production

1. **Change Secrets**:
   - Generate strong `API_KEY` and `WEBHOOK_SECRET`
   - Never commit secrets to git

2. **Configure Email Provider**:
   - Set up SendGrid account
   - Configure Inbound Parse webhook to point to your domain
   - Verify sender domain

3. **Configure LLM Provider**:
   - Get Anthropic API key
   - Set rate limits and monitoring

4. **Database**:
   - Use managed PostgreSQL (RDS, Cloud SQL, etc.)
   - Enable backups
   - Configure connection pooling

5. **Redis**:
   - Use managed Redis (ElastiCache, Cloud Memorystore, etc.)
   - Enable persistence (AOF or RDB)

6. **Worker Scaling**:
   - Run multiple worker instances for throughput
   - Monitor queue depth

7. **Monitoring**:
   - Set up log aggregation (DataDog, Sentry, etc.)
   - Monitor API latency and error rates
   - Alert on worker failures

8. **Rate Limiting**:
   - Implement rate limiting on API endpoints
   - Respect SendGrid sending limits
   - Monitor Anthropic API usage

## License

Proprietary - Internal Use Only
