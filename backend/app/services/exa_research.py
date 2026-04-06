"""
Exa AI Research Service — Deep web research on expert candidates.
Finds publications, talks, news mentions, and relevant content.
"""
import logging
from typing import Optional

from exa_py import Exa

from app.config import settings

logger = logging.getLogger(__name__)


def get_exa_client() -> Optional[Exa]:
    """Get Exa client if API key is configured."""
    if not settings.exa_api_key:
        logger.warning("EXA_API_KEY not set — Exa research will be skipped")
        return None
    return Exa(api_key=settings.exa_api_key)


async def research_expert(
    name: str,
    company: str,
    title: str,
    linkedin_url: Optional[str] = None,
) -> dict:
    """Research an expert using Exa AI to find publications, talks, and news."""
    client = get_exa_client()
    if not client:
        return {"status": "skipped", "reason": "No Exa API key configured"}

    results = {
        "publications": [],
        "talks_and_panels": [],
        "news_mentions": [],
        "company_news": [],
    }

    try:
        # Search for the person's publications and articles
        pub_query = f'"{name}" {company} article OR blog OR publication OR whitepaper'
        pub_results = client.search(
            pub_query,
            num_results=5,
            use_autoprompt=True,
            type="auto",
        )
        for r in pub_results.results:
            results["publications"].append({
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
                "snippet": getattr(r, "text", "")[:300] if hasattr(r, "text") else "",
            })
    except Exception as e:
        logger.warning(f"Exa publications search failed for {name}: {e}")

    try:
        # Search for conference talks and panel appearances
        talk_query = f'"{name}" conference OR panel OR keynote OR speaker OR webinar'
        talk_results = client.search(
            talk_query,
            num_results=5,
            use_autoprompt=True,
            type="auto",
        )
        for r in talk_results.results:
            results["talks_and_panels"].append({
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
            })
    except Exception as e:
        logger.warning(f"Exa talks search failed for {name}: {e}")

    try:
        # Search for news mentions
        news_query = f'"{name}" {company}'
        news_results = client.search(
            news_query,
            num_results=5,
            use_autoprompt=True,
            type="news",
        )
        for r in news_results.results:
            results["news_mentions"].append({
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
            })
    except Exception as e:
        logger.warning(f"Exa news search failed for {name}: {e}")

    try:
        # Company-specific news
        company_query = f"{company} database OR modernization OR migration OR technology"
        company_results = client.search(
            company_query,
            num_results=3,
            use_autoprompt=True,
            type="news",
        )
        for r in company_results.results:
            results["company_news"].append({
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
            })
    except Exception as e:
        logger.warning(f"Exa company news search failed for {company}: {e}")

    total_found = sum(len(v) for v in results.values())
    logger.info(f"Exa research for {name} at {company}: {total_found} results found")
    results["status"] = "completed"
    results["total_results"] = total_found
    return results
