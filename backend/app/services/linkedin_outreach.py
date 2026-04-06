"""
LinkedIn Outreach Service — Automated personalized LinkedIn messaging.
Uses Claude to generate connection notes and follow-up messages,
and Playwright for browser automation.
"""
import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# Daily limits to stay safe on LinkedIn
MAX_CONNECTIONS_PER_DAY = 50
MAX_MESSAGES_PER_DAY = 100
MIN_DELAY_SECONDS = 120  # 2 minutes between actions
MAX_DELAY_SECONDS = 300  # 5 minutes between actions

CONNECTION_NOTE_PROMPT = """You are writing a LinkedIn connection request note.
The note must be under 300 characters. It should be warm, professional, and reference
the recipient's specific expertise relevant to the research project.

Do NOT be generic. Reference their specific role, company, or domain expertise.
Do NOT mention that you found them through any tool or database.
Do NOT use buzzwords like "synergy" or "leverage".

Example good notes:
- "Hi Craig — your database modernization work at WSI caught my attention. We're researching enterprise DB migration strategies and would love to get your perspective."
- "Hi Sarah — I noticed your experience leading cloud transformations at Deloitte. We're exploring similar initiatives and your insights would be invaluable."
"""

FOLLOWUP_MESSAGE_PROMPT = """You are writing a LinkedIn follow-up message to a newly connected expert.
The message should be:
- 2-3 short paragraphs
- Professional and respectful of their time
- Specific about what expertise you're seeking
- Clear about the format (30-60 min consultation call)
- Mention compensation if a rate is known
- Include a clear call to action

Do NOT be overly formal or use corporate jargon.
Do NOT write more than 4 sentences per paragraph.
"""


async def generate_connection_note(
    expert_name: str,
    expert_title: str,
    expert_company: str,
    project_description: str,
    project_expertise: list[str],
) -> str:
    """Generate a personalized LinkedIn connection note (≤300 chars)."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": f"""Write a LinkedIn connection note for:
- Expert: {expert_name}, {expert_title} at {expert_company}
- Project: {project_description}
- Their relevant expertise: {'; '.join(project_expertise[:3])}

Return ONLY the note text, nothing else. Must be under 300 characters.""",
            }
        ],
        system=CONNECTION_NOTE_PROMPT,
    )

    note = message.content[0].text.strip().strip('"')
    # Enforce 300 char limit
    if len(note) > 300:
        note = note[:297] + "..."
    return note


async def generate_followup_message(
    expert_name: str,
    expert_title: str,
    expert_company: str,
    project_description: str,
    project_expertise: list[str],
    rate_per_hour: Optional[float] = None,
    sender_name: str = "Research Team",
) -> str:
    """Generate a personalized LinkedIn follow-up message."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    rate_mention = f"We compensate experts at ${rate_per_hour}/hour for their time." if rate_per_hour else "We compensate experts for their time at competitive market rates."

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": f"""Write a LinkedIn follow-up message for:
- Expert: {expert_name}, {expert_title} at {expert_company}
- Sender: {sender_name}
- Project: {project_description}
- Their relevant expertise: {'; '.join(project_expertise[:3])}
- Compensation: {rate_mention}

Return ONLY the message text, nothing else.""",
            }
        ],
        system=FOLLOWUP_MESSAGE_PROMPT,
    )

    return message.content[0].text.strip()


async def send_linkedin_connection(
    linkedin_url: str,
    connection_note: str,
    session_cookie: Optional[str] = None,
) -> dict:
    """Send a LinkedIn connection request using Playwright browser automation.

    Returns dict with status and any error message.
    """
    cookie = session_cookie or settings.linkedin_session_cookie
    if not cookie:
        return {
            "success": False,
            "error": "LinkedIn session cookie not configured. Set LINKEDIN_SESSION_COOKIE in .env",
        }

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()

            # Set LinkedIn session cookie
            await context.add_cookies([{
                "name": "li_at",
                "value": cookie,
                "domain": ".linkedin.com",
                "path": "/",
            }])

            page = await context.new_page()

            # Navigate to the profile
            await page.goto(linkedin_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Look for Connect button
            connect_btn = page.locator('button:has-text("Connect")')
            if await connect_btn.count() == 0:
                # Might need to click "More" first
                more_btn = page.locator('button:has-text("More")')
                if await more_btn.count() > 0:
                    await more_btn.first.click()
                    await page.wait_for_timeout(1000)
                    connect_btn = page.locator('button:has-text("Connect")')

            if await connect_btn.count() == 0:
                await browser.close()
                return {"success": False, "error": "Connect button not found — may already be connected"}

            await connect_btn.first.click()
            await page.wait_for_timeout(1500)

            # Click "Add a note"
            add_note_btn = page.locator('button:has-text("Add a note")')
            if await add_note_btn.count() > 0:
                await add_note_btn.first.click()
                await page.wait_for_timeout(1000)

                # Type the note
                note_field = page.locator('textarea[name="message"]')
                if await note_field.count() > 0:
                    await note_field.fill(connection_note)
                    await page.wait_for_timeout(500)

            # Click Send
            send_btn = page.locator('button:has-text("Send")')
            if await send_btn.count() > 0:
                await send_btn.first.click()
                await page.wait_for_timeout(2000)

            await browser.close()
            return {"success": True}

    except ImportError:
        return {"success": False, "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}
    except Exception as e:
        logger.error(f"LinkedIn connection request failed: {e}")
        return {"success": False, "error": str(e)}


async def send_linkedin_message(
    linkedin_url: str,
    message_text: str,
    session_cookie: Optional[str] = None,
) -> dict:
    """Send a LinkedIn direct message to an already-connected expert."""
    cookie = session_cookie or settings.linkedin_session_cookie
    if not cookie:
        return {"success": False, "error": "LinkedIn session cookie not configured"}

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()

            await context.add_cookies([{
                "name": "li_at",
                "value": cookie,
                "domain": ".linkedin.com",
                "path": "/",
            }])

            page = await context.new_page()
            await page.goto(linkedin_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Click Message button
            msg_btn = page.locator('button:has-text("Message")')
            if await msg_btn.count() == 0:
                await browser.close()
                return {"success": False, "error": "Message button not found — may not be connected"}

            await msg_btn.first.click()
            await page.wait_for_timeout(2000)

            # Type message
            msg_box = page.locator('div[role="textbox"]')
            if await msg_box.count() > 0:
                await msg_box.first.fill(message_text)
                await page.wait_for_timeout(1000)

                # Send
                send_btn = page.locator('button[type="submit"]:has-text("Send")')
                if await send_btn.count() > 0:
                    await send_btn.first.click()
                    await page.wait_for_timeout(2000)

            await browser.close()
            return {"success": True}

    except Exception as e:
        logger.error(f"LinkedIn message failed: {e}")
        return {"success": False, "error": str(e)}
