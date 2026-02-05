"""
Email service supporting multiple providers.

Currently supports:
- Resend (recommended)
- SendGrid (legacy)
- Stub mode (development)
"""
from typing import Optional

import httpx

from app.config import settings


class EmailService:
    """Service for sending emails via Resend or SendGrid"""

    def __init__(self):
        self.provider = None
        self.client = None

        # Prefer Resend if configured
        if settings.resend_api_key:
            self.provider = "resend"
        elif settings.sendgrid_api_key:
            self.provider = "sendgrid"
            from sendgrid import SendGridAPIClient
            self.client = SendGridAPIClient(settings.sendgrid_api_key)

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> dict:
        """
        Send an email via configured provider.

        Returns dict with status and message_id.
        """
        if self.provider == "resend":
            return self._send_via_resend(to_email, subject, body, from_email, from_name)
        elif self.provider == "sendgrid":
            return self._send_via_sendgrid(to_email, subject, body, from_email, from_name)
        else:
            # Stub mode for development
            return {
                "status": "sent",
                "message_id": f"stub-{to_email}",
                "error": None,
                "provider": "stub",
            }

    def _send_via_resend(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> dict:
        """Send email via Resend API."""
        sender_email = from_email or settings.resend_from_email
        sender_name = from_name or settings.resend_from_name

        # Format sender as "Name <email>" if name provided
        if sender_name:
            sender = f"{sender_name} <{sender_email}>"
        else:
            sender = sender_email

        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": sender,
                    "to": [to_email],
                    "subject": subject,
                    "text": body,
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "sent",
                    "message_id": data.get("id"),
                    "error": None,
                    "provider": "resend",
                }
            else:
                error_data = response.json() if response.content else {}
                return {
                    "status": "failed",
                    "message_id": None,
                    "error": error_data.get("message", f"Resend returned {response.status_code}"),
                    "provider": "resend",
                }

        except Exception as e:
            return {
                "status": "failed",
                "message_id": None,
                "error": str(e),
                "provider": "resend",
            }

    def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> dict:
        """Send email via SendGrid API."""
        from sendgrid.helpers.mail import Mail

        try:
            message = Mail(
                from_email=(from_email or settings.sendgrid_from_email, from_name or settings.sendgrid_from_name),
                to_emails=to_email,
                subject=subject,
                plain_text_content=body,
            )

            response = self.client.send(message)

            if response.status_code in [200, 202]:
                message_id = response.headers.get("X-Message-Id", "unknown")
                return {
                    "status": "sent",
                    "message_id": message_id,
                    "error": None,
                    "provider": "sendgrid",
                }
            else:
                return {
                    "status": "failed",
                    "message_id": None,
                    "error": f"SendGrid returned {response.status_code}",
                    "provider": "sendgrid",
                }

        except Exception as e:
            return {
                "status": "failed",
                "message_id": None,
                "error": str(e),
                "provider": "sendgrid",
            }

    def classify_inbound_reply(self, body_text: str) -> str:
        """
        Classify an inbound reply using simple rule-based logic.

        Returns one of: interested, not_interested, referral, ooo, unsubscribe, unknown
        """
        if not body_text:
            return "unknown"

        body_lower = body_text.lower()

        # Unsubscribe (highest priority)
        if "unsubscribe" in body_lower or "stop" in body_lower or "remove" in body_lower:
            return "unsubscribe"

        # Out of office
        if "out of office" in body_lower or "ooo" in body_lower or "away from" in body_lower:
            return "ooo"

        # Not interested
        if any(
            phrase in body_lower
            for phrase in [
                "not interested",
                "no thanks",
                "not at this time",
                "please remove",
                "don't contact",
            ]
        ):
            return "not_interested"

        # Interested
        if any(
            phrase in body_lower
            for phrase in [
                "yes",
                "happy to",
                "would love to",
                "available",
                "interested",
                "sure",
                "sounds good",
                "let's talk",
            ]
        ):
            return "interested"

        # Referral
        if any(
            phrase in body_lower
            for phrase in [
                "you should contact",
                "reach out to",
                "talk to",
                "connect with",
                "try reaching",
            ]
        ):
            return "referral"

        return "unknown"
