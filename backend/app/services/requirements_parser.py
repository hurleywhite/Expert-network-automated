"""
Requirements Document Parser — Uses Claude to extract structured project data
from a natural language requirements document.
"""
import json
import logging
import uuid
from datetime import datetime

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

PARSE_PROMPT = """You are an expert network research analyst. Given a project requirements document,
extract structured data for sourcing experts.

Return a JSON object with exactly this structure:
{
  "title": "Project title",
  "description": "1-2 sentence project description",
  "industry": "Primary industry (e.g., Technology, Healthcare, Financial Services)",
  "categories": [
    {
      "name": "Category name (e.g., Systems Integrators, DB Product Leaders)",
      "description": "What kind of experts belong here",
      "search_criteria": {
        "titles": ["VP of Engineering", "CTO", ...],
        "seniorities": ["director", "vp", "c_suite"],
        "keywords": ["database", "migration", ...],
        "industries": ["technology", ...],
        "company_sizes": ["51,200", "201,500", "501,1000"],
        "locations": []
      }
    }
  ],
  "screener_questions": [
    {
      "question_text": "Which of the following best describes your relevant role?",
      "question_type": "multiple_choice",
      "options": ["CIO", "CTO", "VP of Engineering", "VP / Director of IT Infrastructure", "Other (please specify)"]
    },
    {
      "question_text": "For benchmarking purposes, can you please indicate the approximate annual revenue of the relevant organization?",
      "question_type": "multiple_choice",
      "options": ["Under $100M", "$100M - $500M", "$500M - $1B", "Over $1B"]
    }
  ],
  "ideal_profile": "Description of the ideal expert for scoring purposes"
}

Rules:
- Create 2-5 expert categories that make sense for the project
- Generate 5-10 screener questions that help qualify experts
- Screener questions should cover: role, industry, company size, relevant experience, decision-making authority, technology stack, and workload environment
- question_type must be one of: multiple_choice, free_text, yes_no, scale
- For multiple_choice, always include options
- Titles should be realistic job titles, not descriptions
- Make search criteria specific enough to find relevant people on Apollo/LinkedIn
"""


async def parse_requirements_document(document_text: str) -> dict:
    """Parse a requirements document into structured project data using Claude."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"Parse this project requirements document and extract structured data:\n\n---\n{document_text}\n---",
            }
        ],
        system=PARSE_PROMPT,
    )

    response_text = message.content[0].text

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    parsed = json.loads(response_text.strip())

    # Validate required fields
    assert "title" in parsed, "Missing title"
    assert "categories" in parsed, "Missing categories"
    assert "screener_questions" in parsed, "Missing screener_questions"

    logger.info(f"Parsed requirements: {parsed['title']} with {len(parsed['categories'])} categories and {len(parsed['screener_questions'])} screener questions")
    return parsed
