from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db
from app.deps import verify_api_key
from app.workers.jobs import send_job
from app.workers.queue import default_queue

router = APIRouter(
    prefix="/drafts",
    tags=["drafts"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/", response_model=List[schemas.MessageDraftResponse])
def list_drafts(
    project_id: Optional[UUID] = None,
    candidate_id: Optional[UUID] = None,
    approved: Optional[bool] = None,
    has_risk_flags: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    List drafts with optional filters.

    Filters:
    - project_id: Filter by project
    - candidate_id: Filter by candidate
    - approved: True for approved, False for pending
    - has_risk_flags: True for drafts needing review
    """
    query = db.query(models.MessageDraft)

    if project_id:
        query = query.filter(models.MessageDraft.project_id == project_id)
    if candidate_id:
        query = query.filter(models.MessageDraft.candidate_id == candidate_id)
    if approved is not None:
        if approved:
            query = query.filter(models.MessageDraft.approved_at != None)
        else:
            query = query.filter(models.MessageDraft.approved_at == None)
    if has_risk_flags is not None:
        from sqlalchemy import cast, String
        if has_risk_flags:
            query = query.filter(cast(models.MessageDraft.risk_flags, String) != '[]')
        else:
            query = query.filter(cast(models.MessageDraft.risk_flags, String) == '[]')

    drafts = query.offset(skip).limit(limit).all()
    return drafts


@router.get("/{draft_id}", response_model=schemas.MessageDraftResponse)
def get_draft(
    draft_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a specific draft with full details."""
    draft = crud.get_draft(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/{draft_id}/approve", response_model=schemas.MessageDraftResponse)
def approve_draft(
    draft_id: UUID,
    approval: schemas.DraftApproval,
    db: Session = Depends(get_db),
):
    """Approve a message draft"""
    draft = crud.approve_draft(db, draft_id, approval.approved_by)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/{draft_id}/reject")
def reject_draft(
    draft_id: UUID,
    rejection: schemas.DraftRejection,
    db: Session = Depends(get_db),
):
    """Reject a message draft - removes it from the queue."""
    draft = crud.get_draft(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Delete the draft
    db.delete(draft)
    db.commit()

    # Log the rejection
    crud.create_audit_log(
        db,
        rejection.rejected_by,
        "reject_draft",
        "draft",
        str(draft_id),
        {"reason": rejection.reason} if rejection.reason else {},
    )

    return {"status": "rejected", "draft_id": str(draft_id)}


@router.post("/{draft_id}/send", response_model=schemas.JobEnqueuedResponse)
def send_draft(
    draft_id: UUID,
    payload: schemas.DraftSend,
    db: Session = Depends(get_db),
):
    """Enqueue send job for approved draft"""
    draft = crud.get_draft(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if not draft.approved_at:
        raise HTTPException(status_code=400, detail="Draft must be approved before sending")

    # Check if candidate is on do-not-contact
    candidate = crud.get_candidate(db, draft.candidate_id)
    if candidate and candidate.email:
        if crud.is_do_not_contact(db, candidate.email):
            raise HTTPException(
                status_code=400,
                detail="Candidate is on do-not-contact list",
            )

    job = default_queue.enqueue(send_job, str(draft_id), payload.actor)

    return schemas.JobEnqueuedResponse(
        job_id=job.id,
        message=f"Send job enqueued for draft {draft_id}",
    )
