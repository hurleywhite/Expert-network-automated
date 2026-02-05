"""
Natural language project brief parser.

Converts plain English descriptions like:
  "Find 401(k) benefits administrators at companies with 10,000+ employees"

Into structured project criteria.
"""
import json
from typing import Dict, Any, Optional

from anthropic import Anthropic

from app.config import settings


class ProjectParser:
    """Parse natural language expert search requests into structured criteria."""

    def __init__(self):
        self.client = None
        if settings.anthropic_api_key:
            self.client = Anthropic(api_key=settings.anthropic_api_key)

    def parse(self, description: str) -> Dict[str, Any]:
        """
        Parse a natural language description into project criteria.

        Example input:
            "Find 401(k) benefits administrators at companies with 10,000+ employees"

        Example output:
            {
                "name": "401(k) Benefits Administrators",
                "titles_include": ["Benefits Administrator", "Benefits Manager", "401k Administrator"],
                "keywords": ["401k", "retirement", "benefits"],
                "company_size_min": 10000,
                "industry": null,
                "regions": [],
                "titles_exclude": [],
                "exclusions": [],
                "interpretation": "Looking for HR/benefits professionals who manage 401(k) plans..."
            }
        """
        if not self.client:
            return self._stub_parse(description)

        prompt = self._build_prompt(description)

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
                # Remove first line (```json) and last line (```)
                lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(lines)

            result = json.loads(response_text)
            return result

        except Exception as e:
            # Fallback to stub on error
            return self._stub_parse(description)

    def _build_prompt(self, description: str) -> str:
        return f"""You are an expert network researcher (like GLG, AlphaSights, Third Bridge).
Your job is to interpret a client's expert search request and extract structured criteria.

CLIENT REQUEST:
"{description}"

TASK:
Parse this into structured search criteria. Think like an expert network associate:
- What job titles would these experts have?
- What keywords indicate relevant expertise?
- What company characteristics matter?
- What should we exclude?

OUTPUT FORMAT (strict JSON):
{{
  "name": "Short descriptive name for this search",
  "interpretation": "Your understanding of what the client wants (1-2 sentences)",
  "titles_include": ["List", "of", "job", "titles", "to", "target"],
  "titles_exclude": ["Titles", "to", "avoid"],
  "keywords": ["domain", "expertise", "keywords"],
  "exclusions": ["companies", "or", "types", "to", "exclude"],
  "industry": "Primary industry or null",
  "subvertical": "Specific subvertical or null",
  "regions": ["Geographic regions if specified, or empty"],
  "company_size_min": 10000 or null if not specified,
  "seniority_signals": ["Words indicating seniority level to look for"],
  "expertise_signals": ["Specific expertise indicators"]
}}

GUIDELINES:
- titles_include: Be comprehensive. Include variations (Manager vs Director vs VP)
- keywords: Focus on domain expertise, not generic business terms
- Think about what LinkedIn profile text would indicate this expertise
- Consider adjacent roles that might have relevant knowledge
- For company_size_min, default to 10000 if "enterprise" or "large company" mentioned

Parse the request now:"""

    def _stub_parse(self, description: str) -> Dict[str, Any]:
        """Fallback parsing when no API key available."""
        # Basic keyword extraction
        description_lower = description.lower()

        # Try to extract company size
        company_size_min = None
        if "10,000" in description or "10000" in description:
            company_size_min = 10000
        elif "1,000" in description or "1000" in description:
            company_size_min = 1000
        elif "enterprise" in description_lower or "large" in description_lower:
            company_size_min = 10000

        return {
            "name": description[:50] + "..." if len(description) > 50 else description,
            "interpretation": "Parsed from description (stub mode - no API key)",
            "titles_include": [],
            "titles_exclude": [],
            "keywords": description.split()[:5],  # First 5 words as keywords
            "exclusions": [],
            "industry": None,
            "subvertical": None,
            "regions": [],
            "company_size_min": company_size_min,
            "seniority_signals": [],
            "expertise_signals": [],
        }
