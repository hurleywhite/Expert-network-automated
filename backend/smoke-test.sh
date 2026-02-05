#!/bin/bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dev-api-key-change-in-production}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-dev-webhook-secret-change-in-production}"

echo "Expert Outreach Backend Smoke Test"
echo "==================================="

# 1. Health check
echo -n "Testing health endpoint... "
curl -f -s "$API_URL/health" > /dev/null
echo "✓"

# 2. Create project
echo -n "Creating test project... "
PROJECT_RESPONSE=$(curl -s -X POST "$API_URL/projects" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"name":"Smoke Test","industry":"Tech","regions":["US-West"],"titles_include":["Engineer"]}')
PROJECT_ID=$(echo "$PROJECT_RESPONSE" | jq -r '.id')
if [ "$PROJECT_ID" = "null" ]; then
  echo "✗ Failed to create project"
  echo "$PROJECT_RESPONSE"
  exit 1
fi
echo "✓ ($PROJECT_ID)"

# 3. Create candidate
echo -n "Creating test candidate... "
CANDIDATE_RESPONSE=$(curl -s -X POST "$API_URL/candidates/bulk" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"candidates":[{"full_name":"Jane Test","email":"jane@example.com","title":"Engineer"}]}')
CANDIDATE_ID=$(echo "$CANDIDATE_RESPONSE" | jq -r '.[0].id')
if [ "$CANDIDATE_ID" = "null" ]; then
  echo "✗ Failed to create candidate"
  echo "$CANDIDATE_RESPONSE"
  exit 1
fi
echo "✓ ($CANDIDATE_ID)"

# 4. Draft message
echo -n "Enqueuing draft job... "
DRAFT_JOB_RESPONSE=$(curl -s -X POST "$API_URL/projects/$PROJECT_ID/candidates/$CANDIDATE_ID/draft" \
  -H "X-API-Key: $API_KEY")
DRAFT_JOB_ID=$(echo "$DRAFT_JOB_RESPONSE" | jq -r '.job_id')
if [ "$DRAFT_JOB_ID" = "null" ]; then
  echo "✗ Failed to enqueue draft job"
  echo "$DRAFT_JOB_RESPONSE"
  exit 1
fi
echo "✓ (job: $DRAFT_JOB_ID)"

# Wait for job to complete
sleep 3

# 5. Test multipart/form-data webhook
echo -n "Testing inbound webhook (multipart/form-data)... "
WEBHOOK_RESPONSE=$(curl -s -X POST "$API_URL/webhooks/inbound-email" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -F "to=outreach@example.com" \
  -F "from=jane@example.com" \
  -F "subject=Re: Test" \
  -F "text=Yes, interested!")
WEBHOOK_STATUS=$(echo "$WEBHOOK_RESPONSE" | jq -r '.status')
if [ "$WEBHOOK_STATUS" != "processed" ] && [ "$WEBHOOK_STATUS" != "ignored" ]; then
  echo "✗ Unexpected webhook response"
  echo "$WEBHOOK_RESPONSE"
  exit 1
fi
echo "✓"

# 6. Test SendGrid event webhook
echo -n "Testing event webhook (bounce)... "
EVENT_RESPONSE=$(curl -s -X POST "$API_URL/webhooks/sendgrid-events" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -d '[{"event":"bounce","email":"bounce@example.com","sg_message_id":"test-123","reason":"User unknown"}]')
PROCESSED_COUNT=$(echo "$EVENT_RESPONSE" | jq -r '.processed')
if [ "$PROCESSED_COUNT" != "1" ]; then
  echo "✗ Event webhook failed"
  echo "$EVENT_RESPONSE"
  exit 1
fi
echo "✓"

# 7. Worker observability
echo -n "Testing worker observability endpoint... "
WORKER_RESPONSE=$(curl -s "$API_URL/admin/workers" -H "X-API-Key: $API_KEY")
QUEUE_LENGTH=$(echo "$WORKER_RESPONSE" | jq -r '.queue.length')
if [ -z "$QUEUE_LENGTH" ]; then
  echo "✗ Worker endpoint failed"
  echo "$WORKER_RESPONSE"
  exit 1
fi
echo "✓ (queue length: $QUEUE_LENGTH)"

echo ""
echo "==================================="
echo "All smoke tests passed! ✓"
echo "==================================="
