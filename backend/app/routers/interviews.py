"""
Interview API endpoints for AI-moderated interviews
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db
from app.deps import verify_api_key
from app.services.interview_service import interview_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic schemas for interview requests/responses
class InterviewTemplateCreate(schemas.BaseModel):
    name: str
    description: Optional[str] = ""
    interview_type: models.InterviewType
    
    
class InterviewTemplateResponse(schemas.BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    interview_type: models.InterviewType
    estimated_duration_minutes: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class InterviewSessionCreate(schemas.BaseModel):
    candidate_id: UUID
    project_id: UUID
    template_id: UUID
    scheduled_for: datetime
    timezone: str = "UTC"
    video_enabled: bool = True
    ai_voice_id: Optional[str] = None


class InterviewSessionResponse(schemas.BaseModel):
    id: UUID
    candidate_id: UUID
    project_id: UUID
    template_id: UUID
    status: models.InterviewStatus
    scheduled_for: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    meet_link: Optional[str]
    summary: Optional[str]
    qualification_score: Optional[float]
    
    class Config:
        from_attributes = True


class HumanResponseRequest(schemas.BaseModel):
    text: str
    timestamp_seconds: float
    audio_url: Optional[str] = None


class InterviewMessageResponse(schemas.BaseModel):
    id: UUID
    message_type: models.MessageType
    text_content: Optional[str]
    audio_url: Optional[str]
    timestamp_seconds: float
    sentiment_score: Optional[float]
    emotion_detected: Optional[str]
    
    class Config:
        from_attributes = True


@router.get("/templates", response_model=List[InterviewTemplateResponse])
async def list_interview_templates(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """List all interview templates."""
    templates = db.query(models.InterviewTemplate).all()
    return templates


@router.post("/templates", response_model=InterviewTemplateResponse)
async def create_interview_template(
    template_data: InterviewTemplateCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Create a new interview template."""
    template = await interview_service.create_interview_template(
        db=db,
        name=template_data.name,
        interview_type=template_data.interview_type,
        description=template_data.description,
        created_by="api_user"
    )
    return template


@router.get("/templates/{template_id}", response_model=InterviewTemplateResponse)
async def get_interview_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get a specific interview template."""
    template = db.query(models.InterviewTemplate).filter(
        models.InterviewTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview template not found"
        )
    
    return template


@router.post("/sessions", response_model=InterviewSessionResponse)
async def schedule_interview(
    session_data: InterviewSessionCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Schedule a new AI interview session."""
    
    # Verify candidate exists
    candidate = db.query(models.Candidate).filter(
        models.Candidate.id == session_data.candidate_id
    ).first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found"
        )
    
    # Verify project exists
    project = db.query(models.ProjectBrief).filter(
        models.ProjectBrief.id == session_data.project_id
    ).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Verify template exists
    template = db.query(models.InterviewTemplate).filter(
        models.InterviewTemplate.id == session_data.template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview template not found"
        )
    
    session = await interview_service.schedule_interview(
        db=db,
        candidate_id=session_data.candidate_id,
        project_id=session_data.project_id,
        template_id=session_data.template_id,
        scheduled_for=session_data.scheduled_for,
        timezone=session_data.timezone,
        video_enabled=session_data.video_enabled,
        ai_voice_id=session_data.ai_voice_id,
        created_by="api_user"
    )
    
    return session


@router.get("/sessions", response_model=List[InterviewSessionResponse])
async def list_interview_sessions(
    project_id: Optional[UUID] = None,
    candidate_id: Optional[UUID] = None,
    status: Optional[models.InterviewStatus] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """List interview sessions with optional filters."""
    
    query = db.query(models.InterviewSession)
    
    if project_id:
        query = query.filter(models.InterviewSession.project_id == project_id)
    
    if candidate_id:
        query = query.filter(models.InterviewSession.candidate_id == candidate_id)
    
    if status:
        query = query.filter(models.InterviewSession.status == status)
    
    sessions = query.limit(limit).all()
    return sessions


@router.get("/sessions/{session_id}", response_model=InterviewSessionResponse)
async def get_interview_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get a specific interview session."""
    
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found"
        )
    
    return session


@router.post("/sessions/{session_id}/start")
async def start_interview_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Start an interview session."""
    
    try:
        result = await interview_service.start_interview(db, session_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/respond")
async def submit_human_response(
    session_id: UUID,
    response: HumanResponseRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Submit a human response to the AI interview."""
    
    try:
        result = await interview_service.process_human_response(
            db=db,
            session_id=session_id,
            response_text=response.text,
            timestamp_seconds=response.timestamp_seconds,
            audio_url=response.audio_url
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/complete")
async def complete_interview_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Complete an interview session."""
    
    try:
        result = await interview_service.complete_interview(db, session_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/sessions/{session_id}/messages", response_model=List[InterviewMessageResponse])
async def get_interview_messages(
    session_id: UUID,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get all messages from an interview session."""
    
    # Verify session exists
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found"
        )
    
    messages = db.query(models.InterviewMessage).filter(
        models.InterviewMessage.session_id == session_id
    ).order_by(models.InterviewMessage.timestamp_seconds).all()
    
    return messages


@router.get("/sessions/{session_id}/transcript")
async def get_interview_transcript(
    session_id: UUID,
    format: str = "text",  # text, json, or html
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get interview transcript in various formats."""
    
    # Verify session exists
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found"
        )
    
    messages = db.query(models.InterviewMessage).filter(
        models.InterviewMessage.session_id == session_id
    ).order_by(models.InterviewMessage.timestamp_seconds).all()
    
    if format == "text":
        transcript = []
        for msg in messages:
            role = "AI" if msg.message_type == models.MessageType.AI_QUESTION else "Human"
            timestamp = f"{int(msg.timestamp_seconds // 60):02d}:{int(msg.timestamp_seconds % 60):02d}"
            transcript.append(f"[{timestamp}] {role}: {msg.text_content}")
        
        return {"transcript": "\n".join(transcript)}
    
    elif format == "json":
        return {
            "session_id": session_id,
            "messages": [
                {
                    "timestamp": msg.timestamp_seconds,
                    "type": msg.message_type.value,
                    "text": msg.text_content,
                    "audio_url": msg.audio_url,
                    "sentiment": msg.sentiment_score,
                    "emotion": msg.emotion_detected
                }
                for msg in messages
            ]
        }
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be 'text' or 'json'"
        )


# Quick API to create default templates
@router.post("/setup-default-templates")
async def setup_default_templates(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Create default interview templates for quick setup."""
    
    templates = []
    
    # Follow-up interview template
    follow_up = await interview_service.create_interview_template(
        db=db,
        name="Expert Follow-Up Interview",
        interview_type=models.InterviewType.FOLLOW_UP,
        description="Follow-up interview for prospects who responded to outreach",
        created_by="api_user"
    )
    templates.append(follow_up)
    
    # Qualification template  
    qualification = await interview_service.create_interview_template(
        db=db,
        name="Expert Qualification Screen",
        interview_type=models.InterviewType.QUALIFICATION,
        description="Quick qualification to assess expertise level",
        created_by="api_user"
    )
    templates.append(qualification)
    
    # Deep dive template
    deep_dive = await interview_service.create_interview_template(
        db=db,
        name="Expert Deep-Dive Consultation",
        interview_type=models.InterviewType.DEEP_DIVE,
        description="Detailed expert interview for specific topics",
        created_by="api_user"
    )
    templates.append(deep_dive)
    
    return {
        "message": "Default interview templates created",
        "templates": [
            {"id": t.id, "name": t.name, "type": t.interview_type}
            for t in templates
        ]
    }