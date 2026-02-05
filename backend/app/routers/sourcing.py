"""
Candidate Sourcing Router

Provides API endpoints for sourcing candidates from external providers
like Apollo.io. Supports searching and auto-importing candidates into projects.
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.deps import verify_api_key
from app.services.apollo import (
    ApolloAPIError,
    ApolloRateLimitError,
    get_apollo_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sourcing",
    tags=["sourcing"],
    dependencies=[Depends(verify_api_key)],
)


# Request/Response schemas
class SourcingSearchCriteria(BaseModel):
    """Search criteria for sourcing candidates."""

    titles: List[str] = Field(
        default_factory=list,
        description="Job titles to search for (e.g., 'VP of Benefits', 'Director of HR')"
    )
    company_sizes: List[str] = Field(
        default_factory=list,
        description="Company size ranges (e.g., '1001-5000', '5001-10000', '10001+')"
    )
    industries: List[str] = Field(
        default_factory=list,
        description="Industries to target"
    )
    locations: List[str] = Field(
        default_factory=list,
        description="Locations to search (e.g., 'United States', 'California')"
    )
    seniorities: List[str] = Field(
        default_factory=list,
        description="Seniority levels (e.g., 'director', 'vp', 'c_suite', 'manager')"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Additional keywords for broader matching"
    )
    company_names: List[str] = Field(
        default_factory=list,
        description="Specific company names to target"
    )
    exclude_companies: List[str] = Field(
        default_factory=list,
        description="Company names to exclude"
    )
    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=25, ge=1, le=100, description="Results per page")


class SourcingSearchResponse(BaseModel):
    """Response from a sourcing search."""

    results: List[Dict[str, Any]]
    total_returned: int
    page: int
    per_page: int
    source: str = "apollo"
    stub_mode: bool = False


class SourcingImportRequest(BaseModel):
    """Request to import candidates from sourcing search."""

    criteria: SourcingSearchCriteria
    max_results: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of candidates to import"
    )
    require_email: bool = Field(
        default=True,
        description="Only import candidates with email addresses"
    )


class SourcingImportResponse(BaseModel):
    """Response from importing sourced candidates."""

    project_id: UUID
    candidates_found: int
    candidates_imported: int
    candidates_skipped_no_email: int
    candidates_skipped_duplicate: int
    candidates: List[schemas.CandidateResponse]


class EnrichPersonRequest(BaseModel):
    """Request to enrich a person by LinkedIn URL."""

    linkedin_url: str = Field(description="LinkedIn profile URL to enrich")


class FindEmailRequest(BaseModel):
    """Request to find email for a person."""

    person_id: str = Field(description="Apollo person ID")


@router.post("/search", response_model=SourcingSearchResponse)
def search_candidates(
    criteria: SourcingSearchCriteria,
) -> SourcingSearchResponse:
    """
    Search Apollo.io for candidates matching the specified criteria.

    This endpoint searches Apollo's people database and returns matches
    mapped to our Candidate model format. Use this to preview results
    before importing.

    Returns candidates with the following mapped fields:
    - first_name, last_name, full_name
    - title, company, company_employee_count
    - linkedin_url, email, email_verified
    - region (city, state, country combined)
    - apollo_data (additional Apollo-specific fields)
    """
    apollo = get_apollo_service()

    try:
        results = apollo.search_people(
            criteria=criteria.model_dump(
                exclude={"page", "per_page"}
            ),
            page=criteria.page,
            per_page=criteria.per_page,
        )

        return SourcingSearchResponse(
            results=results,
            total_returned=len(results),
            page=criteria.page,
            per_page=criteria.per_page,
            source="apollo",
            stub_mode=apollo.stub_mode,
        )

    except ApolloRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": e.retry_after,
                "message": str(e),
            }
        )

    except ApolloAPIError as e:
        raise HTTPException(
            status_code=e.status_code if 400 <= e.status_code < 600 else 500,
            detail={
                "error": "Apollo API error",
                "message": e.message,
            }
        )


@router.post("/import/{project_id}", response_model=SourcingImportResponse)
def import_candidates_for_project(
    project_id: UUID,
    request: SourcingImportRequest,
    db: Session = Depends(get_db),
) -> SourcingImportResponse:
    """
    Search Apollo and auto-import matching candidates for a project.

    This endpoint:
    1. Searches Apollo with the provided criteria
    2. Filters results based on requirements (e.g., require_email)
    3. Creates Candidate records with Apollo as the source
    4. Skips duplicates (by email)
    5. Returns import statistics and created candidates

    The imported candidates are ready for scoring and drafting.
    """
    # Verify project exists
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    apollo = get_apollo_service()

    try:
        # Search with pagination to get max_results
        all_results = apollo.search_people_paginated(
            criteria=request.criteria.model_dump(
                exclude={"page", "per_page"}
            ),
            max_results=request.max_results,
            per_page=request.criteria.per_page,
        )

    except ApolloRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": e.retry_after,
                "message": str(e),
            }
        )

    except ApolloAPIError as e:
        raise HTTPException(
            status_code=e.status_code if 400 <= e.status_code < 600 else 500,
            detail={
                "error": "Apollo API error",
                "message": e.message,
            }
        )

    # Process results
    candidates_found = len(all_results)
    candidates_skipped_no_email = 0
    candidates_skipped_duplicate = 0
    imported_candidates: List[schemas.CandidateCreate] = []

    for result in all_results:
        # Check email requirement
        if request.require_email and not result.get("email"):
            candidates_skipped_no_email += 1
            continue

        # Build candidate create schema
        candidate_data = schemas.CandidateCreate(
            first_name=result.get("first_name"),
            last_name=result.get("last_name"),
            full_name=result.get("full_name", "Unknown"),
            title=result.get("title"),
            company=result.get("company"),
            company_employee_count=result.get("company_employee_count"),
            region=result.get("region"),
            linkedin_url=result.get("linkedin_url"),
            email=result.get("email"),
            source_name="apollo",
            source_url=f"https://app.apollo.io/#/people/{result.get('apollo_id')}"
            if result.get("apollo_id")
            else None,
            source_payload={
                "apollo_id": result.get("apollo_id"),
                "apollo_data": result.get("apollo_data"),
                "project_id": str(project_id),
            },
        )
        imported_candidates.append(candidate_data)

    # Bulk create candidates (handles duplicates)
    created_candidates = crud.bulk_create_candidates(db, imported_candidates)
    candidates_skipped_duplicate = len(imported_candidates) - len(created_candidates)

    logger.info(
        f"Imported {len(created_candidates)} candidates for project {project_id}. "
        f"Found: {candidates_found}, Skipped (no email): {candidates_skipped_no_email}, "
        f"Skipped (duplicate): {candidates_skipped_duplicate}"
    )

    return SourcingImportResponse(
        project_id=project_id,
        candidates_found=candidates_found,
        candidates_imported=len(created_candidates),
        candidates_skipped_no_email=candidates_skipped_no_email,
        candidates_skipped_duplicate=candidates_skipped_duplicate,
        candidates=[
            schemas.CandidateResponse.model_validate(c)
            for c in created_candidates
        ],
    )


@router.post("/enrich-project/{project_id}")
def enrich_project_candidates(
    project_id: UUID,
    limit: int = 25,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Enrich all candidates for a project to get full names and emails.

    This uses Apollo's people/match API with the Apollo IDs from import.
    Each enrichment costs Apollo API credits.

    Args:
        project_id: The project to enrich candidates for
        limit: Maximum number of candidates to enrich (to control costs)
    """
    from app import models

    # Get candidates sourced for this project that need enrichment
    candidates = (
        db.query(models.Candidate)
        .join(models.CandidateSource)
        .filter(
            models.CandidateSource.source_payload['project_id'].astext == str(project_id)
        )
        .limit(limit)
        .all()
    )

    apollo = get_apollo_service()
    enriched_count = 0
    failed_count = 0
    results = []

    for candidate in candidates:
        # Get Apollo ID from source
        source = (
            db.query(models.CandidateSource)
            .filter(models.CandidateSource.candidate_id == candidate.id)
            .first()
        )

        if not source or not source.source_payload:
            continue

        apollo_id = source.source_payload.get("apollo_id")
        if not apollo_id:
            continue

        try:
            # Enrich using Apollo ID
            enriched = apollo.enrich_by_id(apollo_id)

            # Update candidate with enriched data
            if enriched.get("first_name"):
                candidate.first_name = enriched["first_name"]
            if enriched.get("last_name"):
                candidate.last_name = enriched["last_name"]
            if enriched.get("first_name") and enriched.get("last_name"):
                candidate.full_name = f"{enriched['first_name']} {enriched['last_name']}"
            if enriched.get("email"):
                candidate.email = enriched["email"]
                candidate.email_verified = enriched.get("email_verified", False)
            if enriched.get("linkedin_url"):
                candidate.linkedin_url = enriched["linkedin_url"]
            if enriched.get("region"):
                candidate.region = enriched["region"]
            if enriched.get("company_employee_count"):
                candidate.company_employee_count = enriched["company_employee_count"]

            # Update status
            candidate.status = models.CandidateStatus.ENRICHED

            db.commit()
            enriched_count += 1

            results.append({
                "candidate_id": str(candidate.id),
                "full_name": candidate.full_name,
                "email": candidate.email,
                "status": "enriched"
            })

            # Small delay between requests
            import time
            time.sleep(0.5)

        except ApolloRateLimitError as e:
            # Stop if rate limited
            results.append({
                "candidate_id": str(candidate.id),
                "error": f"Rate limited, retry after {e.retry_after}s"
            })
            break

        except ApolloAPIError as e:
            failed_count += 1
            results.append({
                "candidate_id": str(candidate.id),
                "error": str(e)
            })

    return {
        "project_id": str(project_id),
        "candidates_processed": len(results),
        "enriched": enriched_count,
        "failed": failed_count,
        "results": results,
    }


@router.post("/enrich", response_model=Dict[str, Any])
def enrich_person(
    request: EnrichPersonRequest,
) -> Dict[str, Any]:
    """
    Enrich a person's profile from their LinkedIn URL.

    Returns full profile data including email if available.
    Useful for getting detailed information about a specific person
    before importing them.
    """
    apollo = get_apollo_service()

    try:
        result = apollo.enrich_person(request.linkedin_url)
        return {
            "success": True,
            "data": result,
            "stub_mode": apollo.stub_mode,
        }

    except ApolloRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": e.retry_after,
                "message": str(e),
            }
        )

    except ApolloAPIError as e:
        raise HTTPException(
            status_code=e.status_code if 400 <= e.status_code < 600 else 500,
            detail={
                "error": "Apollo API error",
                "message": e.message,
            }
        )


@router.post("/find-email", response_model=Dict[str, Any])
def find_email(
    request: FindEmailRequest,
) -> Dict[str, Any]:
    """
    Find verified email for a person by their Apollo ID.

    Use this to get/refresh email information for a person
    you've already found through search.
    """
    apollo = get_apollo_service()

    try:
        result = apollo.find_email(request.person_id)
        return {
            "success": True,
            "data": result,
            "stub_mode": apollo.stub_mode,
        }

    except ApolloRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": e.retry_after,
                "message": str(e),
            }
        )

    except ApolloAPIError as e:
        raise HTTPException(
            status_code=e.status_code if 400 <= e.status_code < 600 else 500,
            detail={
                "error": "Apollo API error",
                "message": e.message,
            }
        )


@router.post("/import/{project_id}/from-brief", response_model=SourcingImportResponse)
def import_candidates_from_project_brief(
    project_id: UUID,
    max_results: int = 50,
    require_email: bool = True,
    db: Session = Depends(get_db),
) -> SourcingImportResponse:
    """
    Auto-import candidates based on the project brief's criteria.

    This endpoint:
    1. Reads the project brief's search criteria (titles, industry, company size, etc.)
    2. Converts them to Apollo search parameters
    3. Searches and imports matching candidates

    This is a convenience endpoint that automatically builds search criteria
    from the project definition.
    """
    # Verify project exists
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build search criteria from project brief
    criteria = SourcingSearchCriteria(
        titles=project.titles_include or [],
        industries=[project.industry] if project.industry else [],
        keywords=project.keywords or [],
        locations=project.regions or [],
        exclude_companies=project.exclusions or [],
    )

    # Map company_size_min to Apollo's size ranges
    if project.company_size_min:
        size_min = project.company_size_min
        if size_min >= 10000:
            criteria.company_sizes = ["10001+"]
        elif size_min >= 5000:
            criteria.company_sizes = ["5001-10000", "10001+"]
        elif size_min >= 1000:
            criteria.company_sizes = ["1001-5000", "5001-10000", "10001+"]
        elif size_min >= 500:
            criteria.company_sizes = ["501-1000", "1001-5000", "5001-10000", "10001+"]
        elif size_min >= 200:
            criteria.company_sizes = ["201-500", "501-1000", "1001-5000", "5001-10000", "10001+"]

    # Build import request
    import_request = SourcingImportRequest(
        criteria=criteria,
        max_results=max_results,
        require_email=require_email,
    )

    # Delegate to main import endpoint logic
    return import_candidates_for_project(project_id, import_request, db)
