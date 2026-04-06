"""
Expert Profiles Router — GLG-style expert profile management.
Handles document upload, profile generation, screener responses, and activity tracking.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import verify_api_key
from app.models import (
    Candidate,
    ExpertActivity,
    ExpertActivityType,
    ExpertProfile,
    ExpertProfileStatus,
    LinkedInOutreach,
    LinkedInOutreachStatus,
    ProjectBrief,
    ProjectCategory,
    ScreenerQuestion,
    ScreenerQuestionType,
)
from app.services.exa_research import research_expert
from app.services.expert_profiler import generate_expert_profile
from app.services.requirements_parser import parse_requirements_document

router = APIRouter(
    prefix="/expert-network",
    tags=["expert-network"],
    dependencies=[Depends(verify_api_key)],
)


# ─── PROJECT FROM DOCUMENT ────────────────────────────────────────────────────


@router.post("/projects/from-document")
async def create_project_from_document(
    document: UploadFile = File(None),
    document_text: str = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a requirements document (text/markdown/PDF) to create a project with categories and screener questions."""
    if document:
        content = await document.read()
        text = content.decode("utf-8", errors="replace")
    elif document_text:
        text = document_text
    else:
        raise HTTPException(status_code=400, detail="Provide either a document file or document_text")

    # Parse with Claude
    parsed = await parse_requirements_document(text)

    # Create project
    project = ProjectBrief(
        id=uuid.uuid4(),
        name=parsed["title"],
        industry=parsed.get("industry"),
        keywords=parsed.get("keywords", []),
        titles_include=[],
        titles_exclude=[],
        regions=[],
        exclusions=[],
        created_at=datetime.utcnow(),
    )
    db.add(project)
    db.flush()

    # Create categories
    categories = []
    for i, cat_data in enumerate(parsed.get("categories", [])):
        cat = ProjectCategory(
            id=uuid.uuid4(),
            project_id=project.id,
            name=cat_data["name"],
            description=cat_data.get("description", ""),
            search_criteria=cat_data.get("search_criteria", {}),
            sort_order=i,
            created_at=datetime.utcnow(),
        )
        db.add(cat)
        categories.append(cat)

    # Create screener questions
    screener_qs = []
    for i, q_data in enumerate(parsed.get("screener_questions", [])):
        q = ScreenerQuestion(
            id=uuid.uuid4(),
            project_id=project.id,
            question_text=q_data["question_text"],
            question_type=ScreenerQuestionType(q_data.get("question_type", "multiple_choice")),
            options=q_data.get("options", []),
            sort_order=i,
            created_at=datetime.utcnow(),
        )
        db.add(q)
        screener_qs.append(q)

    db.commit()

    return {
        "project_id": str(project.id),
        "name": project.name,
        "industry": project.industry,
        "categories": [{"id": str(c.id), "name": c.name, "description": c.description} for c in categories],
        "screener_questions": [{"id": str(q.id), "question": q.question_text, "type": q.question_type.value} for q in screener_qs],
        "ideal_profile": parsed.get("ideal_profile", ""),
    }


# ─── CATEGORIES ───────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/categories")
def get_project_categories(project_id: str, db: Session = Depends(get_db)):
    """List expert categories for a project."""
    cats = (
        db.query(ProjectCategory)
        .filter(ProjectCategory.project_id == project_id)
        .order_by(ProjectCategory.sort_order)
        .all()
    )
    result = []
    for c in cats:
        expert_count = db.query(ExpertProfile).filter(ExpertProfile.category_id == c.id).count()
        result.append({
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "search_criteria": c.search_criteria,
            "expert_count": expert_count,
            "sort_order": c.sort_order,
        })
    return result


# ─── EXPERTS ──────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/experts")
def get_project_experts(
    project_id: str,
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all experts for a project, optionally filtered by category or status."""
    query = (
        db.query(ExpertProfile)
        .options(joinedload(ExpertProfile.candidate), joinedload(ExpertProfile.category))
        .filter(ExpertProfile.project_id == project_id)
    )

    if category_id:
        query = query.filter(ExpertProfile.category_id == category_id)
    if status:
        query = query.filter(ExpertProfile.status == status)

    profiles = query.order_by(ExpertProfile.relevance_score.desc().nullslast()).all()

    return {
        "project_id": project_id,
        "total": len(profiles),
        "experts": [_serialize_expert_card(p) for p in profiles],
    }


@router.get("/experts/{expert_id}/profile")
def get_expert_profile(expert_id: str, db: Session = Depends(get_db)):
    """Get full expert profile with all details."""
    profile = (
        db.query(ExpertProfile)
        .options(
            joinedload(ExpertProfile.candidate),
            joinedload(ExpertProfile.category),
            joinedload(ExpertProfile.activities),
            joinedload(ExpertProfile.linkedin_outreach),
        )
        .filter(ExpertProfile.id == expert_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    candidate = profile.candidate
    return {
        "id": str(profile.id),
        "candidate_id": str(candidate.id),
        "full_name": candidate.full_name,
        "title": candidate.title,
        "company": candidate.company,
        "region": candidate.region,
        "linkedin_url": candidate.linkedin_url,
        "headline": candidate.headline,
        "photo_url": candidate.photo_url,
        "email": candidate.email,
        "rate_per_hour": float(profile.rate_per_hour) if profile.rate_per_hour else None,
        "relevance_score": profile.relevance_score,
        "status": profile.status.value if profile.status else "sourced",
        "category": {"id": str(profile.category.id), "name": profile.category.name} if profile.category else None,
        "ai_overview": profile.ai_overview,
        "project_expertise": profile.project_expertise or [],
        "work_experience": profile.work_experience or [],
        "screener_responses": profile.screener_responses or {},
        "exa_research": profile.exa_research or {},
        "activities": [
            {
                "id": str(a.id),
                "type": a.activity_type.value,
                "description": a.description,
                "created_at": a.created_at.isoformat(),
            }
            for a in (profile.activities or [])
        ],
        "linkedin_outreach": {
            "status": profile.linkedin_outreach.status.value,
            "connection_note": profile.linkedin_outreach.connection_note,
            "sent_at": profile.linkedin_outreach.sent_at.isoformat() if profile.linkedin_outreach.sent_at else None,
        } if profile.linkedin_outreach else None,
        "created_at": profile.created_at.isoformat(),
    }


# ─── SCREENER QUESTIONS ──────────────────────────────────────────────────────


@router.get("/projects/{project_id}/screener-questions")
def get_screener_questions(project_id: str, db: Session = Depends(get_db)):
    """List screener questions for a project."""
    questions = (
        db.query(ScreenerQuestion)
        .filter(ScreenerQuestion.project_id == project_id)
        .order_by(ScreenerQuestion.sort_order)
        .all()
    )
    return [
        {
            "id": str(q.id),
            "question_text": q.question_text,
            "question_type": q.question_type.value,
            "options": q.options or [],
            "sort_order": q.sort_order,
        }
        for q in questions
    ]


@router.post("/experts/{expert_id}/screener-responses")
def update_screener_responses(expert_id: str, responses: dict, db: Session = Depends(get_db)):
    """Update screener responses for an expert."""
    profile = db.query(ExpertProfile).filter(ExpertProfile.id == expert_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    existing = profile.screener_responses or {}
    existing.update(responses)
    profile.screener_responses = existing
    profile.status = ExpertProfileStatus.SCREENED
    db.commit()

    return {"expert_id": expert_id, "screener_responses": profile.screener_responses}


# ─── PROFILE GENERATION ──────────────────────────────────────────────────────


@router.post("/projects/{project_id}/generate-profiles")
async def generate_profiles_for_project(
    project_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Generate AI profiles for all sourced experts in a project that don't have one yet."""
    project = db.query(ProjectBrief).filter(ProjectBrief.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get categories and screener questions
    categories = db.query(ProjectCategory).filter(ProjectCategory.project_id == project_id).all()
    screener_qs = db.query(ScreenerQuestion).filter(ScreenerQuestion.project_id == project_id).all()

    # Find experts that need profiling (have profile but no ai_overview)
    profiles = (
        db.query(ExpertProfile)
        .options(joinedload(ExpertProfile.candidate))
        .filter(
            ExpertProfile.project_id == project_id,
            ExpertProfile.ai_overview.is_(None),
        )
        .limit(limit)
        .all()
    )

    generated = 0
    errors = 0

    for profile in profiles:
        candidate = profile.candidate
        try:
            # Run Exa research
            exa_data = await research_expert(
                name=candidate.full_name,
                company=candidate.company or "",
                title=candidate.title or "",
                linkedin_url=candidate.linkedin_url,
            )
            profile.exa_research = exa_data

            # Generate AI profile
            candidate_data = {
                "full_name": candidate.full_name,
                "title": candidate.title,
                "company": candidate.company,
                "region": candidate.region,
                "linkedin_url": candidate.linkedin_url,
                "headline": candidate.headline,
                "company_employee_count": candidate.company_employee_count,
                "source_payload": None,
            }

            # Get source payload if available
            if candidate.sources:
                candidate_data["source_payload"] = candidate.sources[0].source_payload

            project_data = {
                "name": project.name,
                "industry": project.industry,
                "description": "",
                "ideal_profile": "",
                "titles_include": project.titles_include or [],
                "keywords": project.keywords or [],
            }

            cat_data = [{"name": c.name, "description": c.description} for c in categories]
            q_data = [{"id": str(q.id), "question_text": q.question_text, "question_type": q.question_type.value, "options": q.options} for q in screener_qs]

            ai_profile = await generate_expert_profile(candidate_data, project_data, exa_data, q_data, cat_data)

            # Update profile
            profile.ai_overview = ai_profile.get("ai_overview")
            profile.project_expertise = ai_profile.get("project_expertise", [])
            profile.relevance_score = ai_profile.get("relevance_score")
            profile.screener_responses = ai_profile.get("screener_responses", {})
            profile.work_experience = ai_profile.get("work_experience", [])
            if ai_profile.get("estimated_rate"):
                profile.rate_per_hour = ai_profile["estimated_rate"]

            # Assign category based on AI suggestion
            suggested_cat = ai_profile.get("suggested_category")
            if suggested_cat and categories:
                for cat in categories:
                    if cat.name.lower() in suggested_cat.lower() or suggested_cat.lower() in cat.name.lower():
                        profile.category_id = cat.id
                        break

            profile.status = ExpertProfileStatus.SCREENED

            # Log activity
            activity = ExpertActivity(
                id=uuid.uuid4(),
                expert_profile_id=profile.id,
                activity_type=ExpertActivityType.ADDED,
                description=f"AI profile generated. Relevance score: {profile.relevance_score}",
                created_at=datetime.utcnow(),
            )
            db.add(activity)

            generated += 1
        except Exception as e:
            errors += 1
            import traceback
            traceback.print_exc()

    db.commit()

    return {
        "project_id": project_id,
        "generated": generated,
        "errors": errors,
        "total_profiled": generated,
    }


# ─── ACTIVITY & STATUS ───────────────────────────────────────────────────────


@router.post("/experts/{expert_id}/schedule-call")
def schedule_call(expert_id: str, db: Session = Depends(get_db)):
    """Log a call request for an expert."""
    profile = db.query(ExpertProfile).filter(ExpertProfile.id == expert_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    activity = ExpertActivity(
        id=uuid.uuid4(),
        expert_profile_id=profile.id,
        activity_type=ExpertActivityType.CALL_REQUESTED,
        description="Call requested",
        created_at=datetime.utcnow(),
    )
    db.add(activity)
    profile.status = ExpertProfileStatus.SCHEDULED
    db.commit()

    return {"expert_id": expert_id, "status": "call_requested"}


@router.patch("/experts/{expert_id}/status")
def update_expert_status(expert_id: str, status: str, db: Session = Depends(get_db)):
    """Update expert profile status."""
    profile = db.query(ExpertProfile).filter(ExpertProfile.id == expert_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    profile.status = ExpertProfileStatus(status)
    db.commit()
    return {"expert_id": expert_id, "status": status}


# ─── HELPERS ──────────────────────────────────────────────────────────────────


def _serialize_expert_card(profile: ExpertProfile) -> dict:
    """Serialize an expert profile for the card view."""
    candidate = profile.candidate
    return {
        "id": str(profile.id),
        "candidate_id": str(candidate.id),
        "full_name": candidate.full_name,
        "title": candidate.title,
        "company": candidate.company,
        "region": candidate.region,
        "linkedin_url": candidate.linkedin_url,
        "headline": candidate.headline,
        "photo_url": candidate.photo_url,
        "email": candidate.email,
        "rate_per_hour": float(profile.rate_per_hour) if profile.rate_per_hour else None,
        "relevance_score": profile.relevance_score,
        "status": profile.status.value if profile.status else "sourced",
        "category": {"id": str(profile.category.id), "name": profile.category.name} if profile.category else None,
        "ai_overview_snippet": (profile.ai_overview[:200] + "...") if profile.ai_overview and len(profile.ai_overview) > 200 else profile.ai_overview,
        "project_expertise": profile.project_expertise or [],
        "activity_count": len(profile.activities) if profile.activities else 0,
    }
