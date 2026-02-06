import uuid
from typing import Dict, Any

from sqlalchemy.orm import Session

from app import crud, models
from app.database import SessionLocal
from app.services.email import EmailService
from app.services.llm import LLMService
from app.services.scoring import ScoringService
from app.services.validator import DraftValidator


def enrichment_job(candidate_id: str) -> Dict[str, Any]:
    """
    Background job to enrich candidate data.

    In production, this would call real enrichment APIs.
    For now, it's a mock that simulates email finding.
    """
    db = SessionLocal()
    try:
        candidate = crud.get_candidate(db, uuid.UUID(candidate_id))
        if not candidate:
            return {"error": "Candidate not found"}

        # Mock enrichment: generate email from name if not present
        if not candidate.email and candidate.full_name:
            # Simple mock: firstname.lastname@company.com
            name_parts = candidate.full_name.lower().split()
            if len(name_parts) >= 2 and candidate.company:
                company_domain = candidate.company.lower().replace(" ", "").replace(",", "")
                mock_email = f"{name_parts[0]}.{name_parts[-1]}@{company_domain}.com"
                candidate.email = mock_email
                candidate.email_verified = False

        # Create enrichment record
        db_enrichment = models.Enrichment(
            candidate_id=candidate.id,
            provider="mock_enrichment",
            payload={"email": candidate.email, "method": "generated"},
            confidence=0.6,
        )
        db.add(db_enrichment)

        # Update status
        candidate.status = models.CandidateStatus.ENRICHED
        db.commit()

        crud.create_audit_log(
            db, "system", "enrich", "candidate", str(candidate.id)
        )

        return {
            "candidate_id": str(candidate.id),
            "email": candidate.email,
            "status": "enriched",
        }

    finally:
        db.close()


def scoring_job(project_id: str, candidate_id: str) -> Dict[str, Any]:
    """Background job to score candidate against project"""
    db = SessionLocal()
    try:
        candidate = crud.get_candidate(db, uuid.UUID(candidate_id))
        project = crud.get_project(db, uuid.UUID(project_id))

        if not candidate or not project:
            return {"error": "Candidate or project not found"}

        # Build dicts for scoring
        candidate_dict = {
            "title": candidate.title,
            "company": candidate.company,
            "region": candidate.region,
            "company_employee_count": candidate.company_employee_count,
        }

        project_dict = {
            "titles_include": project.titles_include,
            "titles_exclude": project.titles_exclude,
            "regions": project.regions,
            "company_size_min": project.company_size_min,
            "keywords": project.keywords,
            "exclusions": project.exclusions,
        }

        # Score
        hard_pass, score, reasons = ScoringService.score_candidate(
            candidate_dict, project_dict
        )

        # Save score
        db_score = crud.create_score(
            db,
            candidate_id=uuid.UUID(candidate_id),
            project_id=uuid.UUID(project_id),
            hard_pass=hard_pass,
            score=score,
            reasons=reasons,
        )

        return {
            "candidate_id": str(candidate.id),
            "project_id": str(project.id),
            "hard_pass": hard_pass,
            "score": score,
            "reasons": reasons,
        }

    finally:
        db.close()


def drafting_job(project_id: str, candidate_id: str) -> Dict[str, Any]:
    """Background job to draft message using LLM"""
    db = SessionLocal()
    try:
        candidate = crud.get_candidate(db, uuid.UUID(candidate_id))
        project = crud.get_project(db, uuid.UUID(project_id))

        if not candidate or not project:
            return {"error": "Candidate or project not found"}

        # Build facts
        candidate_facts = {
            "full_name": candidate.full_name,
            "first_name": candidate.first_name,
            "title": candidate.title,
            "company": candidate.company,
            "region": candidate.region,
        }

        project_facts = {
            "name": project.name,
            "industry": project.industry,
            "subvertical": project.subvertical,
        }

        # Call LLM service
        llm_service = LLMService()
        draft_result = llm_service.draft_message(candidate_facts, project_facts)

        # Validate draft
        provided_facts = {
            **{f"candidate.{k}": v for k, v in candidate_facts.items() if v},
            **{f"project.{k}": v for k, v in project_facts.items() if v},
        }

        validation_flags = DraftValidator.validate(
            subject=draft_result["subject"],
            body=draft_result["body"],
            facts_used=draft_result["facts_used"],
            provided_facts=provided_facts,
        )

        # Merge risk flags
        all_risk_flags = list(set(draft_result.get("risk_flags", []) + validation_flags))

        # Save draft
        db_draft = crud.create_draft(
            db,
            candidate_id=uuid.UUID(candidate_id),
            project_id=uuid.UUID(project_id),
            subject=draft_result["subject"],
            body=draft_result["body"],
            facts_used=draft_result["facts_used"],
            risk_flags=all_risk_flags,
        )

        return {
            "draft_id": str(db_draft.id),
            "candidate_id": str(candidate.id),
            "project_id": str(project.id),
            "risk_flags": all_risk_flags,
            "safe_to_send": len(all_risk_flags) == 0,
        }

    finally:
        db.close()


def send_job(draft_id: str, actor: str) -> Dict[str, Any]:
    """Background job to send approved draft via email"""
    db = SessionLocal()
    try:
        draft = crud.get_draft(db, uuid.UUID(draft_id))
        if not draft:
            return {"error": "Draft not found"}

        candidate = crud.get_candidate(db, draft.candidate_id)
        if not candidate or not candidate.email:
            return {"error": "Candidate email not available"}

        # Check do-not-contact
        if crud.is_do_not_contact(db, candidate.email):
            return {"error": "Candidate is on do-not-contact list"}

        # Check if approved
        if not draft.approved_at:
            return {"error": "Draft not approved"}

        # Verify approval hash - detect tampering
        if not crud.verify_approval_hash(draft):
            return {"error": "Draft approval integrity check failed - content may have been modified"}

        # Note: Risk flags are informational for reviewers. If a draft was approved,
        # the human reviewer has accepted any risks. We proceed with sending.

        # Generate idempotency key (stable per draft, not per actor)
        idempotency_key = f"draft:{draft_id}"

        # Get or create event with lock (proper idempotency)
        outbound_event, is_new = crud.get_or_create_outbound_event_with_lock(
            db,
            message_draft_id=draft.id,
            candidate_id=candidate.id,
            project_id=draft.project_id,
            idempotency_key=idempotency_key,
        )

        # If already sent, return early (idempotent)
        if outbound_event.status == models.OutboundEventStatus.SENT:
            db.rollback()  # Release lock
            return {
                "message": "Already sent (idempotent)",
                "event_id": str(outbound_event.id),
            }

        # Check rate limit AFTER idempotency check but BEFORE sending
        from app.services.rate_limiter import RateLimiter
        domain = RateLimiter.get_domain_from_email(candidate.email)
        if not RateLimiter.can_send_to_domain(domain):
            db.rollback()  # Release lock without creating duplicate events
            return {"error": f"Rate limit exceeded for domain {domain}", "status": "rate_limited"}

        # Apply jitter delay (random delay to avoid overwhelming recipient servers)
        RateLimiter.apply_jitter_delay()

        # Send email (within same transaction)
        email_service = EmailService()
        result = email_service.send_email(
            to_email=candidate.email,
            subject=draft.subject,
            body=draft.body,
        )

        # Update event status atomically
        if result["status"] == "sent":
            # Increment domain counter
            RateLimiter.increment_domain_count(domain)

            outbound_event.status = models.OutboundEventStatus.SENT
            outbound_event.provider_message_id = result["message_id"]
            outbound_event.meta = {"actor": actor}
            db.commit()  # Commit all changes atomically

            # Update candidate status
            crud.update_candidate_status(db, candidate.id, models.CandidateStatus.SENT)

            # Create conversation + outbound message
            conversation = crud.get_or_create_conversation(
                db, candidate.id, draft.project_id
            )
            crud.create_conversation_message(
                db,
                conversation_id=conversation.id,
                direction=models.MessageDirection.OUTBOUND,
                from_addr="outreach@example.com",
                to_addr=candidate.email,
                subject=draft.subject,
                body_text=draft.body,
                raw_payload=None,
            )

            crud.create_audit_log(
                db, actor, "send", "draft", str(draft.id), {"candidate_id": str(candidate.id)}
            )

            return {
                "status": "sent",
                "event_id": str(outbound_event.id),
                "message_id": result["message_id"],
            }
        else:
            outbound_event.status = models.OutboundEventStatus.FAILED
            outbound_event.meta = {"error": result["error"], "actor": actor}
            db.commit()
            return {"error": result["error"]}

    finally:
        db.close()
