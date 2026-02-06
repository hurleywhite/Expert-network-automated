"""
Expert outreach pipeline orchestration.

Coordinates the full flow:
1. Parse natural language brief
2. Score all candidates
3. Draft messages for qualified candidates
4. Queue for human review
5. Send approved drafts
"""
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app import crud, models
from app.services.project_parser import ProjectParser
from app.services.expert_scorer import ExpertScorer
from app.services.llm import LLMService
from app.services.validator import DraftValidator


class Pipeline:
    """Orchestrates the expert outreach pipeline."""

    # Minimum score to qualify for outreach
    MIN_SCORE_FOR_OUTREACH = 40

    # Minimum score for priority outreach
    PRIORITY_SCORE_THRESHOLD = 70

    @classmethod
    def create_project_from_description(
        cls, db: Session, description: str, created_by: str
    ) -> Dict[str, Any]:
        """
        Create a project from natural language description, or return existing if similar.

        Example:
            "Find 401(k) benefits administrators at companies with 10,000+ employees"

        If a similar project already exists (by name/industry), returns existing project.
        New candidates will be added to the existing project when searched.
        """
        parser = ProjectParser()
        parsed = parser.parse(description)

        project_name = parsed.get("name", description[:50])
        industry = parsed.get("industry")
        subvertical = parsed.get("subvertical")

        # Check for existing similar project
        existing_project = cls._find_similar_project(
            db, project_name, industry, subvertical
        )

        if existing_project:
            # Return existing project
            crud.create_audit_log(
                db,
                created_by,
                "found_existing_project",
                "project",
                str(existing_project.id),
                {
                    "original_description": description,
                    "matched_to": existing_project.name,
                },
            )
            return {
                "project": existing_project,
                "interpretation": f"Found existing project: {existing_project.name}",
                "parsed_criteria": parsed,
                "is_existing": True,
            }

        # Create new project
        from app.schemas import ProjectBriefCreate

        project_data = ProjectBriefCreate(
            name=project_name,
            industry=industry,
            subvertical=subvertical,
            company_size_min=parsed.get("company_size_min"),
            regions=parsed.get("regions", []),
            titles_include=parsed.get("titles_include", []),
            titles_exclude=parsed.get("titles_exclude", []),
            keywords=parsed.get("keywords", []),
            exclusions=parsed.get("exclusions", []),
        )

        project = crud.create_project(db, project_data)

        # Log the creation
        crud.create_audit_log(
            db,
            created_by,
            "create_project_from_nl",
            "project",
            str(project.id),
            {
                "original_description": description,
                "interpretation": parsed.get("interpretation"),
                "parsed_criteria": parsed,
            },
        )

        return {
            "project": project,
            "interpretation": parsed.get("interpretation"),
            "parsed_criteria": parsed,
            "is_existing": False,
        }

    @classmethod
    def _find_similar_project(
        cls, db: Session, name: str, industry: Optional[str], subvertical: Optional[str]
    ) -> Optional[models.ProjectBrief]:
        """
        Find an existing project that matches the criteria.

        Matches on:
        - Exact or similar name
        - Same industry + subvertical
        """
        # Try exact name match first
        existing = db.query(models.ProjectBrief).filter(
            models.ProjectBrief.name == name
        ).first()
        if existing:
            return existing

        # Try industry + subvertical match
        if industry and subvertical:
            existing = db.query(models.ProjectBrief).filter(
                models.ProjectBrief.industry == industry,
                models.ProjectBrief.subvertical == subvertical,
            ).first()
            if existing:
                return existing

        # Try fuzzy name match (contains key words)
        name_lower = name.lower()
        key_words = [w for w in name_lower.split() if len(w) > 4]

        if key_words:
            projects = db.query(models.ProjectBrief).all()
            for project in projects:
                project_name_lower = project.name.lower()
                # Check if most key words match
                matches = sum(1 for w in key_words if w in project_name_lower)
                if matches >= len(key_words) * 0.6:  # 60% word match
                    return project

        return None

    @classmethod
    def score_all_candidates(
        cls, db: Session, project_id: UUID, outreach_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Score all candidates against a project and auto-generate drafts.

        After scoring, automatically drafts emails for qualified candidates (score >= 40).

        Args:
            outreach_context: Optional dict with research_topic, rate_range, sender_name, sender_title

        Returns scoring summary, candidate rankings, and auto-draft count.
        """
        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        # Build project criteria dict
        project_dict = {
            "titles_include": project.titles_include or [],
            "titles_exclude": project.titles_exclude or [],
            "keywords": project.keywords or [],
            "exclusions": project.exclusions or [],
            "regions": project.regions or [],
            "company_size_min": project.company_size_min,
            "seniority_signals": [],  # Could be added to project model
            "expertise_signals": [],
        }

        # Get candidates sourced for this specific project
        # Join with CandidateSource and filter by project_id in source_payload
        from sqlalchemy import cast, String
        from sqlalchemy.dialects.postgresql import JSONB

        # Include NEW, ENRICHED, and DRAFTED candidates for (re)scoring
        # This allows re-scoring after criteria changes (e.g., geographic filtering)
        candidates_for_project = (
            db.query(models.Candidate)
            .join(models.CandidateSource)
            .filter(
                models.CandidateSource.source_payload['project_id'].astext == str(project_id),
                models.Candidate.status.in_([
                    models.CandidateStatus.NEW,
                    models.CandidateStatus.ENRICHED,
                    models.CandidateStatus.DRAFTED,
                ])
            )
            .all()
        )

        candidates = candidates_for_project

        results = {
            "total_candidates": len(candidates),
            "scored": 0,
            "qualified": 0,
            "priority": 0,
            "excluded": 0,
            "rankings": [],
        }

        for candidate in candidates:
            candidate_dict = {
                "full_name": candidate.full_name,
                "email": candidate.email,
                "title": candidate.title,
                "company": candidate.company,
                "region": candidate.region,
                "company_employee_count": candidate.company_employee_count,
                "linkedin_url": candidate.linkedin_url,
            }

            hard_pass, score, reasons, details = ExpertScorer.score_candidate(
                candidate_dict, project_dict
            )

            # Save score to database
            crud.create_score(
                db,
                candidate_id=candidate.id,
                project_id=project_id,
                hard_pass=hard_pass,
                score=score,
                reasons=reasons,
            )

            results["scored"] += 1

            if hard_pass:
                results["excluded"] += 1
            elif score >= cls.MIN_SCORE_FOR_OUTREACH:
                results["qualified"] += 1
                if score >= cls.PRIORITY_SCORE_THRESHOLD:
                    results["priority"] += 1

            results["rankings"].append({
                "candidate_id": str(candidate.id),
                "full_name": candidate.full_name,
                "title": candidate.title,
                "company": candidate.company,
                "score": score,
                "hard_pass": hard_pass,
                "recommendation": details.get("recommendation"),
                "reasons": reasons[:5],  # Top 5 reasons
            })

        # Sort by score descending
        results["rankings"].sort(key=lambda x: x["score"], reverse=True)

        # Auto-generate drafts for qualified candidates
        if results["qualified"] > 0:
            # Use provided context or build default from project info
            if outreach_context:
                context = outreach_context
            else:
                context = {
                    "research_topic": f"{project.industry or 'industry'} trends and practices",
                    "rate_range": "500 dollars",
                    "sender_name": "Research Team",
                    "sender_title": "Research Director",
                }

            draft_results = cls.draft_for_qualified_candidates(
                db=db,
                project_id=project_id,
                min_score=cls.MIN_SCORE_FOR_OUTREACH,
                outreach_context=context,
            )

            results["auto_drafted"] = draft_results.get("drafted", 0)
            results["draft_errors"] = draft_results.get("errors", 0)

        return results

    @classmethod
    def draft_for_qualified_candidates(
        cls,
        db: Session,
        project_id: UUID,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
        outreach_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate drafts for all qualified candidates.

        Only drafts for candidates who:
        - Have a score >= min_score (default: MIN_SCORE_FOR_OUTREACH)
        - Are not hard-passed
        - Don't already have a draft for this project
        - Have an email address
        - Are not on do-not-contact

        Args:
            outreach_context: Optional dict with research_topic, rate_range, sender_name, sender_title
        """
        if min_score is None:
            min_score = cls.MIN_SCORE_FOR_OUTREACH

        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        # Get qualified candidates with scores
        scores = (
            db.query(models.Score)
            .filter(
                models.Score.project_id == project_id,
                models.Score.hard_pass == False,
                models.Score.score >= min_score,
            )
            .order_by(models.Score.score.desc())
            .all()
        )

        if limit:
            scores = scores[:limit]

        results = {
            "total_qualified": len(scores),
            "drafted": 0,
            "skipped": 0,
            "errors": 0,
            "drafts": [],
        }

        llm_service = LLMService()

        # Fetch rejection learnings for this project to improve future drafts
        rejection_learnings = (
            db.query(models.RejectionLearning)
            .filter(models.RejectionLearning.project_id == project_id)
            .order_by(models.RejectionLearning.created_at.desc())
            .limit(5)
            .all()
        )
        learnings_data = [
            {
                "rejected_body": rl.rejected_body,
                "inferred_issues": rl.inferred_issues or [],
            }
            for rl in rejection_learnings
        ]

        for score_record in scores:
            candidate = crud.get_candidate(db, score_record.candidate_id)

            # Skip if no email
            if not candidate.email:
                results["skipped"] += 1
                continue

            # Skip if on do-not-contact
            if crud.is_do_not_contact(db, candidate.email):
                results["skipped"] += 1
                continue

            # Skip if already has draft for this project
            existing_draft = (
                db.query(models.MessageDraft)
                .filter(
                    models.MessageDraft.candidate_id == candidate.id,
                    models.MessageDraft.project_id == project_id,
                )
                .first()
            )
            if existing_draft:
                results["skipped"] += 1
                continue

            # Build facts for drafting
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

            try:
                # Generate draft (with learnings from past rejections)
                draft_result = llm_service.draft_message(
                    candidate_facts,
                    project_facts,
                    outreach_context,
                    rejection_learnings=learnings_data if learnings_data else None,
                )

                # Validate
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

                all_risk_flags = list(set(draft_result.get("risk_flags", []) + validation_flags))

                # Save draft
                draft = crud.create_draft(
                    db,
                    candidate_id=candidate.id,
                    project_id=project_id,
                    subject=draft_result["subject"],
                    body=draft_result["body"],
                    facts_used=draft_result["facts_used"],
                    risk_flags=all_risk_flags,
                )

                results["drafted"] += 1
                results["drafts"].append({
                    "draft_id": str(draft.id),
                    "candidate_id": str(candidate.id),
                    "candidate_name": candidate.full_name,
                    "candidate_title": candidate.title,
                    "candidate_company": candidate.company,
                    "score": score_record.score,
                    "subject": draft.subject,
                    "risk_flags": all_risk_flags,
                    "safe_to_send": len(all_risk_flags) == 0,
                })

            except Exception as e:
                results["errors"] += 1

        return results

    @classmethod
    def get_review_queue(
        cls, db: Session, project_id: UUID
    ) -> Dict[str, Any]:
        """
        Get drafts pending human review.

        Returns drafts grouped by:
        - Ready to approve (no risk flags)
        - Needs review (has risk flags)
        """
        drafts = (
            db.query(models.MessageDraft)
            .filter(
                models.MessageDraft.project_id == project_id,
                models.MessageDraft.approved_at == None,
            )
            .all()
        )

        ready_to_approve = []
        needs_review = []

        for draft in drafts:
            candidate = crud.get_candidate(db, draft.candidate_id)
            # Get the latest score (order by id desc to get most recent)
            score = (
                db.query(models.Score)
                .filter(
                    models.Score.candidate_id == draft.candidate_id,
                    models.Score.project_id == project_id,
                )
                .order_by(models.Score.id.desc())
                .first()
            )

            # Cap score at 100 for display
            score_value = min(100, score.score) if score else 0

            draft_info = {
                "draft_id": str(draft.id),
                "candidate_id": str(draft.candidate_id),
                "candidate_name": candidate.full_name if candidate else "Unknown",
                "candidate_title": candidate.title if candidate else "",
                "candidate_company": candidate.company if candidate else "",
                "candidate_email": candidate.email if candidate else "",
                "candidate_linkedin": candidate.linkedin_url if candidate else "",
                "score": score_value,
                "subject": draft.subject,
                "body": draft.body,
                "facts_used": draft.facts_used,
                "risk_flags": draft.risk_flags,
                "created_at": draft.created_at.isoformat(),
            }

            if draft.risk_flags:
                needs_review.append(draft_info)
            else:
                ready_to_approve.append(draft_info)

        return {
            "project_id": str(project_id),
            "total_pending": len(drafts),
            "ready_to_approve": {
                "count": len(ready_to_approve),
                "drafts": ready_to_approve,
            },
            "needs_review": {
                "count": len(needs_review),
                "drafts": needs_review,
            },
        }

    @classmethod
    def bulk_approve_safe_drafts(
        cls, db: Session, project_id: UUID, approved_by: str
    ) -> Dict[str, Any]:
        """
        Approve all drafts with no risk flags.

        Human still reviews drafts with risk flags individually.
        """
        from sqlalchemy import cast, String

        drafts = (
            db.query(models.MessageDraft)
            .filter(
                models.MessageDraft.project_id == project_id,
                models.MessageDraft.approved_at == None,
                cast(models.MessageDraft.risk_flags, String) == '[]',
            )
            .all()
        )

        approved_count = 0
        for draft in drafts:
            crud.approve_draft(db, draft.id, approved_by)
            approved_count += 1

        crud.create_audit_log(
            db,
            approved_by,
            "bulk_approve",
            "project",
            str(project_id),
            {"approved_count": approved_count},
        )

        return {
            "project_id": str(project_id),
            "approved_count": approved_count,
            "approved_by": approved_by,
        }

    @classmethod
    def get_pipeline_status(cls, db: Session, project_id: UUID) -> Dict[str, Any]:
        """Get overall pipeline status for a project."""
        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        # Count candidates by status
        candidates_scored = (
            db.query(models.Score)
            .filter(models.Score.project_id == project_id)
            .count()
        )

        qualified = (
            db.query(models.Score)
            .filter(
                models.Score.project_id == project_id,
                models.Score.hard_pass == False,
                models.Score.score >= cls.MIN_SCORE_FOR_OUTREACH,
            )
            .count()
        )

        drafts_total = (
            db.query(models.MessageDraft)
            .filter(models.MessageDraft.project_id == project_id)
            .count()
        )

        drafts_approved = (
            db.query(models.MessageDraft)
            .filter(
                models.MessageDraft.project_id == project_id,
                models.MessageDraft.approved_at != None,
            )
            .count()
        )

        from sqlalchemy import cast, String
        from sqlalchemy.dialects.postgresql import JSONB

        drafts_with_risk = (
            db.query(models.MessageDraft)
            .filter(
                models.MessageDraft.project_id == project_id,
                models.MessageDraft.approved_at == None,
                cast(models.MessageDraft.risk_flags, String) != '[]',
            )
            .count()
        )

        sent = (
            db.query(models.OutboundEvent)
            .filter(
                models.OutboundEvent.project_id == project_id,
                models.OutboundEvent.status == models.OutboundEventStatus.SENT,
            )
            .count()
        )

        replies = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.project_id == project_id,
                models.Conversation.last_status != models.ConversationStatus.NONE,
            )
            .count()
        )

        interested = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.project_id == project_id,
                models.Conversation.last_status == models.ConversationStatus.INTERESTED,
            )
            .count()
        )

        return {
            "project_id": str(project_id),
            "project_name": project.name,
            "pipeline": {
                "candidates_scored": candidates_scored,
                "qualified_for_outreach": qualified,
                "drafts_created": drafts_total,
                "drafts_pending_review": drafts_total - drafts_approved,
                "drafts_with_risk_flags": drafts_with_risk,
                "drafts_approved": drafts_approved,
                "emails_sent": sent,
                "replies_received": replies,
                "interested": interested,
            },
            "next_action": cls._get_next_action(
                candidates_scored, qualified, drafts_total, drafts_approved, sent
            ),
        }

    @classmethod
    def _get_next_action(
        cls,
        scored: int,
        qualified: int,
        drafted: int,
        approved: int,
        sent: int,
    ) -> str:
        """Suggest the next action in the pipeline."""
        if scored == 0:
            return "Score candidates: POST /projects/{id}/score-all"
        if drafted == 0 and qualified > 0:
            return "Generate drafts: POST /projects/{id}/draft-qualified"
        if approved < drafted:
            return "Review and approve drafts: GET /projects/{id}/review-queue"
        if sent < approved:
            return "Send approved drafts: POST /projects/{id}/send-approved"
        return "Monitor replies and follow up with interested experts"

    # Follow-up email template
    FOLLOWUP_TEMPLATE = """Hi {first_name},

Just circling back from our last email, in case you were busy or it was buried. I'm still looking for a couple perspectives on {topic} for an internal analysis, and {credential} made me think you'd be a strong person to speak with.

Would you be open to a 30-minute call this week or next? We can offer {rate} for 30 min for your time. No prep needed — I'd keep it focused on:
• How {customers} evaluate {thing} and what actually drives decisions
• Common pitfalls / failure modes you've seen in {process}
• What you're seeing change in {market} over the next 12–18 months

If you're open, feel free to share a couple times that work — or I can send a scheduling link.

Best,
{sender_name}"""

    @classmethod
    def get_followup_queue(
        cls, db: Session, project_id: UUID, days_since_sent: int = 3
    ) -> Dict[str, Any]:
        """
        Get sent emails that are ready for follow-up.

        Returns emails that:
        - Were sent successfully
        - Have no reply yet
        - Were sent more than days_since_sent days ago
        - Don't already have a follow-up draft
        """
        from datetime import datetime, timedelta

        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        cutoff = datetime.utcnow() - timedelta(days=days_since_sent)

        # Get sent events for initial emails (sequence_number = 1)
        sent_events = (
            db.query(models.OutboundEvent)
            .join(models.MessageDraft)
            .filter(
                models.OutboundEvent.project_id == project_id,
                models.OutboundEvent.status == models.OutboundEventStatus.SENT,
                models.OutboundEvent.created_at < cutoff,
                models.MessageDraft.sequence_number == 1,
            )
            .all()
        )

        ready_for_followup = []

        for event in sent_events:
            candidate = crud.get_candidate(db, event.candidate_id)
            if not candidate:
                continue

            # Check if there's a reply
            has_reply = (
                db.query(models.Conversation)
                .filter(
                    models.Conversation.candidate_id == event.candidate_id,
                    models.Conversation.project_id == project_id,
                    models.Conversation.last_status != models.ConversationStatus.NONE,
                )
                .first()
            )
            if has_reply:
                continue

            # Check if follow-up already exists
            existing_followup = (
                db.query(models.MessageDraft)
                .filter(
                    models.MessageDraft.candidate_id == event.candidate_id,
                    models.MessageDraft.project_id == project_id,
                    models.MessageDraft.sequence_number == 2,
                )
                .first()
            )
            if existing_followup:
                continue

            original_draft = event.message_draft

            ready_for_followup.append({
                "candidate_id": str(candidate.id),
                "candidate_name": candidate.full_name,
                "candidate_title": candidate.title,
                "candidate_company": candidate.company,
                "candidate_email": candidate.email,
                "candidate_linkedin": candidate.linkedin_url,
                "original_draft_id": str(original_draft.id),
                "original_subject": original_draft.subject,
                "sent_at": event.created_at.isoformat(),
                "days_since_sent": (datetime.utcnow() - event.created_at).days,
            })

        return {
            "project_id": str(project_id),
            "ready_for_followup": {
                "count": len(ready_for_followup),
                "candidates": ready_for_followup,
            },
        }

    @classmethod
    def generate_followup_drafts(
        cls,
        db: Session,
        project_id: UUID,
        outreach_context: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate follow-up drafts for sent emails without replies.

        Uses the follow-up template with personalization based on original context.
        """
        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        # Get candidates ready for follow-up
        queue = cls.get_followup_queue(db, project_id)
        if "error" in queue:
            return queue

        candidates = queue["ready_for_followup"]["candidates"]
        if limit:
            candidates = candidates[:limit]

        results = {
            "total_eligible": len(queue["ready_for_followup"]["candidates"]),
            "drafted": 0,
            "errors": 0,
            "drafts": [],
        }

        # Default context
        context = outreach_context or {}
        topic = context.get("research_topic", f"{project.industry or 'industry'} trends")
        rate = context.get("rate_range", "$150-300")
        sender_name = context.get("sender_name", "Research Team")

        for candidate_info in candidates:
            try:
                candidate = crud.get_candidate(db, UUID(candidate_info["candidate_id"]))
                original_draft = crud.get_draft(db, UUID(candidate_info["original_draft_id"]))

                if not candidate or not original_draft:
                    results["errors"] += 1
                    continue

                # Build credential from title/company
                credential = f"your role as {candidate.title} at {candidate.company}"

                # Infer context from project
                customers = "teams" if "B2B" in (project.industry or "") else "customers"
                thing = f"{project.industry or 'solutions'} tools and approaches"
                process = f"{project.industry or 'business'} operations"
                market = f"the {project.industry or 'market'} space"

                # Generate follow-up body
                body = cls.FOLLOWUP_TEMPLATE.format(
                    first_name=candidate.first_name or candidate.full_name.split()[0],
                    topic=topic,
                    credential=credential,
                    rate=rate,
                    customers=customers,
                    thing=thing,
                    process=process,
                    market=market,
                    sender_name=sender_name,
                )

                # Create follow-up draft
                followup = models.MessageDraft(
                    candidate_id=candidate.id,
                    project_id=project_id,
                    subject=f"Re: {original_draft.subject}",
                    body=body,
                    facts_used=["follow_up_template", "original_draft"],
                    risk_flags=[],
                    sequence_number=2,
                    parent_draft_id=original_draft.id,
                )
                db.add(followup)
                db.commit()

                results["drafted"] += 1
                results["drafts"].append({
                    "draft_id": str(followup.id),
                    "candidate_name": candidate.full_name,
                    "subject": followup.subject,
                })

            except Exception as e:
                results["errors"] += 1
                print(f"Error generating follow-up: {e}")

        return results

    @classmethod
    def get_followup_drafts(
        cls, db: Session, project_id: UUID
    ) -> Dict[str, Any]:
        """
        Get all follow-up drafts for a project.

        Returns drafts grouped by status: pending, approved, sent.
        """
        project = crud.get_project(db, project_id)
        if not project:
            return {"error": "Project not found"}

        # Get follow-up drafts (sequence_number > 1)
        followup_drafts = (
            db.query(models.MessageDraft)
            .filter(
                models.MessageDraft.project_id == project_id,
                models.MessageDraft.sequence_number > 1,
            )
            .all()
        )

        # Get sent follow-up IDs
        sent_followup_ids = set(
            row[0] for row in db.query(models.OutboundEvent.message_draft_id)
            .filter(
                models.OutboundEvent.project_id == project_id,
                models.OutboundEvent.status == models.OutboundEventStatus.SENT,
            )
            .all()
        )

        pending = []
        approved = []
        sent = []

        for draft in followup_drafts:
            candidate = crud.get_candidate(db, draft.candidate_id)

            draft_info = {
                "draft_id": str(draft.id),
                "candidate_id": str(draft.candidate_id),
                "candidate_name": candidate.full_name if candidate else "Unknown",
                "candidate_title": candidate.title if candidate else "",
                "candidate_company": candidate.company if candidate else "",
                "candidate_email": candidate.email if candidate else "",
                "candidate_linkedin": candidate.linkedin_url if candidate else None,
                "subject": draft.subject,
                "body": draft.body,
                "sequence_number": draft.sequence_number,
                "created_at": draft.created_at.isoformat(),
            }

            if draft.id in sent_followup_ids:
                draft_info["status"] = "sent"
                sent.append(draft_info)
            elif draft.approved_at:
                draft_info["status"] = "approved"
                draft_info["approved_at"] = draft.approved_at.isoformat()
                draft_info["approved_by"] = draft.approved_by
                approved.append(draft_info)
            else:
                draft_info["status"] = "pending"
                pending.append(draft_info)

        return {
            "project_id": str(project_id),
            "pending": {
                "count": len(pending),
                "drafts": pending,
            },
            "approved": {
                "count": len(approved),
                "drafts": approved,
            },
            "sent": {
                "count": len(sent),
                "drafts": sent,
            },
        }
