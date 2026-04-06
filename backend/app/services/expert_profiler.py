"""
AI Expert Profiler — Generates rich GLG-style expert profiles using Claude.
Takes candidate data + Exa research + project requirements and produces
AI overview, project expertise bullets, screener responses, and relevance scoring.
"""
import json
import logging
from typing import Optional

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

PROFILE_PROMPT = """You are an expert network analyst creating a detailed expert profile.
Given candidate data, web research, and project requirements, generate a comprehensive profile.

Return a JSON object with this structure:
{
  "ai_overview": "2-3 paragraph summary of who this person is, their career trajectory, and why they are relevant to this project. Write in third person. Include specifics from their work history and any research findings. This should read like a GLG expert profile.",
  "project_expertise": [
    "Bullet point mapping their specific experience to project needs. Each bullet should start with a verb and reference concrete experience.",
    "Example: Stated experience as a leader in IT architecture, driving execution for a major transformation by migrating a legacy ERP to modern platforms.",
    "Example: Confirmed production experience with Microsoft SQL Server, Oracle Database, cloud-hosted databases, and PostgreSQL/MySQL/Aurora-class services.",
    "Example: Reported hands-on experience running at least one third-party COTS application on SQL Server or Oracle."
  ],
  "screener_responses": {
    "question_id_here": {
      "answer": "The answer text or selected option",
      "confidence": "high|medium|low",
      "reasoning": "Brief explanation of why this answer was inferred"
    }
  },
  "relevance_score": 85,
  "relevance_reasoning": "Why this score was assigned",
  "suggested_category": "Which project category this expert best fits",
  "work_experience": [
    {
      "date_range": "09/2025 - Present",
      "title": "FOUNDER AND PRINCIPAL CONSULTANT",
      "company": "Company Name, LLC",
      "is_current": true
    }
  ],
  "estimated_rate": 500
}

Rules:
- ai_overview should be 2-3 substantial paragraphs
- project_expertise should have 5-7 bullet points, each starting with an action verb like "Stated", "Confirmed", "Reported", "Noted", "Indicated"
- screener_responses should map each screener question ID to an inferred answer based on available data
- relevance_score is 0-100 based on how well they match the project requirements
- work_experience should be extracted from available data, sorted most recent first
- estimated_rate should be in USD per hour, based on seniority and market rates
- Do NOT fabricate facts — only use information from the provided data
- If you can't determine a screener answer, set confidence to "low"
"""


async def generate_expert_profile(
    candidate_data: dict,
    project_requirements: dict,
    exa_research: dict,
    screener_questions: list,
    categories: list,
) -> dict:
    """Generate a rich AI expert profile using Claude."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Build context for Claude
    context = f"""
## Candidate Data
- Name: {candidate_data.get('full_name', 'Unknown')}
- Current Title: {candidate_data.get('title', 'Unknown')}
- Company: {candidate_data.get('company', 'Unknown')}
- Location: {candidate_data.get('region', 'Unknown')}
- LinkedIn: {candidate_data.get('linkedin_url', 'N/A')}
- Headline: {candidate_data.get('headline', 'N/A')}
- Company Size: {candidate_data.get('company_employee_count', 'Unknown')} employees

## Project Requirements
- Title: {project_requirements.get('name', 'Unknown')}
- Industry: {project_requirements.get('industry', 'Unknown')}
- Description: {project_requirements.get('description', '')}
- Ideal Profile: {project_requirements.get('ideal_profile', '')}
- Target Titles: {', '.join(project_requirements.get('titles_include', []))}
- Keywords: {', '.join(project_requirements.get('keywords', []))}

## Expert Categories
{json.dumps([{"name": c.get("name"), "description": c.get("description")} for c in categories], indent=2)}

## Screener Questions
{json.dumps([{"id": str(q.get("id")), "question": q.get("question_text"), "type": q.get("question_type"), "options": q.get("options", [])} for q in screener_questions], indent=2)}

## Web Research (Exa AI)
{json.dumps(exa_research, indent=2) if exa_research.get("status") == "completed" else "No web research available."}

## Apollo Source Data
{json.dumps(candidate_data.get('source_payload', {}), indent=2) if candidate_data.get('source_payload') else "No additional source data."}
"""

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"Generate a comprehensive expert profile for this candidate:\n{context}",
            }
        ],
        system=PROFILE_PROMPT,
    )

    response_text = message.content[0].text

    # Extract JSON
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    profile = json.loads(response_text.strip())
    logger.info(f"Generated profile for {candidate_data.get('full_name')}: score={profile.get('relevance_score')}")
    return profile
