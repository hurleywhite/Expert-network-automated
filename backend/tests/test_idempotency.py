"""
Tests for send job idempotency.

Tests ISSUE 2: Idempotency key should be stable per draft (not per actor).
Multiple sends with different actors should result in exactly one outbound event and one email send.
"""
import os
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, crud
from app.workers.jobs import send_job

# Test database - use PostgreSQL to match production types (UUID, ENUM)
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/expert_outreach_test"
)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create a wrapper that prevents close() from actually closing the session
    # This is needed because send_job calls db.close() which would close our test session
    original_close = db.close

    def noop_close():
        pass  # Don't actually close - we'll close in fixture teardown

    db.close = noop_close

    # Patch SessionLocal to use test database
    with patch("app.workers.jobs.SessionLocal", return_value=db):
        yield db

    # Restore original close and close the session
    db.close = original_close
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def setup_approved_draft(db_session):
    """Create project, candidate, and approved draft ready to send."""
    # Create project
    project = models.ProjectBrief(
        name="Test Project",
        industry="Tech",
        regions=["US"],
        titles_include=["Engineer"],
    )
    db_session.add(project)
    db_session.commit()

    # Create candidate with email
    candidate = models.Candidate(
        full_name="John Doe",
        email="john.doe@example.com",
        status=models.CandidateStatus.APPROVED,
    )
    db_session.add(candidate)
    db_session.commit()

    # Create approved draft with no risk flags
    now = datetime.utcnow()
    draft = models.MessageDraft(
        candidate_id=candidate.id,
        project_id=project.id,
        subject="Test Subject",
        body="Test Body",
        facts_used=["test_fact"],
        risk_flags=[],  # Empty risk flags - safe to send
        approved_at=now,
        approved_by="tester@example.com",
        approved_hash=crud.compute_approval_hash("Test Subject", "Test Body", "tester@example.com", now),
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    return {
        "project": project,
        "candidate": candidate,
        "draft": draft,
    }


@pytest.fixture
def mock_email_service():
    """Mock EmailService to track send calls."""
    with patch("app.workers.jobs.EmailService") as MockEmailService:
        mock_instance = Mock()
        mock_instance.send_email.return_value = {
            "status": "sent",
            "message_id": "mock-message-id-123",
        }
        MockEmailService.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_rate_limiter():
    """Mock RateLimiter to always allow sending."""
    with patch("app.services.rate_limiter.RateLimiter") as MockRateLimiter:
        MockRateLimiter.get_domain_from_email.return_value = "example.com"
        MockRateLimiter.can_send_to_domain.return_value = True
        MockRateLimiter.apply_jitter_delay.return_value = None
        MockRateLimiter.increment_domain_count.return_value = None
        yield MockRateLimiter


def test_idempotency_different_actors_single_send(db_session, setup_approved_draft, mock_email_service, mock_rate_limiter):
    """
    Test that calling send_job twice with different actors results in:
    - Exactly one email send
    - Exactly one outbound event
    - Second call returns 'Already sent (idempotent)'
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # SessionLocal is already patched in db_session fixture
    # First send with actor "alice@company.com"
    result1 = send_job(draft_id, actor="alice@company.com")

    # Second send with actor "bob@company.com"
    result2 = send_job(draft_id, actor="bob@company.com")

    # Verify email was sent exactly once
    assert mock_email_service.send_email.call_count == 1

    # Verify first send succeeded
    assert result1["status"] == "sent"
    assert "event_id" in result1
    assert "message_id" in result1

    # Verify second send was idempotent
    assert "message" in result2
    assert result2["message"] == "Already sent (idempotent)"
    assert "event_id" in result2

    # Verify exactly one outbound event exists
    outbound_events = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).all()
    assert len(outbound_events) == 1

    # Verify the event is marked as SENT
    assert outbound_events[0].status == models.OutboundEventStatus.SENT
    assert outbound_events[0].provider_message_id == "mock-message-id-123"

    # Verify idempotency key format (should not include actor)
    assert outbound_events[0].idempotency_key == f"draft:{draft_id}"


def test_idempotency_same_actor_multiple_calls(db_session, setup_approved_draft, mock_email_service, mock_rate_limiter):
    """
    Test that calling send_job multiple times with the same actor is also idempotent.
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # SessionLocal is already patched in db_session fixture
    # First send
    result1 = send_job(draft_id, actor="alice@company.com")

    # Second send with same actor
    result2 = send_job(draft_id, actor="alice@company.com")

    # Third send with same actor
    result3 = send_job(draft_id, actor="alice@company.com")

    # Verify email was sent exactly once
    assert mock_email_service.send_email.call_count == 1

    # Verify first send succeeded
    assert result1["status"] == "sent"

    # Verify subsequent sends were idempotent
    assert result2["message"] == "Already sent (idempotent)"
    assert result3["message"] == "Already sent (idempotent)"

    # Verify exactly one outbound event
    outbound_events = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).all()
    assert len(outbound_events) == 1


def test_idempotency_key_format(db_session, setup_approved_draft, mock_email_service, mock_rate_limiter):
    """
    Test that idempotency key follows the format: draft:{draft_id}
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # SessionLocal is already patched in db_session fixture
    result = send_job(draft_id, actor="alice@company.com")

    assert result["status"] == "sent"

    # Check the idempotency key format
    outbound_event = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).first()

    expected_key = f"draft:{draft_id}"
    assert outbound_event.idempotency_key == expected_key
    # Verify it does NOT contain actor
    assert "alice" not in outbound_event.idempotency_key


def test_concurrent_sends_with_different_actors(db_session, setup_approved_draft, mock_email_service, mock_rate_limiter):
    """
    Test that even with different actors attempting to send concurrently,
    only one send occurs due to database locking.
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # SessionLocal is already patched in db_session fixture
    # Simulate two actors trying to send
    actors = ["alice@company.com", "bob@company.com", "charlie@company.com"]
    results = []

    for actor in actors:
        result = send_job(draft_id, actor=actor)
        results.append(result)

    # Exactly one should succeed, others should be idempotent
    sent_count = sum(1 for r in results if r.get("status") == "sent")
    idempotent_count = sum(1 for r in results if "Already sent (idempotent)" in r.get("message", ""))

    assert sent_count == 1
    assert idempotent_count == 2

    # Verify email sent exactly once
    assert mock_email_service.send_email.call_count == 1

    # Verify exactly one outbound event
    outbound_events = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).all()
    assert len(outbound_events) == 1


def test_rate_limited_does_not_create_duplicate_events(db_session, setup_approved_draft, mock_email_service):
    """
    Test that when rate limited, we don't persist outbound events (rolled back).
    This allows the job to be retried later when rate limit is lifted.
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # Mock rate limiter to deny first attempt
    # SessionLocal is already patched in db_session fixture
    with patch("app.services.rate_limiter.RateLimiter") as MockRateLimiter:
        MockRateLimiter.get_domain_from_email.return_value = "example.com"
        MockRateLimiter.can_send_to_domain.return_value = False  # Rate limited

        result = send_job(draft_id, actor="alice@company.com")

    # Verify rate limited response
    assert result["status"] == "rate_limited"
    assert "Rate limit exceeded" in result["error"]

    # Verify email was NOT sent
    assert mock_email_service.send_email.call_count == 0

    # Verify NO outbound event was created (transaction rolled back)
    # This allows the job to be retried later when rate limit is lifted
    outbound_events = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).all()
    assert len(outbound_events) == 0


def test_actor_stored_in_metadata(db_session, setup_approved_draft, mock_email_service, mock_rate_limiter):
    """
    Test that even though actor is not in the idempotency key,
    it's still stored in the metadata for audit purposes.
    """
    draft = setup_approved_draft["draft"]
    draft_id = str(draft.id)

    # SessionLocal is already patched in db_session fixture
    result = send_job(draft_id, actor="alice@company.com")

    assert result["status"] == "sent"

    # Check that actor is stored in meta
    outbound_event = db_session.query(models.OutboundEvent).filter_by(
        message_draft_id=draft.id
    ).first()

    assert outbound_event.meta is not None
    assert outbound_event.meta.get("actor") == "alice@company.com"
