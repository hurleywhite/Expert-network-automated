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
- Rate: ${rate_range} for 30 min (you may adjust slightly based on seniority level)
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

We'd keep it brief, mainly focusing on:
• How [CUSTOMERS/TEAMS] evaluate [THING] and what actually drives decisions
• Common pitfalls / failure modes you've seen in [PROCESS]
• What's changing in [MARKET/REGULATION/TECH] in the near future

No prep required. And we can offer $[RATE] for 30 min for your time.

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

We'd keep it brief, mainly focusing on:
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

    def score_candidate(
        self,
        candidate_facts: Dict[str, Any],
        project_facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Use LLM to intelligently score a candidate's fit for a project.

        Returns dict with: relevance_score (0-100), confidence, reasoning, signals
        """
        if not self.client:
            return self._stub_score(candidate_facts, project_facts)

        prompt = self._build_scoring_prompt(candidate_facts, project_facts)

        try:
            response = self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Strip markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(lines)

            result = json.loads(response_text)

            # Ensure required fields with defaults
            return {
                "relevance_score": result.get("relevance_score", 50),
                "confidence": result.get("confidence", "medium"),
                "reasoning": result.get("reasoning", []),
                "title_match_quality": result.get("title_match_quality", "partial"),
                "expertise_signals": result.get("expertise_signals", []),
                "concerns": result.get("concerns", []),
                "recommendation": result.get("recommendation", "review"),
            }

        except Exception as e:
            # Fallback to stub on error
            return self._stub_score(candidate_facts, project_facts)

    def _build_scoring_prompt(
        self,
        candidate_facts: Dict[str, Any],
        project_facts: Dict[str, Any],
    ) -> str:
        """Build prompt for LLM-based candidate scoring"""
        return f"""You are an expert network researcher evaluating whether a candidate is a good fit for an expert consultation project.

PROJECT REQUIREMENTS:
- Industry: {project_facts.get('industry', 'Not specified')}
- Subvertical: {project_facts.get('subvertical', 'Not specified')}
- Target Titles: {json.dumps(project_facts.get('titles_include', []))}
- Titles to Exclude: {json.dumps(project_facts.get('titles_exclude', []))}
- Keywords of Interest: {json.dumps(project_facts.get('keywords', []))}
- Minimum Company Size: {project_facts.get('company_size_min', 'Not specified')}
- Target Regions: {json.dumps(project_facts.get('regions', []))}

CANDIDATE PROFILE:
- Name: {candidate_facts.get('full_name', 'Unknown')}
- Title: {candidate_facts.get('title', 'Unknown')}
- Company: {candidate_facts.get('company', 'Unknown')}
- Company Size: {candidate_facts.get('company_employee_count', 'Unknown')} employees
- Region: {candidate_facts.get('region', 'Unknown')}
- Has Email: {'Yes' if candidate_facts.get('email') else 'No'}
- Has LinkedIn: {'Yes' if candidate_facts.get('linkedin_url') else 'No'}

EVALUATE THIS CANDIDATE:

1. TITLE RELEVANCE: Does their title indicate they have the expertise we're looking for?
   - Consider semantic similarity (e.g., "CCO" = "Chief Commercial Officer")
   - Consider related roles that would have similar knowledge
   - Consider seniority level appropriateness

2. COMPANY FIT: Does their company context make them a good source?
   - Is the company in the right industry/space?
   - Is the company size appropriate?
   - Would they have relevant exposure at this company?

3. EXPERTISE SIGNALS: What specific knowledge would they likely have?
   - What decisions do they probably make or influence?
   - What processes/systems are they likely familiar with?
   - What market dynamics would they understand?

4. CONCERNS: What might make them a poor fit?
   - Title mismatch or tangential role
   - Company in wrong industry
   - Seniority too junior/senior for the need

OUTPUT FORMAT (strict JSON):
{{
  "relevance_score": <0-100 integer>,
  "confidence": "<high|medium|low>",
  "title_match_quality": "<exact|strong|partial|weak|mismatch>",
  "reasoning": [
    "reason 1 for the score",
    "reason 2 for the score",
    "reason 3 for the score"
  ],
  "expertise_signals": [
    "specific expertise they likely have",
    "another area of knowledge"
  ],
  "concerns": [
    "any concern about fit (or empty array if none)"
  ],
  "recommendation": "<priority|include|review|skip>"
}}

SCORING GUIDELINES:
- 85-100: Excellent fit - title closely matches, company is in target space, high confidence
- 70-84: Good fit - strong relevance, would likely be valuable
- 50-69: Moderate fit - some relevance but not ideal match
- 30-49: Weak fit - tangential relevance, consider only if pipeline is thin
- 0-29: Poor fit - likely not relevant, skip unless desperate

Be rigorous but practical. We want experts who can speak credibly to the topic, not perfect matches.

Evaluate now:"""

    def _stub_score(
        self,
        candidate_facts: Dict[str, Any],
        project_facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fallback scoring when no API key is configured"""
        title = (candidate_facts.get("title") or "").lower()
        titles_include = [t.lower() for t in project_facts.get("titles_include", [])]

        # Simple title matching
        title_match = "mismatch"
        base_score = 40

        for target in titles_include:
            if target in title:
                title_match = "exact"
                base_score = 75
                break
            # Check word overlap
            target_words = set(target.split())
            title_words = set(title.split())
            if target_words & title_words:
                title_match = "partial"
                base_score = 55
                break

        # Adjust for data quality
        if candidate_facts.get("email"):
            base_score += 10
        if candidate_facts.get("linkedin_url"):
            base_score += 5
        if candidate_facts.get("company_employee_count"):
            base_score += 5

        return {
            "relevance_score": min(100, base_score),
            "confidence": "low",
            "title_match_quality": title_match,
            "reasoning": ["stub_mode_no_api_key - using rule-based fallback"],
            "expertise_signals": [],
            "concerns": ["LLM scoring not available - basic matching only"],
            "recommendation": "review",
        }
