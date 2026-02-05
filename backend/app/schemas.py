from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models import CandidateStatus, ConversationStatus, OutboundEventStatus


# Project Schemas
class ProjectBriefCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    subvertical: Optional[str] = None
    company_size_min: Optional[int] = None
    regions: List[str] = Field(default_factory=list)
    titles_include: List[str] = Field(default_factory=list)
    titles_exclude: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)


class ProjectBriefResponse(BaseModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    subvertical: Optional[str] = None
    company_size_min: Optional[int] = None
    regions: List[str]
    titles_include: List[str]
    titles_exclude: List[str]
    keywords: List[str]
    exclusions: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Candidate Schemas
class CandidateCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    title: Optional[str] = None
    company: Optional[str] = None
    company_employee_count: Optional[int] = None
    region: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_payload: Optional[dict] = None


class CandidateBulkCreate(BaseModel):
    candidates: List[CandidateCreate]


class CandidateResponse(BaseModel):
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    title: Optional[str] = None
    company: Optional[str] = None
    company_employee_count: Optional[int] = None
    region: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    email_verified: bool
    status: CandidateStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Score Schemas
class ScoreResponse(BaseModel):
    id: int
    candidate_id: UUID
    project_id: UUID
    hard_pass: bool
    score: Optional[float] = None
    reasons: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Draft Schemas
class MessageDraftResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    project_id: UUID
    subject: str
    body: str
    facts_used: List[str]
    risk_flags: List[str]
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DraftApproval(BaseModel):
    approved_by: str


class DraftSend(BaseModel):
    actor: str


# Webhook Schemas
class InboundEmailPayload(BaseModel):
    """SendGrid Inbound Parse payload (simplified)"""

    to: str
    from_email: str = Field(alias="from")
    subject: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    headers: Optional[dict] = None
    envelope: Optional[dict] = None

    model_config = {"populate_by_name": True}


# Job Response
class JobEnqueuedResponse(BaseModel):
    job_id: str
    message: str
