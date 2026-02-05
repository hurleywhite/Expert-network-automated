#!/bin/bash
set -e

echo "=========================================="
echo "Running Production Fix Tests"
echo "=========================================="
echo ""

cd /Users/hurleywhite/expert-outreach

echo "Step 1: Building and starting services..."
docker compose up -d --build

echo ""
echo "Step 2: Waiting for services to be ready..."
sleep 10

echo ""
echo "Step 3: Running database migrations..."
docker compose exec -T backend alembic upgrade head

echo ""
echo "Step 4: Running all tests..."
docker compose exec -T backend pytest -q

echo ""
echo "Step 5: Running specific tests for the fixes..."
docker compose exec -T backend pytest -v tests/test_sendgrid_events.py tests/test_idempotency.py

echo ""
echo "=========================================="
echo "All tests completed!"
echo "=========================================="
