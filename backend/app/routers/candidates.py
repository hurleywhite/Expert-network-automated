from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.deps import verify_api_key
from app.workers.jobs import enrichment_job
from app.workers.queue import default_queue

router = APIRouter(
    prefix="/candidates",
    tags=["candidates"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/bulk", response_model=List[schemas.CandidateResponse], status_code=201)
def bulk_create_candidates(
    payload: schemas.CandidateBulkCreate,
    db: Session = Depends(get_db),
):
    """Bulk create candidates"""
    return crud.bulk_create_candidates(db, payload.candidates)


@router.get("/", response_model=List[schemas.CandidateResponse])
def list_candidates(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    region: Optional[str] = None,
    project_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """List candidates with optional filters"""
    return crud.get_candidates(
        db,
        skip=skip,
        limit=limit,
        status=status,
        company=company,
        title=title,
        region=region,
        project_id=project_id,
    )


@router.get("/{candidate_id}", response_model=schemas.CandidateResponse)
def get_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a specific candidate"""
    candidate = crud.get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.post("/{candidate_id}/enrich", response_model=schemas.JobEnqueuedResponse)
def enrich_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
):
    """Enqueue enrichment job for candidate"""
    candidate = crud.get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job = default_queue.enqueue(enrichment_job, str(candidate_id))

    return schemas.JobEnqueuedResponse(
        job_id=job.id,
        message=f"Enrichment job enqueued for candidate {candidate_id}",
    )
