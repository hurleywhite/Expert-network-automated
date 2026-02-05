"""
Expert network-style candidate scoring.

Mimics how GLG/AlphaSights/Third Bridge evaluate expert relevance:
- Title/role match
- Domain expertise signals
- Seniority appropriateness
- Company relevance
- Recency/currency of experience
"""
from typing import Dict, List, Tuple, Any, Optional
import re


class ExpertScorer:
    """
    Score candidates like an expert network would.

    Scoring philosophy:
    - We're looking for EXPERTS who can provide insights, not just people with titles
    - Seniority matters: too junior = no strategic insight, too senior = may be out of touch
    - Domain expertise matters more than exact title match
    - Company relevance: industry match, company size, market position
    """

    # Seniority levels and their typical scoring weight
    SENIORITY_TIERS = {
        "c_level": {
            "patterns": ["ceo", "cfo", "coo", "cto", "cio", "cmo", "chief"],
            "weight": 0.9,  # Very senior, great for strategy, may be too high-level for ops
        },
        "vp": {
            "patterns": ["vp ", "vice president", "svp", "evp"],
            "weight": 1.0,  # Ideal: strategic + operational knowledge
        },
        "director": {
            "patterns": ["director", "head of"],
            "weight": 1.0,  # Ideal: deep domain expertise
        },
        "senior_manager": {
            "patterns": ["senior manager", "sr manager", "sr. manager"],
            "weight": 0.9,
        },
        "manager": {
            "patterns": ["manager"],
            "weight": 0.7,  # Good for operational insights
        },
        "specialist": {
            "patterns": ["specialist", "analyst", "coordinator", "associate"],
            "weight": 0.5,  # May lack strategic perspective
        },
    }

    @classmethod
    def score_candidate(
        cls,
        candidate: Dict[str, Any],
        project: Dict[str, Any],
    ) -> Tuple[bool, float, List[str], Dict[str, Any]]:
        """
        Score a candidate's relevance as an expert.

        Returns: (hard_pass, score, reasons, scoring_details)

        Score ranges from 0-100:
        - 80-100: Excellent match, prioritize outreach
        - 60-79: Good match, include in outreach
        - 40-59: Moderate match, include if list is short
        - 20-39: Weak match, probably skip
        - 0-19: Poor match or hard pass
        """
        reasons = []
        scoring_details = {}

        # Extract candidate info
        title = (candidate.get("title") or "").lower()
        company = (candidate.get("company") or "").lower()
        region = candidate.get("region") or ""
        company_size = candidate.get("company_employee_count")
        linkedin_url = candidate.get("linkedin_url") or ""

        # Extract project criteria
        titles_include = [t.lower() for t in project.get("titles_include", [])]
        titles_exclude = [t.lower() for t in project.get("titles_exclude", [])]
        keywords = [k.lower() for k in project.get("keywords", [])]
        exclusions = [e.lower() for e in project.get("exclusions", [])]
        regions = project.get("regions", [])
        company_size_min = project.get("company_size_min")
        seniority_signals = [s.lower() for s in project.get("seniority_signals", [])]
        expertise_signals = [s.lower() for s in project.get("expertise_signals", [])]

        # ============ HARD PASS CHECKS ============
        hard_pass = False

        # Check title exclusions
        for excluded in titles_exclude:
            if excluded in title:
                hard_pass = True
                reasons.append(f"EXCLUDE: title contains '{excluded}'")

        # Check company exclusions
        for exclusion in exclusions:
            if exclusion in company:
                hard_pass = True
                reasons.append(f"EXCLUDE: company contains '{exclusion}'")

        if hard_pass:
            return (True, 0.0, reasons, {"hard_pass_reason": reasons})

        # ============ SCORING ============
        scores = {}

        # 1. TITLE RELEVANCE (0-35 points)
        title_score, title_reasons = cls._score_title_relevance(
            title, titles_include, keywords
        )
        scores["title_relevance"] = title_score
        reasons.extend(title_reasons)

        # 2. SENIORITY APPROPRIATENESS (0-20 points)
        seniority_score, seniority_reasons = cls._score_seniority(
            title, seniority_signals
        )
        scores["seniority"] = seniority_score
        reasons.extend(seniority_reasons)

        # 3. DOMAIN EXPERTISE (0-25 points)
        expertise_score, expertise_reasons = cls._score_expertise(
            title, company, keywords, expertise_signals
        )
        scores["domain_expertise"] = expertise_score
        reasons.extend(expertise_reasons)

        # 4. COMPANY FIT (0-15 points)
        company_score, company_reasons = cls._score_company_fit(
            company, company_size, company_size_min, keywords
        )
        scores["company_fit"] = company_score
        reasons.extend(company_reasons)

        # 5. REGION MATCH (0-5 points)
        region_score, region_reasons = cls._score_region(region, regions)
        scores["region"] = region_score
        reasons.extend(region_reasons)

        # Calculate total
        total_score = sum(scores.values())

        # Add scoring details for transparency
        scoring_details = {
            "component_scores": scores,
            "total": total_score,
            "recommendation": cls._get_recommendation(total_score),
        }

        return (False, total_score, reasons, scoring_details)

    @classmethod
    def _score_title_relevance(
        cls, title: str, titles_include: List[str], keywords: List[str]
    ) -> Tuple[float, List[str]]:
        """Score how well the title matches what we're looking for."""
        reasons = []
        score = 0.0

        # Direct title match (up to 25 points)
        best_match = None
        best_match_score = 0

        for target_title in titles_include:
            if target_title in title:
                # Exact substring match
                match_score = 25
                if match_score > best_match_score:
                    best_match = target_title
                    best_match_score = match_score
            elif cls._fuzzy_title_match(title, target_title):
                # Fuzzy match
                match_score = 15
                if match_score > best_match_score:
                    best_match = target_title
                    best_match_score = match_score

        if best_match:
            score += best_match_score
            reasons.append(f"title_match: '{best_match}' ({best_match_score}pts)")
        else:
            reasons.append("title: no direct match")

        # Keyword presence in title (up to 10 points)
        keyword_matches = [k for k in keywords if k in title]
        if keyword_matches:
            keyword_score = min(10, len(keyword_matches) * 5)
            score += keyword_score
            reasons.append(f"title_keywords: {keyword_matches} ({keyword_score}pts)")

        return (score, reasons)

    @classmethod
    def _fuzzy_title_match(cls, actual: str, target: str) -> bool:
        """Check for fuzzy title matches (handles variations)."""
        # Common title variations
        variations = {
            "administrator": ["admin", "administrator"],
            "manager": ["manager", "mgr"],
            "director": ["director", "dir"],
            "specialist": ["specialist", "spec"],
            "analyst": ["analyst"],
            "coordinator": ["coordinator", "coord"],
            "vice president": ["vp", "vice president"],
        }

        for base, variants in variations.items():
            if any(v in target for v in variants):
                if any(v in actual for v in variants):
                    return True

        # Check word overlap
        target_words = set(target.split())
        actual_words = set(actual.split())
        overlap = target_words & actual_words

        return len(overlap) >= 2

    @classmethod
    def _score_seniority(
        cls, title: str, seniority_signals: List[str]
    ) -> Tuple[float, List[str]]:
        """Score seniority appropriateness."""
        reasons = []

        # Detect seniority tier
        detected_tier = None
        for tier_name, tier_info in cls.SENIORITY_TIERS.items():
            for pattern in tier_info["patterns"]:
                if pattern in title:
                    detected_tier = tier_name
                    break
            if detected_tier:
                break

        if detected_tier:
            weight = cls.SENIORITY_TIERS[detected_tier]["weight"]
            score = 20 * weight
            reasons.append(f"seniority: {detected_tier} ({score:.0f}pts)")
        else:
            # Unknown seniority, give partial credit
            score = 10
            reasons.append("seniority: unknown (10pts)")

        return (score, reasons)

    @classmethod
    def _score_expertise(
        cls,
        title: str,
        company: str,
        keywords: List[str],
        expertise_signals: List[str],
    ) -> Tuple[float, List[str]]:
        """Score domain expertise signals."""
        reasons = []
        score = 0.0
        combined = f"{title} {company}"

        # Keyword matches (up to 15 points)
        keyword_matches = [k for k in keywords if k in combined]
        if keyword_matches:
            keyword_score = min(15, len(keyword_matches) * 5)
            score += keyword_score
            reasons.append(f"expertise_keywords: {keyword_matches} ({keyword_score}pts)")

        # Expertise signal matches (up to 10 points)
        signal_matches = [s for s in expertise_signals if s in combined]
        if signal_matches:
            signal_score = min(10, len(signal_matches) * 5)
            score += signal_score
            reasons.append(f"expertise_signals: {signal_matches} ({signal_score}pts)")

        if not keyword_matches and not signal_matches:
            reasons.append("expertise: no keyword/signal matches")

        return (score, reasons)

    @classmethod
    def _score_company_fit(
        cls,
        company: str,
        company_size: Optional[int],
        company_size_min: Optional[int],
        keywords: List[str],
    ) -> Tuple[float, List[str]]:
        """Score company relevance."""
        reasons = []
        score = 0.0

        # Company size check (up to 10 points)
        if company_size_min:
            if company_size and company_size >= company_size_min:
                score += 10
                reasons.append(f"company_size: {company_size} >= {company_size_min} (10pts)")
            elif company_size:
                reasons.append(f"company_size: {company_size} < {company_size_min} (0pts)")
            else:
                score += 5  # Unknown size, give partial credit
                reasons.append("company_size: unknown (5pts)")
        else:
            score += 5

        # Company name contains keywords (up to 5 points)
        company_keyword_matches = [k for k in keywords if k in company]
        if company_keyword_matches:
            score += 5
            reasons.append(f"company_keywords: {company_keyword_matches} (5pts)")

        return (score, reasons)

    @classmethod
    def _score_region(
        cls, region: str, required_regions: List[str]
    ) -> Tuple[float, List[str]]:
        """Score region match."""
        if not required_regions:
            return (5, ["region: no requirement (5pts)"])

        if region in required_regions:
            return (5, [f"region: {region} matches (5pts)"])

        return (0, [f"region: {region} not in {required_regions} (0pts)"])

    @classmethod
    def _get_recommendation(cls, score: float) -> str:
        """Get outreach recommendation based on score."""
        if score >= 80:
            return "PRIORITY - Excellent match, prioritize outreach"
        elif score >= 60:
            return "INCLUDE - Good match, include in outreach"
        elif score >= 40:
            return "MAYBE - Moderate match, include if list is short"
        elif score >= 20:
            return "WEAK - Poor match, probably skip"
        else:
            return "SKIP - Not a match"
