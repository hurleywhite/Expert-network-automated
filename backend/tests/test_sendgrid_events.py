"""
Tests for SendGrid event webhook handling.

Tests ISSUE 1: SendGrid sends both "spamreport" and "spam_report" - both should be handled identically.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app import models

# Test database - use PostgreSQL to match production types (UUID, ENUM)
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/expert_outreach_test"
)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_candidate(db_session):
    """Create a test candidate."""
    candidate = models.Candidate(
        full_name="Test User",
        email="test@example.com",
        status=models.CandidateStatus.NEW,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate


@pytest.fixture
def test_outbound_event(db_session, test_candidate):
    """Create a test project, draft, and outbound event."""
    # Create project
    project = models.ProjectBrief(
        name="Test Project",
        industry="Tech",
    )
    db_session.add(project)
    db_session.commit()

    # Create draft
    draft = models.MessageDraft(
        candidate_id=test_candidate.id,
        project_id=project.id,
        subject="Test Subject",
        body="Test Body",
        facts_used=[],
        risk_flags=[],
    )
    db_session.add(draft)
    db_session.commit()

    # Create outbound event
    event = models.OutboundEvent(
        message_draft_id=draft.id,
        candidate_id=test_candidate.id,
        project_id=project.id,
        idempotency_key="test-key",
        provider_message_id="sg-test-123",
        status=models.OutboundEventStatus.SENT,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_spamreport_no_underscore(client, db_session, test_candidate):
    """Test that 'spamreport' (no underscore) is handled correctly."""
    payload = [
        {
            "event": "spamreport",
            "email": "test@example.com",
            "sg_message_id": "test-msg-123",
            "reason": "User marked as spam",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    assert data["results"][0]["event"] == "spamreport"
    assert data["results"][0]["status"] == "processed"

    # Verify do_not_contact entry created
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_spamreport"

    # Verify candidate status updated to DO_NOT_CONTACT
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_spam_report_with_underscore(client, db_session, test_candidate):
    """Test that 'spam_report' (with underscore) is handled identically to 'spamreport'."""
    payload = [
        {
            "event": "spam_report",
            "email": "test@example.com",
            "sg_message_id": "test-msg-456",
            "reason": "User marked as spam",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    # Event should be normalized to "spamreport"
    assert data["results"][0]["event"] == "spamreport"
    assert data["results"][0]["status"] == "processed"

    # Verify do_not_contact entry created with normalized name
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_spamreport"

    # Verify candidate status updated
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_bounce_event(client, db_session, test_candidate, test_outbound_event):
    """Test that bounce events are handled correctly."""
    payload = [
        {
            "event": "bounce",
            "email": "test@example.com",
            "sg_message_id": "sg-test-123",
            "reason": "550 User unknown",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1

    # Verify do_not_contact entry
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_bounce"

    # Verify outbound event status updated
    db_session.refresh(test_outbound_event)
    assert test_outbound_event.status == models.OutboundEventStatus.BOUNCED
    assert test_outbound_event.meta["event_type"] == "bounce"

    # Verify candidate status updated
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_dropped_event(client, db_session, test_candidate):
    """Test that dropped events trigger suppression."""
    payload = [
        {
            "event": "dropped",
            "email": "test@example.com",
            "reason": "Unsubscribed Address",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1

    # Verify suppression
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_dropped"

    # Verify candidate status
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_blocked_event(client, db_session, test_candidate):
    """Test that blocked events trigger suppression."""
    payload = [
        {
            "event": "blocked",
            "email": "test@example.com",
            "reason": "Blocked by spam filter",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1

    # Verify suppression
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_blocked"

    # Verify candidate status
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_unsubscribe_event(client, db_session, test_candidate):
    """Test that unsubscribe events trigger suppression."""
    payload = [
        {
            "event": "unsubscribe",
            "email": "test@example.com",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1

    # Verify suppression
    dnc = db_session.query(models.DoNotContact).filter_by(email="test@example.com").first()
    assert dnc is not None
    assert dnc.reason == "sendgrid_unsubscribe"

    # Verify candidate status
    db_session.refresh(test_candidate)
    assert test_candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_mixed_case_event_normalization(client, db_session, test_candidate):
    """Test that event names are normalized to lowercase."""
    payload = [
        {
            "event": "SpamReport",  # Mixed case
            "email": "test@example.com",
        }
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    # Should be normalized to lowercase "spamreport"
    assert data["results"][0]["event"] == "spamreport"


def test_batch_events(client, db_session):
    """Test processing multiple events in one batch."""
    # Create multiple candidates
    for i in range(3):
        candidate = models.Candidate(
            full_name=f"Test User {i}",
            email=f"test{i}@example.com",
            status=models.CandidateStatus.NEW,
        )
        db_session.add(candidate)
    db_session.commit()

    payload = [
        {"event": "bounce", "email": "test0@example.com"},
        {"event": "spamreport", "email": "test1@example.com"},
        {"event": "spam_report", "email": "test2@example.com"},  # Should normalize to spamreport
    ]

    response = client.post(
        "/webhooks/sendgrid-events",
        json=payload,
        headers={"X-Webhook-Secret": "dev-webhook-secret-change-in-production"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 3

    # Verify all suppressions created
    dnc_count = db_session.query(models.DoNotContact).count()
    assert dnc_count == 3

    # Verify all candidates updated
    for i in range(3):
        candidate = db_session.query(models.Candidate).filter_by(email=f"test{i}@example.com").first()
        assert candidate.status == models.CandidateStatus.DO_NOT_CONTACT
