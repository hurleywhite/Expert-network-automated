"""
LLM-enhanced candidate scoring.

Combines:
1. LLM-based relevance evaluation (semantic understanding of fit)
2. Rule-based data quality checks (email, name, reachability)

The LLM evaluates whether the candidate's role/company makes them
a good expert for the project. Rule-based checks ensure we can
actually reach them.
"""
from typing import Dict, List, Tuple, Any, Optional

from app.services.llm import LLMService


class ExpertScorer:
    """
    Score candidates using LLM for relevance and rules for data quality.

    Philosophy: Use AI to understand semantic fit, but verify
    we have the data needed to actually reach out.
    """

    _llm_service: Optional[LLMService] = None

    @classmethod
    def _get_llm(cls) -> LLMService:
        """Lazy-load LLM service"""
        if cls._llm_service is None:
            cls._llm_service = LLMService()
        return cls._llm_service

    @classmethod
    def score_candidate(
        cls,
        candidate: Dict[str, Any],
        project: Dict[str, Any],
    ) -> Tuple[bool, float, List[str], Dict[str, Any]]:
        """
        Score a candidate using LLM for relevance + rules for data quality.

        Returns: (hard_pass, score, reasons, scoring_details)

        Score ranges from 0-100:
        - 85-100: Priority - excellent fit, verified data
        - 70-84: Include - good fit, solid data
        - 50-69: Review - moderate fit or data gaps
        - 30-49: Weak - poor fit or missing data
        - 0-29: Skip - not relevant or unreachable
        """
        reasons = []
        scores = {}

        # Extract candidate info
        title = candidate.get("title") or ""
        company = candidate.get("company") or ""
        email = candidate.get("email") or ""
        linkedin_url = candidate.get("linkedin_url") or ""
        company_size = candidate.get("company_employee_count")
        region = candidate.get("region") or ""
        full_name = candidate.get("full_name") or ""

        # Extract project criteria
        titles_exclude = [t.lower() for t in project.get("titles_exclude", [])]
        exclusions = [e.lower() for e in project.get("exclusions", [])]

        # ============ HARD PASS CHECKS ============
        hard_pass = False
        title_lower = title.lower()
        company_lower = company.lower()

        # Check title exclusions
        for excluded in titles_exclude:
            if excluded and excluded in title_lower:
                hard_pass = True
                reasons.append(f"EXCLUDE: title contains '{excluded}'")

        # Check company exclusions
        for exclusion in exclusions:
            if exclusion and exclusion in company_lower:
                hard_pass = True
                reasons.append(f"EXCLUDE: company matches '{exclusion}'")

        # Check geographic requirements - if project specifies regions, candidate must match
        target_regions = project.get("regions", [])
        if target_regions and region:
            if not cls._matches_target_region(region, target_regions):
                hard_pass = True
                reasons.append(f"EXCLUDE: location '{region}' outside target regions {target_regions}")
        elif target_regions and not region:
            # Project requires specific region but candidate has no location data
            hard_pass = True
            reasons.append(f"EXCLUDE: no location data, project requires {target_regions}")

        if hard_pass:
            return (True, 0.0, reasons, {"hard_pass_reason": reasons})

        # ============ LLM-BASED RELEVANCE SCORING (0-60 points) ============
        llm = cls._get_llm()
        llm_result = llm.score_candidate(candidate, project)

        # Scale LLM score (0-100) to 0-60 points
        llm_relevance_score = llm_result.get("relevance_score", 50)
        relevance_points = int(llm_relevance_score * 0.6)
        scores["llm_relevance"] = relevance_points

        # Add LLM reasoning
        llm_reasoning = llm_result.get("reasoning", [])
        title_match = llm_result.get("title_match_quality", "unknown")
        confidence = llm_result.get("confidence", "medium")

        reasons.append(f"LLM relevance: {llm_relevance_score}/100 → {relevance_points}pts ({confidence} confidence)")
        reasons.append(f"Title match: {title_match}")

        for signal in llm_result.get("expertise_signals", [])[:2]:
            reasons.append(f"Expertise: {signal}")

        for concern in llm_result.get("concerns", [])[:1]:
            reasons.append(f"Concern: {concern}")

        # ============ RULE-BASED DATA QUALITY (0-25 points) ============
        data_score, data_reasons = cls._score_data_quality(
            full_name, title, company, linkedin_url, region
        )
        scores["data_quality"] = data_score
        reasons.extend(data_reasons)

        # ============ REACHABILITY (0-15 points) ============
        reach_score, reach_reasons = cls._score_reachability(email, linkedin_url)
        scores["reachability"] = reach_score
        reasons.extend(reach_reasons)

        # ============ CALCULATE FINAL SCORE ============
        total_score = min(100, sum(scores.values()))  # Cap at 100

        # Get recommendation from LLM result or derive from score
        llm_recommendation = llm_result.get("recommendation", "review")

        scoring_details = {
            "component_scores": scores,
            "total": total_score,
            "llm_evaluation": {
                "relevance_score": llm_relevance_score,
                "confidence": confidence,
                "title_match": title_match,
                "expertise_signals": llm_result.get("expertise_signals", []),
                "concerns": llm_result.get("concerns", []),
            },
            "recommendation": cls._get_recommendation(total_score, llm_recommendation),
            "confidence_level": cls._get_confidence_level(total_score),
        }

        return (False, total_score, reasons, scoring_details)

    @classmethod
    def _score_data_quality(
        cls,
        full_name: str,
        title: str,
        company: str,
        linkedin_url: str,
        region: str,
    ) -> Tuple[float, List[str]]:
        """Score based on how complete the candidate data is."""
        reasons = []
        score = 0.0

        # Full name (7 points)
        if full_name and len(full_name.split()) >= 2:
            score += 7
            reasons.append("Data: full name present (+7)")
        elif full_name:
            score += 3
            reasons.append("Data: partial name (+3)")

        # Title present (6 points)
        if title and len(title) > 3:
            score += 6
            reasons.append("Data: title present (+6)")

        # Company present (6 points)
        if company and len(company) > 2:
            score += 6
            reasons.append("Data: company present (+6)")

        # LinkedIn (3 points)
        if linkedin_url and "linkedin.com" in linkedin_url.lower():
            score += 3
            reasons.append("Data: LinkedIn present (+3)")

        # Region (3 points)
        if region:
            score += 3
            reasons.append("Data: region present (+3)")

        return (score, reasons)

    @classmethod
    def _score_reachability(
        cls, email: str, linkedin_url: str
    ) -> Tuple[float, List[str]]:
        """Score based on how confident we are we can reach them."""
        reasons = []
        score = 0.0

        if email and "@" in email and "." in email.split("@")[-1]:
            if cls._is_business_email(email):
                score += 12
                reasons.append("Reach: business email (+12)")
            else:
                score += 8
                reasons.append("Reach: personal email (+8)")
        elif email:
            score += 4
            reasons.append("Reach: questionable email (+4)")
        else:
            reasons.append("Reach: no email (0)")

        # LinkedIn as backup
        if linkedin_url and "linkedin.com" in linkedin_url.lower():
            score += 3
            reasons.append("Reach: LinkedIn backup (+3)")

        return (score, reasons)

    @classmethod
    def _is_business_email(cls, email: str) -> bool:
        """Check if email appears to be a business email."""
        personal_domains = [
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "aol.com", "icloud.com", "mail.com", "protonmail.com"
        ]
        domain = email.lower().split("@")[-1]
        return domain not in personal_domains

    @classmethod
    def _matches_target_region(cls, candidate_region: str, target_regions: List[str]) -> bool:
        """
        Check if candidate's region matches any of the target regions.

        Uses strict word-boundary matching to avoid false positives like
        "Manhattan" matching "Malaysia" via the "ma" abbreviation.
        """
        if not candidate_region or not target_regions:
            return False

        candidate_lower = candidate_region.lower()
        # Extract words from candidate region for word-boundary matching
        candidate_words = set(candidate_lower.replace(",", " ").replace(".", " ").split())

        # Define specific keywords that uniquely identify each region
        # Avoid common words like "new" that appear in multiple places
        nyc_specific = {"york", "nyc", "manhattan", "brooklyn", "queens", "bronx"}
        sf_specific = {"francisco", "sf"}
        la_specific = {"angeles"}
        chicago_specific = {"chicago"}
        boston_specific = {"boston"}
        seattle_specific = {"seattle"}
        dc_specific = {"columbia", "district"}

        for target in target_regions:
            target_lower = target.lower().strip()
            target_words = set(target_lower.replace(",", " ").replace(".", " ").split())

            # Direct word match - if ALL target words appear as whole words in candidate
            if target_words and target_words.issubset(candidate_words):
                return True

            # Check if target phrase appears in candidate (for multi-word names)
            if len(target_lower) > 4 and target_lower in candidate_lower:
                return True

            # For NYC targets, check if candidate has NYC-specific keywords
            # "york" is specific enough to not match "New Delhi"
            if target_words & nyc_specific or ("new" in target_words and "york" in target_words):
                if candidate_words & nyc_specific or ("new" in candidate_words and "york" in candidate_words):
                    return True

            # Similarly for other regions - use specific keywords
            if target_words & sf_specific:
                if candidate_words & sf_specific or "california" in candidate_words:
                    return True

            if target_words & la_specific:
                if candidate_words & la_specific or ("los" in candidate_words and "angeles" in candidate_words):
                    return True

            if target_words & chicago_specific:
                if candidate_words & chicago_specific or "illinois" in candidate_words:
                    return True

            if target_words & boston_specific:
                if candidate_words & boston_specific or "massachusetts" in candidate_words:
                    return True

            if target_words & seattle_specific:
                if candidate_words & seattle_specific or "washington" in candidate_words:
                    return True

            if target_words & dc_specific or ("washington" in target_words and "dc" in target_words):
                if candidate_words & dc_specific or ("washington" in candidate_words and "dc" in candidate_words):
                    return True

        return False

    @classmethod
    def _get_recommendation(cls, score: float, llm_rec: str) -> str:
        """Get outreach recommendation combining score and LLM advice."""
        if score >= 85:
            return "PRIORITY - Excellent fit, reach out first"
        elif score >= 70:
            return "INCLUDE - Good fit, add to outreach"
        elif score >= 50:
            return "REVIEW - Moderate fit, check manually"
        elif score >= 30:
            return "WEAK - Poor fit or missing data"
        else:
            return "SKIP - Not relevant or unreachable"

    @classmethod
    def _get_confidence_level(cls, score: float) -> str:
        """Get simple confidence level label."""
        if score >= 85:
            return "high"
        elif score >= 70:
            return "good"
        elif score >= 50:
            return "moderate"
        elif score >= 30:
            return "low"
        else:
            return "very_low"
