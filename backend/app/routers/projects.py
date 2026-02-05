from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db
from app.deps import verify_api_key
from app.workers.jobs import scoring_job, drafting_job, send_job
from app.workers.queue import default_queue
from app.services.pipeline import Pipeline

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(verify_api_key)],
)


# Additional request schemas
class NaturalLanguageProjectCreate(BaseModel):
    """Create project from natural language description."""
    description: str
    created_by: str


class BulkApproveRequest(BaseModel):
    """Request to bulk approve drafts."""
    approved_by: str


class BulkSendRequest(BaseModel):
    """Request to send approved drafts."""
    actor: str
    limit: Optional[int] = None


class OutreachContext(BaseModel):
    """Context for personalizing outreach emails."""
    research_topic: str = "industry trends and best practices"
    rate_range: str = "$150-300"
    sender_name: str = "[Your Name]"
    sender_title: Optional[str] = ""


class DraftWithContextRequest(BaseModel):
    """Request to generate drafts with outreach context."""
    outreach_context: OutreachContext
    min_score: Optional[float] = 40
    limit: Optional[int] = None


@router.post("/", response_model=schemas.ProjectBriefResponse, status_code=201)
def create_project(
    project: schemas.ProjectBriefCreate,
    db: Session = Depends(get_db),
):
    """Create a new project brief"""
    return crud.create_project(db, project)


@router.post("/from-description", status_code=201)
def create_project_from_description(
    payload: NaturalLanguageProjectCreate,
    db: Session = Depends(get_db),
):
    """
    Create a project from natural language description.

    Example:
        "Find 401(k) benefits administrators at companies with 10,000+ employees"

    The system will:
    1. Parse the description to extract search criteria
    2. Create a structured project brief
    3. Return the project with interpretation details
    """
    result = Pipeline.create_project_from_description(
        db, payload.description, payload.created_by
    )
    return {
        "project": schemas.ProjectBriefResponse.model_validate(result["project"]),
        "interpretation": result["interpretation"],
        "parsed_criteria": result["parsed_criteria"],
    }


@router.get("/", response_model=List[schemas.ProjectBriefResponse])
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all project briefs"""
    return crud.get_projects(db, skip=skip, limit=limit)


@router.get("/{project_id}", response_model=schemas.ProjectBriefResponse)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a specific project brief"""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/{project_id}/candidates/{candidate_id}/score",
    response_model=schemas.JobEnqueuedResponse,
)
def score_candidate(
    project_id: UUID,
    candidate_id: UUID,
    db: Session = Depends(get_db),
):
    """Enqueue scoring job for candidate against project"""
    candidate = crud.get_candidate(db, candidate_id)
    project = crud.get_project(db, project_id)

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    job = default_queue.enqueue(scoring_job, str(project_id), str(candidate_id))

    return schemas.JobEnqueuedResponse(
        job_id=job.id,
        message=f"Scoring job enqueued for candidate {candidate_id}",
    )


@router.post(
    "/{project_id}/candidates/{candidate_id}/draft",
    response_model=schemas.JobEnqueuedResponse,
)
def draft_message(
    project_id: UUID,
    candidate_id: UUID,
    db: Session = Depends(get_db),
):
    """Enqueue message drafting job"""
    candidate = crud.get_candidate(db, candidate_id)
    project = crud.get_project(db, project_id)

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    job = default_queue.enqueue(drafting_job, str(project_id), str(candidate_id))

    return schemas.JobEnqueuedResponse(
        job_id=job.id,
        message=f"Drafting job enqueued for candidate {candidate_id}",
    )


# ============ BATCH PIPELINE ENDPOINTS ============

@router.post("/{project_id}/score-all")
def score_all_candidates(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Score ALL candidates against this project's criteria.

    Uses expert-network style scoring (like GLG/AlphaSights):
    - Title relevance
    - Seniority appropriateness
    - Domain expertise signals
    - Company fit

    Returns ranked list with recommendations.
    """
    result = Pipeline.score_all_candidates(db, project_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/{project_id}/draft-qualified")
def draft_for_qualified(
    project_id: UUID,
    min_score: Optional[float] = None,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Generate personalized drafts for all qualified candidates.

    Candidates must:
    - Have score >= min_score (default: 40)
    - Not be hard-passed
    - Have an email address
    - Not be on do-not-contact list
    - Not already have a draft for this project

    Drafts are created with anti-hallucination validation.
    """
    result = Pipeline.draft_for_qualified_candidates(
        db, project_id, min_score=min_score, limit=limit
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/{project_id}/draft-with-context")
def draft_with_context(
    project_id: UUID,
    request: DraftWithContextRequest,
    db: Session = Depends(get_db),
):
    """
    Generate personalized drafts with custom outreach context.

    This endpoint lets you specify:
    - research_topic: What you're researching (e.g., "digital comics distribution trends")
    - rate_range: Compensation offered (e.g., "$200-400")
    - sender_name: Your name
    - sender_title: Your title/company (optional)

    The LLM will use this context to personalize each email with:
    - Specific credential/signal from their profile
    - Tailored interview questions for their domain
    - Your custom rate and contact info
    """
    outreach_context = request.outreach_context.model_dump()
    result = Pipeline.draft_for_qualified_candidates(
        db,
        project_id,
        min_score=request.min_score,
        limit=request.limit,
        outreach_context=outreach_context,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/review-queue")
def get_review_queue(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get drafts pending human review.

    Returns two groups:
    - ready_to_approve: No risk flags, safe to bulk approve
    - needs_review: Has risk flags, requires human attention

    This is the HUMAN OVERSIGHT checkpoint before sending.
    """
    return Pipeline.get_review_queue(db, project_id)


@router.post("/{project_id}/bulk-approve")
def bulk_approve_safe_drafts(
    project_id: UUID,
    payload: BulkApproveRequest,
    db: Session = Depends(get_db),
):
    """
    Approve all drafts with NO risk flags.

    Drafts with risk flags must be approved individually after review.
    This maintains human oversight while allowing efficiency.
    """
    return Pipeline.bulk_approve_safe_drafts(db, project_id, payload.approved_by)


@router.post("/{project_id}/send-approved")
def send_approved_drafts(
    project_id: UUID,
    payload: BulkSendRequest,
    db: Session = Depends(get_db),
):
    """
    Enqueue send jobs for all approved drafts.

    Sends are:
    - Rate-limited per domain
    - Jittered to avoid detection
    - Idempotent (safe to retry)
    - Tracked for delivery status
    """
    # Get approved drafts not yet sent
    from app import models

    query = (
        db.query(models.MessageDraft)
        .filter(
            models.MessageDraft.project_id == project_id,
            models.MessageDraft.approved_at != None,
        )
    )

    # Exclude already sent
    sent_draft_ids = (
        db.query(models.OutboundEvent.message_draft_id)
        .filter(
            models.OutboundEvent.project_id == project_id,
            models.OutboundEvent.status == models.OutboundEventStatus.SENT,
        )
        .subquery()
    )

    drafts = query.filter(
        ~models.MessageDraft.id.in_(sent_draft_ids)
    ).all()

    if payload.limit:
        drafts = drafts[:payload.limit]

    jobs_enqueued = 0
    for draft in drafts:
        default_queue.enqueue(send_job, str(draft.id), payload.actor)
        jobs_enqueued += 1

    return {
        "project_id": str(project_id),
        "jobs_enqueued": jobs_enqueued,
        "actor": payload.actor,
    }


@router.get("/{project_id}/status")
def get_pipeline_status(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get overall pipeline status for a project.

    Shows progress through:
    - Scoring
    - Drafting
    - Review
    - Sending
    - Replies

    Includes suggested next action.
    """
    result = Pipeline.get_pipeline_status(db, project_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/approved-drafts")
def get_approved_drafts(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get all approved and sent drafts for a project.

    Returns drafts grouped by status:
    - approved: Approved but not yet sent
    - sent: Successfully sent
    """
    # Get approved drafts
    approved_drafts = (
        db.query(models.MessageDraft)
        .filter(
            models.MessageDraft.project_id == project_id,
            models.MessageDraft.approved_at != None,
        )
        .all()
    )

    # Get sent draft IDs
    sent_draft_ids = set(
        row[0] for row in db.query(models.OutboundEvent.message_draft_id)
        .filter(
            models.OutboundEvent.project_id == project_id,
            models.OutboundEvent.status == models.OutboundEventStatus.SENT,
        )
        .all()
    )

    approved_not_sent = []
    sent = []

    for draft in approved_drafts:
        candidate = crud.get_candidate(db, draft.candidate_id)
        draft_info = {
            "draft_id": str(draft.id),
            "candidate_id": str(draft.candidate_id),
            "candidate_name": candidate.full_name if candidate else "Unknown",
            "candidate_title": candidate.title if candidate else "",
            "candidate_company": candidate.company if candidate else "",
            "candidate_email": candidate.email if candidate else "",
            "subject": draft.subject,
            "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
            "approved_by": draft.approved_by,
        }

        if draft.id in sent_draft_ids:
            draft_info["status"] = "sent"
            sent.append(draft_info)
        else:
            draft_info["status"] = "approved"
            approved_not_sent.append(draft_info)

    return {
        "project_id": str(project_id),
        "approved": {
            "count": len(approved_not_sent),
            "drafts": approved_not_sent,
        },
        "sent": {
            "count": len(sent),
            "drafts": sent,
        },
    }


@router.get("/{project_id}/candidates")
def get_project_candidates(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get candidates sourced for this specific project.

    Returns candidates with their scores, sorted by score descending.
    Only shows candidates that were imported for this project.
    """
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get candidates that were sourced for this specific project
    # by checking source_payload.project_id
    project_candidates = (
        db.query(models.Candidate)
        .join(models.CandidateSource)
        .filter(
            models.CandidateSource.source_payload['project_id'].astext == str(project_id)
        )
        .all()
    )

    # Get latest scores for these candidates (ordered by id desc to get most recent)
    candidate_ids = [c.id for c in project_candidates]
    scores_map = {}
    if candidate_ids:
        # Get all scores and keep only the latest one per candidate
        scores = (
            db.query(models.Score)
            .filter(
                models.Score.project_id == project_id,
                models.Score.candidate_id.in_(candidate_ids)
            )
            .order_by(models.Score.id.desc())
            .all()
        )
        # First score per candidate_id is the latest (due to desc ordering)
        for s in scores:
            if s.candidate_id not in scores_map:
                scores_map[s.candidate_id] = s

    candidates = []
    for candidate in project_candidates:
        # Only include candidates with email addresses
        if not candidate.email:
            continue

        score_record = scores_map.get(candidate.id)

        # Skip candidates that are hard_passed (e.g., outside target region)
        if score_record and score_record.hard_pass:
            continue

        # Cap score at 100 for display
        score_value = score_record.score if score_record else None
        if score_value is not None:
            score_value = min(100, score_value)

        candidates.append({
            "candidate_id": str(candidate.id),
            "full_name": candidate.full_name,
            "title": candidate.title,
            "company": candidate.company,
            "email": candidate.email,
            "linkedin_url": candidate.linkedin_url,
            "region": candidate.region,
            "score": score_value,
            "hard_pass": score_record.hard_pass if score_record else False,
            "reasons": score_record.reasons if score_record else [],
        })

    # Sort by score descending (None scores at end)
    candidates.sort(key=lambda x: (x["score"] is not None, x["score"] or 0), reverse=True)

    return {
        "project_id": str(project_id),
        "total": len(candidates),
        "candidates": candidates,
    }
