import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# Enums
class CandidateStatus(str, PyEnum):
    NEW = "new"
    ENRICHED = "enriched"
    DRAFTED = "drafted"
    APPROVED = "approved"
    SENT = "sent"
    REPLIED = "replied"
    DO_NOT_CONTACT = "do_not_contact"


class OutboundEventStatus(str, PyEnum):
    QUEUED = "queued"
    SENT = "sent"
    BOUNCED = "bounced"
    FAILED = "failed"


class ConversationStatus(str, PyEnum):
    NONE = "none"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    REFERRAL = "referral"
    OOO = "ooo"
    UNSUBSCRIBE = "unsubscribe"
    UNKNOWN = "unknown"


class MessageDirection(str, PyEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


# Models
class ProjectBrief(Base):
    __tablename__ = "project_briefs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    industry = Column(String)
    subvertical = Column(String)
    company_size_min = Column(Integer)
    regions = Column(JSON, default=list)
    titles_include = Column(JSON, default=list)
    titles_exclude = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    exclusions = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scores = relationship("Score", back_populates="project")
    message_drafts = relationship("MessageDraft", back_populates="project")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String)
    last_name = Column(String)
    full_name = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    company_employee_count = Column(Integer)
    region = Column(String)
    linkedin_url = Column(String)
    email = Column(String)
    email_verified = Column(Boolean, default=False)
    status = Column(
        Enum(
            CandidateStatus,
            name="candidatestatus",
            create_type=False,  # Use existing type from migration
            values_callable=lambda x: [e.value for e in x],
        ),
        default=CandidateStatus.NEW,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("email", name="uq_candidate_email"),
        Index("ix_candidate_status", "status"),
        Index("ix_candidate_company", "company"),
        Index("ix_candidate_email", "email"),
    )

    sources = relationship("CandidateSource", back_populates="candidate")
    enrichments = relationship("Enrichment", back_populates="candidate")
    scores = relationship("Score", back_populates="candidate")
    message_drafts = relationship("MessageDraft", back_populates="candidate")
    outbound_events = relationship("OutboundEvent", back_populates="candidate")
    conversations = relationship("Conversation", back_populates="candidate")


class CandidateSource(Base):
    __tablename__ = "candidate_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String)
    source_payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="sources")


class Enrichment(Base):
    __tablename__ = "enrichments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    provider = Column(String, nullable=False)
    payload = Column(JSON)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="enrichments")


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    hard_pass = Column(Boolean, default=False, nullable=False)
    score = Column(Float)
    reasons = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="scores")
    project = relationship("ProjectBrief", back_populates="scores")

    __table_args__ = (Index("ix_score_candidate_project", "candidate_id", "project_id"),)


class MessageDraft(Base):
    __tablename__ = "message_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    facts_used = Column(JSON, default=list)
    risk_flags = Column(JSON, default=list)
    approved_at = Column(DateTime)
    approved_by = Column(String)
    approved_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="message_drafts")
    project = relationship("ProjectBrief", back_populates="message_drafts")
    outbound_events = relationship("OutboundEvent", back_populates="message_draft")


class OutboundEvent(Base):
    __tablename__ = "outbound_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_draft_id = Column(UUID(as_uuid=True), ForeignKey("message_drafts.id"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    provider_message_id = Column(String)
    idempotency_key = Column(String, nullable=False)
    status = Column(
        Enum(
            OutboundEventStatus,
            name="outboundeventstatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=OutboundEventStatus.QUEUED,
        nullable=False,
    )
    meta = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbound_idempotency_key"),
    )

    message_draft = relationship("MessageDraft", back_populates="outbound_events")
    candidate = relationship("Candidate", back_populates="outbound_events")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    last_status = Column(
        Enum(
            ConversationStatus,
            name="conversationstatus",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ConversationStatus.NONE,
        nullable=False,
    )
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    direction = Column(
        Enum(
            MessageDirection,
            name="messagedirection",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    from_addr = Column(String, nullable=False)
    to_addr = Column(String, nullable=False)
    subject = Column(String)
    body_text = Column(Text)
    raw_payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")


class DoNotContact(Base):
    __tablename__ = "do_not_contact"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("email", name="uq_do_not_contact_email"),)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    meta = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor", "actor"),
    )
