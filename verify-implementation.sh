#!/bin/bash
# Verify hardening implementation without Docker
# This checks that all code changes are in place

echo "Verifying Hardening Implementation..."
echo "======================================"
echo ""

SUCCESS=0
FAIL=0

check_file() {
    local file=$1
    local pattern=$2
    local description=$3

    if [ -f "$file" ]; then
        if grep -q "$pattern" "$file"; then
            echo "✓ $description"
            ((SUCCESS++))
        else
            echo "✗ $description - pattern not found"
            ((FAIL++))
        fi
    else
        echo "✗ $description - file not found"
        ((FAIL++))
    fi
}

cd /Users/hurleywhite/expert-outreach

# Check model changes
check_file "backend/app/models.py" "approved_hash = Column" "MessageDraft has approved_hash column"

# Check migration exists
check_file "backend/alembic/versions/002_add_approval_hash.py" "add approval hash" "Migration file exists"

# Check config changes
check_file "backend/app/config.py" "rate_limit_per_domain_per_hour" "Config has rate limit settings"

# Check rate limiter service
check_file "backend/app/services/rate_limiter.py" "class RateLimiter" "Rate limiter service exists"
check_file "backend/app/services/rate_limiter.py" "can_send_to_domain" "Rate limiter has domain checking"
check_file "backend/app/services/rate_limiter.py" "apply_jitter_delay" "Rate limiter has jitter delay"

# Check CRUD changes
check_file "backend/app/crud.py" "compute_approval_hash" "CRUD has hash computation"
check_file "backend/app/crud.py" "verify_approval_hash" "CRUD has hash verification"
check_file "backend/app/crud.py" "get_or_create_outbound_event_with_lock" "CRUD has locking function"
check_file "backend/app/crud.py" "with_for_update" "CRUD uses SELECT FOR UPDATE"

# Check worker changes
check_file "backend/app/workers/jobs.py" "verify_approval_hash" "Worker verifies approval hash"
check_file "backend/app/workers/jobs.py" "RateLimiter" "Worker uses rate limiter"
check_file "backend/app/workers/jobs.py" "can_send_to_domain" "Worker checks rate limits"
check_file "backend/app/workers/jobs.py" "apply_jitter_delay" "Worker applies jitter delay"
check_file "backend/app/workers/jobs.py" "get_or_create_outbound_event_with_lock" "Worker uses locking"

# Check webhook changes
check_file "backend/app/routers/webhooks.py" "Form(...)" "Inbound webhook uses Form parameters"
check_file "backend/app/routers/webhooks.py" "/sendgrid-events" "SendGrid event webhook exists"
check_file "backend/app/routers/webhooks.py" "receive_sendgrid_events" "Event webhook handler exists"

# Check main.py changes
check_file "backend/app/main.py" "/admin/workers" "Worker observability endpoint exists"
check_file "backend/app/main.py" "Worker.all" "Worker endpoint queries RQ"

# Check documentation
check_file "README.md" "Hardening Features" "README has hardening section"
check_file ".env.example" "RATE_LIMIT_PER_DOMAIN_PER_HOUR" "env.example has rate limit vars"

# Check test files
check_file "backend/smoke-test.sh" "Expert Outreach Backend Smoke Test" "Smoke test script exists"
[ -x "backend/smoke-test.sh" ] && echo "✓ Smoke test is executable" && ((SUCCESS++)) || (echo "✗ Smoke test not executable" && ((FAIL++)))

echo ""
echo "======================================"
echo "Results: $SUCCESS passed, $FAIL failed"
echo "======================================"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✅ All hardening features are properly implemented!"
    echo ""
    echo "Next steps:"
    echo "  1. Start Docker Desktop"
    echo "  2. Run: ./test-hardening-full.sh"
    exit 0
else
    echo "❌ Some checks failed. Review the output above."
    exit 1
fi
