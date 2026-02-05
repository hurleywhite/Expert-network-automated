#!/bin/bash
set -e

echo "🚀 Testing Expert Outreach Setup..."
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "healthy"; then
    echo "   ✅ Health check passed"
else
    echo "   ❌ Health check failed"
    exit 1
fi

echo ""
echo "2. Testing API with authentication..."

# Create a project
echo "   Creating project..."
PROJECT_RESPONSE=$(curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "name": "Test Project",
    "industry": "Technology",
    "titles_include": ["Engineer", "Director"],
    "regions": ["US-West"]
  }')

PROJECT_ID=$(echo "$PROJECT_RESPONSE" | grep -o '"id":"[^"]*' | cut -d'"' -f4)

if [ -n "$PROJECT_ID" ]; then
    echo "   ✅ Project created: $PROJECT_ID"
else
    echo "   ❌ Failed to create project"
    echo "   Response: $PROJECT_RESPONSE"
    exit 1
fi

# Create a candidate
echo "   Creating candidate..."
CANDIDATE_RESPONSE=$(curl -s -X POST http://localhost:8000/candidates/bulk \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -d '{
    "candidates": [
      {
        "full_name": "Test User",
        "first_name": "Test",
        "last_name": "User",
        "title": "Senior Engineer",
        "company": "TechCorp",
        "email": "test@example.com"
      }
    ]
  }')

CANDIDATE_ID=$(echo "$CANDIDATE_RESPONSE" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)

if [ -n "$CANDIDATE_ID" ]; then
    echo "   ✅ Candidate created: $CANDIDATE_ID"
else
    echo "   ❌ Failed to create candidate"
    exit 1
fi

echo ""
echo "3. Testing background jobs..."

# Enqueue scoring job
echo "   Enqueuing scoring job..."
SCORE_JOB=$(curl -s -X POST "http://localhost:8000/projects/$PROJECT_ID/candidates/$CANDIDATE_ID/score" \
  -H "X-API-Key: dev-api-key-change-in-production")

if echo "$SCORE_JOB" | grep -q "job_id"; then
    echo "   ✅ Scoring job enqueued"
else
    echo "   ❌ Failed to enqueue scoring job"
    exit 1
fi

echo ""
echo "🎉 All tests passed!"
echo ""
echo "📚 Next steps:"
echo "   - View API docs: http://localhost:8000/docs"
echo "   - Check logs: docker compose logs -f"
echo "   - Run unit tests: docker compose exec backend pytest"
