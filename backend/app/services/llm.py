import json
from typing import Dict, List, Any, Optional

from anthropic import Anthropic

from app.config import settings


class LLMService:
    """Service for LLM-based message drafting with strict anti-hallucination controls"""

    def __init__(self):
        self.client = None
        if settings.anthropic_api_key:
            self.client = Anthropic(api_key=settings.anthropic_api_key)

    def draft_message(
        self,
        candidate_facts: Dict[str, Any],
        project_facts: Dict[str, Any],
        outreach_context: Optional[Dict[str, Any]] = None,
        rejection_learnings: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Draft an outreach message using Claude.

        Args:
            rejection_learnings: List of past rejected drafts with issues to avoid

        Returns dict with: subject, body, facts_used, risk_flags
        """
        if not self.client:
            return self._stub_draft(candidate_facts, project_facts, outreach_context)

        # Build the facts object that LLM can use
        provided_facts = {
            **{f"candidate.{k}": v for k, v in candidate_facts.items() if v},
            **{f"project.{k}": v for k, v in project_facts.items() if v},
        }

        # Create prompt
        prompt = self._build_prompt(provided_facts, outreach_context, rejection_learnings)

        try:
            response = self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            response_text = response.content[0].text

            # Strip markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(lines)

            result = json.loads(response_text)

            # Ensure required fields
            if not all(k in result for k in ["subject", "body", "facts_used"]):
                raise ValueError("Missing required fields in LLM response")

            # Initialize risk_flags if not present
            if "risk_flags" not in result:
                result["risk_flags"] = []

            return result

        except Exception as e:
            # Fallback to stub on error
            return self._stub_draft(candidate_facts, project_facts)

    def _build_prompt(
        self,
        provided_facts: Dict[str, Any],
        outreach_context: Optional[Dict[str, Any]] = None,
        rejection_learnings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build the prompt with expert-network style template and learnings from rejections"""
        facts_json = json.dumps(provided_facts, indent=2)

        # Default outreach context if not provided
        ctx = outreach_context or {}
        research_topic = ctx.get("research_topic", "industry trends and best practices")
        rate_range = ctx.get("rate_range", "$150-300")
        sender_name = ctx.get("sender_name", "[Your Name]")
        sender_title = ctx.get("sender_title", "")

        # Build context-specific interview questions based on the domain
        domain = provided_facts.get("project.subvertical") or provided_facts.get("project.industry") or "their field"

        # Build rejection learnings section if available
        learnings_section = ""
        if rejection_learnings and len(rejection_learnings) > 0:
            learnings_section = "\n\nLEARN FROM PAST MISTAKES - DO NOT REPEAT THESE ISSUES:\n"
            for i, learning in enumerate(rejection_learnings[:3], 1):  # Limit to 3 examples
                issues = learning.get("inferred_issues", [])
                learnings_section += f"\nRejected Example {i}:\n"
                learnings_section += f"- Issues: {', '.join(issues)}\n"
                # Include a snippet of the rejected body to show what to avoid
                rejected_body = learning.get("rejected_body", "")
                if len(rejected_body) > 200:
                    rejected_body = rejected_body[:200] + "..."
                learnings_section += f"- Rejected opening: \"{rejected_body.split(chr(10))[0]}\"\n"

            learnings_section += "\nAVOID these patterns. Write naturally and professionally, not robotically.\n"

        return f"""You are drafting a professional expert-network outreach email (like GLG, AlphaSights, Third Bridge style).{learnings_section}

CANDIDATE FACTS (use ONLY these - do not hallucinate):
{facts_json}

OUTREACH CONTEXT:
- Research topic: {research_topic}
- Rate: ${rate_range} for 30 min
- Sender: {sender_name} {sender_title}

YOUR TASK:
1. Analyze the candidate's title, company, and any other facts to infer:
   - A specific credential or signal (their role, company reputation, industry position)
   - Their relevant domain expertise
   - What decisions/processes they likely have exposure to

2. Draft an email using this EXACT structure:

---
Hi [FIRST NAME],
I'm reaching out because I saw [SPECIFIC CREDENTIAL/SIGNAL] and it looks like you've had hands-on exposure to [RELEVANT DOMAIN].

I'm doing targeted research on [TOPIC] to inform an internal analysis. Would you be open to a 30-minute call this week or next?

We'd keep it tight — mainly:
• How [CUSTOMERS/TEAMS] evaluate [THING] and what actually drives decisions
• Common pitfalls / failure modes you've seen in [PROCESS]
• What's changing in [MARKET/REGULATION/TECH] in the near future

No prep required. And we can offer $[RATE] for 30 min (varies by experience), for your time.

If you're open, what does your availability look like — or should I send a scheduling link?

Best,
[SENDER NAME]
---

CRITICAL RULES:
- The [SPECIFIC CREDENTIAL/SIGNAL] must be derived ONLY from provided facts (their title + company)
- The [RELEVANT DOMAIN] must be inferred from their role, not invented
- The 3 bullet questions should be tailored to their likely expertise area
- DO NOT invent specific achievements, publications, or events
- Keep it concise and professional

OUTPUT FORMAT (strict JSON):
{{
  "subject": "Brief subject line (under 50 chars, e.g., 'Quick research question')",
  "body": "The full email body following the template above",
  "facts_used": ["list of fact keys you referenced"],
  "inferred_expertise": "Brief description of what expertise you inferred from their role",
  "risk_flags": ["any concerns about the inferences made"]
}}

Draft the email now:"""

    def _stub_draft(
        self,
        candidate_facts: Dict[str, Any],
        project_facts: Dict[str, Any],
        outreach_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fallback stub when no API key is configured"""
        ctx = outreach_context or {}
        first_name = candidate_facts.get("first_name", candidate_facts.get("full_name", "there"))
        title = candidate_facts.get("title", "professional")
        company = candidate_facts.get("company", "your company")

        research_topic = ctx.get("research_topic", "industry trends")
        rate_range = ctx.get("rate_range", "$150-300")
        sender_name = ctx.get("sender_name", "[Your Name]")
        sender_title = ctx.get("sender_title", "")

        facts_used = ["candidate.first_name", "candidate.title", "candidate.company"]

        return {
            "subject": "Quick research question",
            "body": f"""Hi {first_name},
I'm reaching out because I saw your role as {title} at {company} and it looks like you've had hands-on exposure to this space.

I'm doing targeted research on {research_topic} to inform an internal analysis. Would you be open to a 30-minute call this week or next?

We'd keep it tight — mainly:
• How teams evaluate solutions and what actually drives decisions
• Common pitfalls / failure modes you've seen
• What's changing in the market in the near future

No prep required. And we can offer ${rate_range} for 30 min (varies by experience), for your time.

If you're open, what does your availability look like — or should I send a scheduling link?

Best,
{sender_name}""",
            "facts_used": facts_used,
            "risk_flags": ["stub_mode_no_api_key"],
        }
