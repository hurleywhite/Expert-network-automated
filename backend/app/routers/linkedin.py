"""
LinkedIn Outreach Router — Generate and send automated LinkedIn messages.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import verify_api_key
from app.models import (
    ExpertActivity,
    ExpertActivityType,
    ExpertProfile,
    LinkedInOutreach,
    LinkedInOutreachStatus,
    ProjectBrief,
)
from app.services.linkedin_outreach import (
    generate_connection_note,
    generate_followup_message,
    send_linkedin_connection,
    send_linkedin_message,
)

router = APIRouter(
    prefix="/linkedin",
    tags=["linkedin"],
    dependencies=[Depends(verify_api_key)],
)


class LinkedInOutreachRequest(BaseModel):
    min_relevance_score: float = 50.0
    limit: int = 20
    auto_send: bool = False  # If True, sends immediately. If False, queues for review.
    sender_name: str = "Research Team"


class LinkedInSendRequest(BaseModel):
    session_cookie: Optional[str] = None


# ─── GENERATE OUTREACH ────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/generate-outreach")
async def generate_linkedin_outreach(
    project_id: str,
    request: LinkedInOutreachRequest,
    db: Session = Depends(get_db),
):
    """Generate personalized LinkedIn connection notes and follow-up messages for shortlisted experts."""
    project = db.query(ProjectBrief).filter(ProjectBrief.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get experts with high enough relevance score and LinkedIn URLs
    profiles = (
        db.query(ExpertProfile)
        .options(joinedload(ExpertProfile.candidate), joinedload(ExpertProfile.linkedin_outreach))
        .filter(
            ExpertProfile.project_id == project_id,
            ExpertProfile.relevance_score >= request.min_relevance_score,
        )
        .limit(request.limit)
        .all()
    )

    generated = 0
    skipped = 0
    errors = 0

    for profile in profiles:
        candidate = profile.candidate

        # Skip if no LinkedIn URL
        if not candidate.linkedin_url:
            skipped += 1
            continue

        # Skip if already has outreach
        if profile.linkedin_outreach:
            skipped += 1
            continue

        try:
            # Generate connection note
            note = await generate_connection_note(
                expert_name=candidate.full_name,
                expert_title=candidate.title or "",
                expert_company=candidate.company or "",
                project_description=project.name,
                project_expertise=profile.project_expertise or [],
            )

            # Generate follow-up message
            followup = await generate_followup_message(
                expert_name=candidate.full_name,
                expert_title=candidate.title or "",
                expert_company=candidate.company or "",
                project_description=project.name,
                project_expertise=profile.project_expertise or [],
                rate_per_hour=float(profile.rate_per_hour) if profile.rate_per_hour else None,
                sender_name=request.sender_name,
            )

            # Store outreach record
            outreach = LinkedInOutreach(
                id=uuid.uuid4(),
                expert_profile_id=profile.id,
                linkedin_url=candidate.linkedin_url,
                connection_note=note,
                follow_up_message=followup,
                status=LinkedInOutreachStatus.PENDING,
                created_at=datetime.utcnow(),
            )
            db.add(outreach)
            generated += 1

        except Exception as e:
            errors += 1

    db.commit()

    return {
        "project_id": project_id,
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }


# ─── VIEW STATUS ──────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/outreach-status")
def get_linkedin_outreach_status(project_id: str, db: Session = Depends(get_db)):
    """View LinkedIn outreach status across all experts in a project."""
    outreach_records = (
        db.query(LinkedInOutreach)
        .join(ExpertProfile)
        .options(
            joinedload(LinkedInOutreach.expert_profile).joinedload(ExpertProfile.candidate),
        )
        .filter(ExpertProfile.project_id == project_id)
        .all()
    )

    results = []
    status_counts = {}
    for o in outreach_records:
        status = o.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
        candidate = o.expert_profile.candidate
        results.append({
            "id": str(o.id),
            "expert_id": str(o.expert_profile_id),
            "full_name": candidate.full_name,
            "title": candidate.title,
            "company": candidate.company,
            "linkedin_url": o.linkedin_url,
            "connection_note": o.connection_note,
            "follow_up_message": o.follow_up_message,
            "status": status,
            "sent_at": o.sent_at.isoformat() if o.sent_at else None,
            "connected_at": o.connected_at.isoformat() if o.connected_at else None,
            "error_message": o.error_message,
        })

    return {
        "project_id": project_id,
        "total": len(results),
        "status_breakdown": status_counts,
        "outreach": results,
    }


# ─── SEND INDIVIDUAL ─────────────────────────────────────────────────────────


@router.post("/experts/{expert_id}/send-connection")
async def send_expert_connection(
    expert_id: str,
    request: LinkedInSendRequest,
    db: Session = Depends(get_db),
):
    """Send a LinkedIn connection request to a specific expert."""
    outreach = (
        db.query(LinkedInOutreach)
        .filter(LinkedInOutreach.expert_profile_id == expert_id)
        .first()
    )
    if not outreach:
        raise HTTPException(status_code=404, detail="No outreach record found. Generate outreach first.")

    if outreach.status != LinkedInOutreachStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Outreach already in status: {outreach.status.value}")

    result = await send_linkedin_connection(
        linkedin_url=outreach.linkedin_url,
        connection_note=outreach.connection_note,
        session_cookie=request.session_cookie,
    )

    if result["success"]:
        outreach.status = LinkedInOutreachStatus.CONNECTION_SENT
        outreach.sent_at = datetime.utcnow()

        # Log activity
        activity = ExpertActivity(
            id=uuid.uuid4(),
            expert_profile_id=uuid.UUID(expert_id),
            activity_type=ExpertActivityType.LINKEDIN_SENT,
            description="LinkedIn connection request sent",
            created_at=datetime.utcnow(),
        )
        db.add(activity)
    else:
        outreach.status = LinkedInOutreachStatus.FAILED
        outreach.error_message = result.get("error", "Unknown error")

    db.commit()

    return {
        "expert_id": expert_id,
        "success": result["success"],
        "status": outreach.status.value,
        "error": result.get("error"),
    }


# ─── BULK SEND ────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/send-batch")
async def send_batch_connections(
    project_id: str,
    limit: int = 10,
    request: LinkedInSendRequest = LinkedInSendRequest(),
    db: Session = Depends(get_db),
):
    """Send LinkedIn connection requests to a batch of pending experts."""
    pending = (
        db.query(LinkedInOutreach)
        .join(ExpertProfile)
        .filter(
            ExpertProfile.project_id == project_id,
            LinkedInOutreach.status == LinkedInOutreachStatus.PENDING,
        )
        .limit(limit)
        .all()
    )

    sent = 0
    failed = 0
    import asyncio
    import random

    for outreach in pending:
        result = await send_linkedin_connection(
            linkedin_url=outreach.linkedin_url,
            connection_note=outreach.connection_note,
            session_cookie=request.session_cookie,
        )

        if result["success"]:
            outreach.status = LinkedInOutreachStatus.CONNECTION_SENT
            outreach.sent_at = datetime.utcnow()
            sent += 1

            activity = ExpertActivity(
                id=uuid.uuid4(),
                expert_profile_id=outreach.expert_profile_id,
                activity_type=ExpertActivityType.LINKEDIN_SENT,
                description="LinkedIn connection request sent",
                created_at=datetime.utcnow(),
            )
            db.add(activity)
        else:
            outreach.status = LinkedInOutreachStatus.FAILED
            outreach.error_message = result.get("error")
            failed += 1

        # Random delay between sends
        delay = random.randint(120, 300)
        await asyncio.sleep(delay)

    db.commit()

    return {
        "project_id": project_id,
        "sent": sent,
        "failed": failed,
        "remaining_pending": len(pending) - sent - failed,
    }
