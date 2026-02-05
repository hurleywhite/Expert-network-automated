from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud, models
from app.database import get_db
from app.deps import verify_webhook_secret
from app.schemas import InboundEmailPayload
from app.services.email import EmailService

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


@router.post("/inbound-email")
async def receive_inbound_email(
    to: str = Form(...),
    from_email: str = Form(..., alias="from"),
    subject: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    html: Optional[str] = Form(None),
    envelope: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: str = Depends(verify_webhook_secret),
):
    """
    Receive inbound email from SendGrid Inbound Parse (multipart/form-data).

    Parses email, stores message, classifies intent, updates conversation.
    """
    # Parse envelope JSON if present
    envelope_dict = {}
    if envelope:
        try:
            import json
            envelope_dict = json.loads(envelope)
        except:
            pass

    # Extract email addresses and body
    to_email = to
    body_text = text or html or ""

    # Find candidate by email
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.email == from_email)
        .first()
    )

    if not candidate:
        # Could create a new candidate here, or just log and ignore
        return {"status": "ignored", "reason": "unknown_sender"}

    # Find most recent conversation for this candidate
    conversation = (
        db.query(models.Conversation)
        .filter(models.Conversation.candidate_id == candidate.id)
        .order_by(models.Conversation.updated_at.desc())
        .first()
    )

    if not conversation:
        # No conversation found - might be an unexpected reply
        return {"status": "ignored", "reason": "no_conversation"}

    # Classify reply
    email_service = EmailService()
    classification = email_service.classify_inbound_reply(body_text)

    # Store message
    crud.create_conversation_message(
        db,
        conversation_id=conversation.id,
        direction=models.MessageDirection.INBOUND,
        from_addr=from_email,
        to_addr=to_email,
        subject=subject or "",
        body_text=body_text,
        raw_payload={"to": to_email, "from": from_email, "subject": subject, "text": text, "html": html},
    )

    # Update conversation status
    status_map = {
        "interested": models.ConversationStatus.INTERESTED,
        "not_interested": models.ConversationStatus.NOT_INTERESTED,
        "referral": models.ConversationStatus.REFERRAL,
        "ooo": models.ConversationStatus.OOO,
        "unsubscribe": models.ConversationStatus.UNSUBSCRIBE,
        "unknown": models.ConversationStatus.UNKNOWN,
    }
    new_status = status_map[classification]
    crud.update_conversation_status(db, conversation.id, new_status)

    # If unsubscribe, add to do-not-contact
    if classification == "unsubscribe":
        crud.add_do_not_contact(db, from_email, "unsubscribe_via_email")

    crud.create_audit_log(
        db,
        "system",
        "inbound_reply",
        "candidate",
        str(candidate.id),
        {"classification": classification},
    )

    return {
        "status": "processed",
        "candidate_id": str(candidate.id),
        "conversation_id": str(conversation.id),
        "classification": classification,
    }


@router.post("/sendgrid-events")
def receive_sendgrid_events(
    events: List[dict],
    db: Session = Depends(get_db),
    _: str = Depends(verify_webhook_secret),
):
    """
    Handle SendGrid Event Webhook for bounces, drops, spam reports, and unsubscribes.

    SendGrid sends event batches as JSON array.
    Normalizes event names to handle both "spamreport" and "spam_report".
    """
    results = []

    for event in events:
        raw_event_type = event.get("event")
        email = event.get("email")
        sg_message_id = event.get("sg_message_id")

        if not email or not raw_event_type:
            continue

        # Normalize event type to lowercase and handle aliases
        event_type = raw_event_type.lower()
        # Map spam_report to spamreport for consistency
        if event_type == "spam_report":
            event_type = "spamreport"

        # Handle hard failures that should trigger do-not-contact
        # Include: bounce, dropped, blocked, spamreport
        if event_type in ["bounce", "dropped", "blocked", "spamreport"]:
            # Update outbound_event status if found
            if sg_message_id:
                outbound_event = (
                    db.query(models.OutboundEvent)
                    .filter(models.OutboundEvent.provider_message_id == sg_message_id)
                    .first()
                )
                if outbound_event:
                    crud.update_outbound_event_status(
                        db,
                        outbound_event.id,
                        models.OutboundEventStatus.BOUNCED,
                        meta={"event_type": event_type, "reason": event.get("reason")}
                    )

            # Add to do-not-contact with normalized event name
            crud.add_do_not_contact(db, email, f"sendgrid_{event_type}")

            # Update candidate status to DO_NOT_CONTACT if candidate exists
            candidate = (
                db.query(models.Candidate)
                .filter(models.Candidate.email == email)
                .first()
            )
            if candidate:
                crud.update_candidate_status(db, candidate.id, models.CandidateStatus.DO_NOT_CONTACT)

            results.append({"email": email, "event": event_type, "status": "processed"})

        elif event_type == "unsubscribe":
            crud.add_do_not_contact(db, email, "sendgrid_unsubscribe")

            # Update candidate status to DO_NOT_CONTACT if candidate exists
            candidate = (
                db.query(models.Candidate)
                .filter(models.Candidate.email == email)
                .first()
            )
            if candidate:
                crud.update_candidate_status(db, candidate.id, models.CandidateStatus.DO_NOT_CONTACT)

            results.append({"email": email, "event": event_type, "status": "processed"})

    return {"processed": len(results), "results": results}
