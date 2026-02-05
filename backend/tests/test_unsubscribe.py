import pytest
from uuid import uuid4

from app import crud, models
from app.services.email import EmailService


def test_classify_unsubscribe_reply(db):
    """Test that unsubscribe phrases are correctly classified"""
    email_service = EmailService()

    # Test various unsubscribe phrases
    assert email_service.classify_inbound_reply("Please unsubscribe me") == "unsubscribe"
    assert email_service.classify_inbound_reply("STOP sending me emails") == "unsubscribe"
    assert email_service.classify_inbound_reply("Remove me from your list") == "unsubscribe"
    assert (
        email_service.classify_inbound_reply("I want to unsubscribe from these emails")
        == "unsubscribe"
    )


def test_classify_interested_reply(db):
    """Test that interested phrases are correctly classified"""
    email_service = EmailService()

    assert email_service.classify_inbound_reply("Yes, I'd be happy to chat") == "interested"
    assert email_service.classify_inbound_reply("Sounds good, I'm available") == "interested"
    assert email_service.classify_inbound_reply("Sure, let's talk") == "interested"


def test_classify_not_interested_reply(db):
    """Test that not interested phrases are correctly classified"""
    email_service = EmailService()

    assert email_service.classify_inbound_reply("Not interested, thanks") == "not_interested"
    assert email_service.classify_inbound_reply("No thanks") == "not_interested"
    assert (
        email_service.classify_inbound_reply("Not at this time, please don't contact me")
        == "not_interested"
    )


def test_add_to_do_not_contact(db):
    """Test adding email to do-not-contact list"""
    test_email = "test@example.com"

    # Initially should not be on list
    assert crud.is_do_not_contact(db, test_email) is False

    # Add to list
    crud.add_do_not_contact(db, test_email, "unsubscribe")

    # Now should be on list
    assert crud.is_do_not_contact(db, test_email) is True

    # Adding again should be idempotent
    crud.add_do_not_contact(db, test_email, "unsubscribe")
    assert crud.is_do_not_contact(db, test_email) is True


def test_do_not_contact_updates_candidates(db):
    """Test that adding to DNC updates all candidates with that email"""
    test_email = "candidate@example.com"

    # Create a candidate
    candidate_data = {
        "full_name": "Test Candidate",
        "email": test_email,
    }
    from app.schemas import CandidateCreate

    candidate = crud.create_candidate(db, CandidateCreate(**candidate_data))

    assert candidate.status == models.CandidateStatus.NEW

    # Add to DNC
    crud.add_do_not_contact(db, test_email, "unsubscribe")

    # Refresh candidate
    db.refresh(candidate)

    # Status should be updated
    assert candidate.status == models.CandidateStatus.DO_NOT_CONTACT


def test_send_job_blocks_do_not_contact(db):
    """Test that send job refuses to send to DNC emails"""
    from app.schemas import CandidateCreate, ProjectBriefCreate

    # Create project
    project = crud.create_project(
        db, ProjectBriefCreate(name="Test Project", industry="Tech")
    )

    # Create candidate
    test_email = "blocked@example.com"
    candidate = crud.create_candidate(
        db,
        CandidateCreate(
            full_name="Blocked Person",
            email=test_email,
        ),
    )

    # Create draft
    draft = crud.create_draft(
        db,
        candidate_id=candidate.id,
        project_id=project.id,
        subject="Test",
        body="Test body",
        facts_used=[],
        risk_flags=[],
    )

    # Approve draft
    crud.approve_draft(db, draft.id, "test_user")

    # Add to DNC
    crud.add_do_not_contact(db, test_email, "test")

    # Import send_job
    from app.workers.jobs import send_job

    # Try to send - should return error
    result = send_job(str(draft.id), "test_user")

    assert "error" in result
    assert "do-not-contact" in result["error"].lower()
