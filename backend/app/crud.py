import hashlib
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models, schemas


def create_audit_log(
    db: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    meta: Optional[dict] = None,
) -> models.AuditLog:
    """Create audit log entry"""
    log = models.AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta or {},
    )
    db.add(log)
    db.commit()
    return log


# Projects
def create_project(db: Session, project: schemas.ProjectBriefCreate) -> models.ProjectBrief:
    db_project = models.ProjectBrief(**project.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    create_audit_log(db, "system", "create", "project", str(db_project.id))
    return db_project


def get_projects(db: Session, skip: int = 0, limit: int = 100) -> List[models.ProjectBrief]:
    return db.query(models.ProjectBrief).offset(skip).limit(limit).all()


def get_project(db: Session, project_id: UUID) -> Optional[models.ProjectBrief]:
    return db.query(models.ProjectBrief).filter(models.ProjectBrief.id == project_id).first()


# Candidates
def create_candidate(db: Session, candidate: schemas.CandidateCreate) -> models.Candidate:
    candidate_data = candidate.model_dump(
        exclude={"source_name", "source_url", "source_payload"}
    )
    db_candidate = models.Candidate(**candidate_data)
    db.add(db_candidate)
    db.commit()
    db.refresh(db_candidate)

    # Create source if provided
    if candidate.source_name:
        db_source = models.CandidateSource(
            candidate_id=db_candidate.id,
            source_name=candidate.source_name,
            source_url=candidate.source_url,
            source_payload=candidate.source_payload,
        )
        db.add(db_source)
        db.commit()

    create_audit_log(db, "system", "create", "candidate", str(db_candidate.id))
    return db_candidate


def bulk_create_candidates(
    db: Session, candidates: List[schemas.CandidateCreate]
) -> List[models.Candidate]:
    created = []
    for candidate in candidates:
        # Check if email already exists
        if candidate.email:
            existing = (
                db.query(models.Candidate)
                .filter(models.Candidate.email == candidate.email)
                .first()
            )
            if existing:
                continue
        created.append(create_candidate(db, candidate))
    return created


def get_candidates(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    region: Optional[str] = None,
    project_id: Optional[UUID] = None,
) -> List[models.Candidate]:
    query = db.query(models.Candidate)

    if status:
        query = query.filter(models.Candidate.status == status)
    if company:
        query = query.filter(models.Candidate.company.ilike(f"%{company}%"))
    if title:
        query = query.filter(models.Candidate.title.ilike(f"%{title}%"))
    if region:
        query = query.filter(models.Candidate.region == region)
    if project_id:
        query = query.join(models.Score).filter(models.Score.project_id == project_id)

    return query.offset(skip).limit(limit).all()


def get_candidate(db: Session, candidate_id: UUID) -> Optional[models.Candidate]:
    return db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()


def update_candidate_status(
    db: Session, candidate_id: UUID, status: models.CandidateStatus
) -> Optional[models.Candidate]:
    candidate = get_candidate(db, candidate_id)
    if candidate:
        candidate.status = status
        db.commit()
        db.refresh(candidate)
    return candidate


# Scores
def create_score(
    db: Session,
    candidate_id: UUID,
    project_id: UUID,
    hard_pass: bool,
    score: Optional[float],
    reasons: List[str],
) -> models.Score:
    db_score = models.Score(
        candidate_id=candidate_id,
        project_id=project_id,
        hard_pass=hard_pass,
        score=score,
        reasons=reasons,
    )
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    create_audit_log(db, "system", "score", "candidate", str(candidate_id))
    return db_score


# Drafts
def create_draft(
    db: Session,
    candidate_id: UUID,
    project_id: UUID,
    subject: str,
    body: str,
    facts_used: List[str],
    risk_flags: List[str],
) -> models.MessageDraft:
    db_draft = models.MessageDraft(
        candidate_id=candidate_id,
        project_id=project_id,
        subject=subject,
        body=body,
        facts_used=facts_used,
        risk_flags=risk_flags,
    )
    db.add(db_draft)
    db.commit()
    db.refresh(db_draft)

    # Update candidate status
    update_candidate_status(db, candidate_id, models.CandidateStatus.DRAFTED)

    create_audit_log(db, "system", "draft", "candidate", str(candidate_id))
    return db_draft


def get_draft(db: Session, draft_id: UUID) -> Optional[models.MessageDraft]:
    return db.query(models.MessageDraft).filter(models.MessageDraft.id == draft_id).first()


def compute_approval_hash(subject: str, body: str, approved_by: str, approved_at: datetime) -> str:
    """Compute SHA256 hash for draft approval integrity."""
    content = f"{subject}|{body}|{approved_by}|{approved_at.isoformat()}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def verify_approval_hash(draft: models.MessageDraft) -> bool:
    """Verify draft hasn't been modified since approval."""
    if not draft.approved_hash or not draft.approved_at or not draft.approved_by:
        return False
    expected_hash = compute_approval_hash(
        draft.subject, draft.body, draft.approved_by, draft.approved_at
    )
    return draft.approved_hash == expected_hash


def approve_draft(db: Session, draft_id: UUID, approved_by: str) -> Optional[models.MessageDraft]:
    draft = get_draft(db, draft_id)
    if draft:
        now = datetime.utcnow()
        draft.approved_at = now
        draft.approved_by = approved_by
        # Store approval hash for integrity verification
        draft.approved_hash = compute_approval_hash(draft.subject, draft.body, approved_by, now)
        db.commit()
        db.refresh(draft)

        # Update candidate status
        update_candidate_status(db, draft.candidate_id, models.CandidateStatus.APPROVED)

        create_audit_log(
            db, approved_by, "approve", "draft", str(draft_id), {"candidate_id": str(draft.candidate_id)}
        )
    return draft


# Do Not Contact
def is_do_not_contact(db: Session, email: str) -> bool:
    return db.query(models.DoNotContact).filter(models.DoNotContact.email == email).first() is not None


def add_do_not_contact(db: Session, email: str, reason: str) -> models.DoNotContact:
    # Check if already exists
    existing = db.query(models.DoNotContact).filter(models.DoNotContact.email == email).first()
    if existing:
        return existing

    db_dnc = models.DoNotContact(email=email, reason=reason)
    db.add(db_dnc)
    db.commit()
    db.refresh(db_dnc)

    # Update all candidates with this email
    candidates = db.query(models.Candidate).filter(models.Candidate.email == email).all()
    for candidate in candidates:
        update_candidate_status(db, candidate.id, models.CandidateStatus.DO_NOT_CONTACT)

    create_audit_log(db, "system", "do_not_contact", "email", email)
    return db_dnc


# Conversations
def get_or_create_conversation(
    db: Session, candidate_id: UUID, project_id: UUID
) -> models.Conversation:
    conversation = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.candidate_id == candidate_id,
            models.Conversation.project_id == project_id,
        )
        .first()
    )
    if not conversation:
        conversation = models.Conversation(
            candidate_id=candidate_id,
            project_id=project_id,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    return conversation


def create_conversation_message(
    db: Session,
    conversation_id: UUID,
    direction: models.MessageDirection,
    from_addr: str,
    to_addr: str,
    subject: Optional[str],
    body_text: Optional[str],
    raw_payload: Optional[dict],
) -> models.ConversationMessage:
    message = models.ConversationMessage(
        conversation_id=conversation_id,
        direction=direction,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body_text=body_text,
        raw_payload=raw_payload,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def update_conversation_status(
    db: Session, conversation_id: UUID, status: models.ConversationStatus
) -> Optional[models.Conversation]:
    conversation = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
    if conversation:
        conversation.last_status = status
        db.commit()
        db.refresh(conversation)

        # Update candidate if replied
        if status == models.ConversationStatus.INTERESTED:
            update_candidate_status(db, conversation.candidate_id, models.CandidateStatus.REPLIED)
    return conversation


# Outbound Events
def create_outbound_event(
    db: Session,
    message_draft_id: UUID,
    candidate_id: UUID,
    project_id: UUID,
    idempotency_key: str,
    provider_message_id: Optional[str] = None,
    status: models.OutboundEventStatus = models.OutboundEventStatus.QUEUED,
    meta: Optional[dict] = None,
) -> models.OutboundEvent:
    # Check if already exists (idempotency)
    existing = (
        db.query(models.OutboundEvent)
        .filter(models.OutboundEvent.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing

    event = models.OutboundEvent(
        message_draft_id=message_draft_id,
        candidate_id=candidate_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
        provider_message_id=provider_message_id,
        status=status,
        meta=meta,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_or_create_outbound_event_with_lock(
    db: Session,
    message_draft_id: UUID,
    candidate_id: UUID,
    project_id: UUID,
    idempotency_key: str,
) -> Tuple[models.OutboundEvent, bool]:
    """Get or create outbound event with pessimistic locking.

    Returns: (outbound_event, is_new)
    """
    # Try to get existing event with lock
    event = (
        db.query(models.OutboundEvent)
        .filter(models.OutboundEvent.idempotency_key == idempotency_key)
        .with_for_update()
        .first()
    )

    if event:
        return (event, False)

    # Create new event
    event = models.OutboundEvent(
        message_draft_id=message_draft_id,
        candidate_id=candidate_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
        status=models.OutboundEventStatus.QUEUED,
    )
    db.add(event)
    db.flush()

    return (event, True)


def update_outbound_event_status(
    db: Session,
    event_id: UUID,
    status: models.OutboundEventStatus,
    provider_message_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> Optional[models.OutboundEvent]:
    event = db.query(models.OutboundEvent).filter(models.OutboundEvent.id == event_id).first()
    if event:
        event.status = status
        if provider_message_id:
            event.provider_message_id = provider_message_id
        if meta:
            event.meta = meta
        db.commit()
        db.refresh(event)
    return event
