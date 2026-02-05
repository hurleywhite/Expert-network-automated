# Expert Outreach System

An automated expert network outreach platform with AI-powered candidate sourcing, scoring, and personalized email drafting.

## Features

- **Natural Language Project Creation**: Describe who you're looking for in plain English
- **Apollo.io Integration**: Automatic candidate sourcing and enrichment
- **LLM-Powered Scoring**: Claude AI evaluates candidate fit with semantic understanding
- **Geographic Filtering**: Automatically excludes candidates outside target regions
- **Industry-Specific Search**: Organization keyword filtering ensures relevant companies
- **Personalized Draft Generation**: AI-written outreach emails with anti-hallucination guardrails
- **Human Approval Workflow**: Review and approve drafts before sending
- **Email Delivery**: Resend integration for reliable sending
- **React Dashboard**: Modern UI for managing projects and reviewing drafts

## Tech Stack

- **Backend**: Python 3.11 + FastAPI
- **Frontend**: React + TypeScript + Tailwind CSS
- **Database**: PostgreSQL
- **Cache/Queue**: Redis + RQ
- **AI**: Anthropic Claude (scoring & drafts)
- **Sourcing**: Apollo.io API
- **Email**: Resend
- **Infrastructure**: Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- API keys for: Apollo.io, Anthropic (Claude), Resend

### 1. Clone the Repository

```bash
git clone https://github.com/hurleywhite/Expert-network-automated.git
cd Expert-network-automated
```

### 2. Configure API Keys

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your API keys:

```env
# Apollo.io API (for candidate sourcing & enrichment)
APOLLO_API_KEY=your_apollo_api_key_here

# Anthropic Claude API (for LLM scoring & draft generation)
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key_here

# Resend API (for sending emails)
RESEND_API_KEY=re_your_resend_api_key_here
RESEND_FROM_EMAIL=outreach@yourdomain.com
RESEND_FROM_NAME=Your Company Name
```

### 3. Start the System

```bash
docker compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Backend API (port 8000)
- Frontend Dashboard (port 3000)
- Background Worker

### 4. Access the Dashboard

Open **http://localhost:3000** in your browser.

### 5. Verify API Health

```bash
curl http://localhost:8000/health
```

## Usage

### Create a Project (Natural Language)

```bash
curl -X POST http://localhost:8000/projects/from-description \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{"description": "Find 10 fintech leaders (C-suite, VPs) in NYC", "created_by": "Your Name"}'
```

### Import Candidates

```bash
curl -X POST http://localhost:8000/sourcing/import/{PROJECT_ID}/from-brief \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{"locations": ["New York, NY"], "seniorities": ["c_suite", "vp"], "max_results": 15}'
```

### Enrich Candidates (Get Emails)

```bash
curl -X POST http://localhost:8000/sourcing/enrich-project/{PROJECT_ID}?limit=15 \
  -H "X-API-Key: dev-api-key-change-in-production"
```

### Score Candidates

```bash
curl -X POST http://localhost:8000/projects/{PROJECT_ID}/score-all \
  -H "X-API-Key: dev-api-key-change-in-production"
```

### Generate Drafts

```bash
curl -X POST http://localhost:8000/projects/{PROJECT_ID}/draft-with-context \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "outreach_context": {
      "research_topic": "fintech industry trends",
      "rate_range": "500 dollars",
      "sender_name": "Your Name",
      "sender_title": "Research Director"
    },
    "min_score": 50
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/projects/from-description` | POST | Create project from natural language |
| `/projects/{id}/status` | GET | Get project pipeline status |
| `/projects/{id}/candidates` | GET | List scored candidates |
| `/projects/{id}/review-queue` | GET | Get drafts pending review |
| `/projects/{id}/score-all` | POST | Score all candidates |
| `/projects/{id}/draft-with-context` | POST | Generate personalized drafts |
| `/sourcing/import/{id}/from-brief` | POST | Import candidates from Apollo |
| `/sourcing/enrich-project/{id}` | POST | Enrich candidates with emails |

## Common Commands

```bash
# Start the system
docker compose up -d

# View logs
docker compose logs -f backend

# Restart after code changes
docker compose restart backend

# Stop the system
docker compose down

# Reset database (caution: deletes all data)
docker compose down -v
docker compose up -d
```

## Project Structure

```
expert-outreach/
├── backend/
│   ├── app/
│   │   ├── routers/       # API endpoints
│   │   ├── services/      # Business logic (Apollo, LLM, scoring)
│   │   ├── models.py      # Database models
│   │   └── crud.py        # Database operations
│   ├── .env.example       # Environment template
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/    # React components
│       ├── pages/         # Page views
│       └── types/         # TypeScript types
├── docker-compose.yml
└── README.md
```

## License

MIT
