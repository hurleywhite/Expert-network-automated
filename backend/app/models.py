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
    Numeric,
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


class InterviewStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class InterviewType(str, PyEnum):
    FOLLOW_UP = "follow_up"  # Post-outreach interview
    QUALIFICATION = "qualification"  # Pre-outreach screening
    DEEP_DIVE = "deep_dive"  # Detailed expert interview


class MessageType(str, PyEnum):
    AI_QUESTION = "ai_question"
    HUMAN_RESPONSE = "human_response"
    SYSTEM = "system"


class MessageDirection(str, PyEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ExpertProfileStatus(str, PyEnum):
    SOURCED = "sourced"
    SCREENED = "screened"
    SHORTLISTED = "shortlisted"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ExpertActivityType(str, PyEnum):
    ADDED = "added"
    CALL_REQUESTED = "call_requested"
    CALL_SCHEDULED = "call_scheduled"
    CALL_COMPLETED = "call_completed"
    EMAIL_SENT = "email_sent"
    REPLY_RECEIVED = "reply_received"
    LINKEDIN_SENT = "linkedin_sent"
    LINKEDIN_CONNECTED = "linkedin_connected"


class ScreenerQuestionType(str, PyEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    FREE_TEXT = "free_text"
    YES_NO = "yes_no"
    SCALE = "scale"


class LinkedInOutreachStatus(str, PyEnum):
    PENDING = "pending"
    CONNECTION_SENT = "connection_sent"
    CONNECTED = "connected"
    MESSAGE_SENT = "message_sent"
    REPLIED = "replied"
    FAILED = "failed"


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
    headline = Column(String)
    photo_url = Column(String)
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
    sequence_number = Column(Integer, default=1, nullable=False)  # 1=initial, 2+=follow-up
    parent_draft_id = Column(UUID(as_uuid=True), ForeignKey("message_drafts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="message_drafts")
    project = relationship("ProjectBrief", back_populates="message_drafts")
    outbound_events = relationship("OutboundEvent", back_populates="message_draft")
    parent_draft = relationship("MessageDraft", remote_side="MessageDraft.id", backref="follow_ups")


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


class RejectionLearning(Base):
    """Stores rejected drafts to learn from mistakes and improve future drafts."""
    __tablename__ = "rejection_learnings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    candidate_title = Column(String)
    candidate_company = Column(String)
    rejected_subject = Column(String, nullable=False)
    rejected_body = Column(Text, nullable=False)
    inferred_issues = Column(JSON, default=list)  # Auto-detected problems
    rejected_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_rejection_learning_project", "project_id"),
    )


class InterviewTemplate(Base):
    """Templates for AI-moderated interviews with different objectives."""
    __tablename__ = "interview_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    interview_type = Column(
        Enum(
            InterviewType,
            name="interviewtype",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    opening_prompt = Column(Text, nullable=False)  # AI's introduction
    question_flow = Column(JSON, default=list)  # Structured questions
    follow_up_rules = Column(JSON, default=dict)  # How AI should follow up
    success_criteria = Column(JSON, default=dict)  # What makes a good interview
    estimated_duration_minutes = Column(Integer, default=15)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("InterviewSession", back_populates="template")


class InterviewSession(Base):
    """AI-moderated interview sessions with candidates."""
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("interview_templates.id"), nullable=False)
    
    status = Column(
        Enum(
            InterviewStatus,
            name="interviewstatus",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=InterviewStatus.SCHEDULED,
        nullable=False,
    )
    
    # Scheduling
    scheduled_for = Column(DateTime)
    timezone = Column(String)
    
    # Session info
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)
    
    # Video/Audio settings
    video_enabled = Column(Boolean, default=True)
    audio_enabled = Column(Boolean, default=True)
    recording_enabled = Column(Boolean, default=True)
    
    # AI settings
    ai_voice_id = Column(String)  # ElevenLabs voice ID
    ai_personality = Column(JSON, default=dict)  # Custom AI behavior
    
    # Results
    summary = Column(Text)
    key_insights = Column(JSON, default=list)
    qualification_score = Column(Float)
    next_steps = Column(JSON, default=list)
    
    # Technical
    meet_link = Column(String)
    recording_url = Column(String)
    transcript_url = Column(String)
    
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_interview_session_candidate", "candidate_id"),
        Index("ix_interview_session_project", "project_id"),
        Index("ix_interview_session_status", "status"),
    )

    candidate = relationship("Candidate")
    project = relationship("ProjectBrief")
    template = relationship("InterviewTemplate", back_populates="sessions")
    messages = relationship("InterviewMessage", back_populates="session")


class InterviewMessage(Base):
    """Individual messages within an AI interview session."""
    __tablename__ = "interview_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id"), nullable=False)
    
    message_type = Column(
        Enum(
            MessageType,
            name="messagetype",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    
    # Content
    text_content = Column(Text)
    audio_url = Column(String)  # Audio file URL
    duration_seconds = Column(Float)
    
    # AI analysis
    sentiment_score = Column(Float)
    emotion_detected = Column(String)
    confidence_score = Column(Float)
    
    # Timing
    timestamp_seconds = Column(Float)  # Seconds from interview start
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_interview_message_session", "session_id"),
        Index("ix_interview_message_type", "message_type"),
    )

    session = relationship("InterviewSession", back_populates="messages")


# ─── GLG-STYLE MODELS ────────────────────────────────────────────────────────


class ProjectCategory(Base):
    """Expert categories within a project (e.g., 'Systems Integrators', 'DB Product Leaders')."""
    __tablename__ = "project_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    search_criteria = Column(JSON, default=dict)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("ProjectBrief", backref="categories")
    expert_profiles = relationship("ExpertProfile", back_populates="category")


class ScreenerQuestion(Base):
    """Screening questions auto-generated from project requirements."""
    __tablename__ = "screener_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(
        Enum(ScreenerQuestionType, name="screenerquestiontype", create_type=True,
             values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    options = Column(JSON, default=list)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("ProjectBrief", backref="screener_questions")


class ExpertProfile(Base):
    """Rich AI-generated expert profile for a candidate within a project."""
    __tablename__ = "expert_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_briefs.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("project_categories.id"), nullable=True)

    ai_overview = Column(Text)
    project_expertise = Column(JSON, default=list)
    relevance_score = Column(Float)
    rate_per_hour = Column(Numeric(10, 2))
    exa_research = Column(JSON, default=dict)
    screener_responses = Column(JSON, default=dict)
    work_experience = Column(JSON, default=list)

    status = Column(
        Enum(ExpertProfileStatus, name="expertprofilestatus", create_type=True,
             values_callable=lambda x: [e.value for e in x]),
        default=ExpertProfileStatus.SOURCED,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_expert_profile_candidate_project", "candidate_id", "project_id"),
        Index("ix_expert_profile_category", "category_id"),
    )

    candidate = relationship("Candidate", backref="expert_profiles")
    project = relationship("ProjectBrief", backref="expert_profiles")
    category = relationship("ProjectCategory", back_populates="expert_profiles")
    activities = relationship("ExpertActivity", back_populates="expert_profile", order_by="ExpertActivity.created_at.desc()")
    linkedin_outreach = relationship("LinkedInOutreach", back_populates="expert_profile", uselist=False)


class ExpertActivity(Base):
    """Activity log entries for expert profiles."""
    __tablename__ = "expert_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expert_profile_id = Column(UUID(as_uuid=True), ForeignKey("expert_profiles.id"), nullable=False)
    activity_type = Column(
        Enum(ExpertActivityType, name="expertactivitytype", create_type=True,
             values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    expert_profile = relationship("ExpertProfile", back_populates="activities")


class LinkedInOutreach(Base):
    """Tracks automated LinkedIn outreach per expert."""
    __tablename__ = "linkedin_outreach"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expert_profile_id = Column(UUID(as_uuid=True), ForeignKey("expert_profiles.id"), nullable=False)
    linkedin_url = Column(String, nullable=False)
    connection_note = Column(String(300))
    follow_up_message = Column(Text)
    status = Column(
        Enum(LinkedInOutreachStatus, name="linkedinoutreachstatus", create_type=True,
             values_callable=lambda x: [e.value for e in x]),
        default=LinkedInOutreachStatus.PENDING,
        nullable=False,
    )
    sent_at = Column(DateTime)
    connected_at = Column(DateTime)
    replied_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    expert_profile = relationship("ExpertProfile", back_populates="linkedin_outreach")
