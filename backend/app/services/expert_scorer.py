"""
Confidence-based candidate scoring.

Instead of strict criteria matching, we score based on:
1. Data quality & completeness (do we have good info?)
2. Relevance confidence (how confident are we they're relevant?)
3. Reachability (can we actually contact them?)
4. Verification signals (is this a real person?)
"""
from typing import Dict, List, Tuple, Any, Optional


class ExpertScorer:
    """
    Score candidates based on confidence in data quality and relevance.

    Philosophy: We'd rather reach out to someone with verified info
    than skip them because their title doesn't match a rigid list.
    """

    @classmethod
    def score_candidate(
        cls,
        candidate: Dict[str, Any],
        project: Dict[str, Any],
    ) -> Tuple[bool, float, List[str], Dict[str, Any]]:
        """
        Score a candidate based on confidence we have good data.

        Returns: (hard_pass, score, reasons, scoring_details)

        Score ranges from 0-100:
        - 80-100: High confidence - verified data, clear relevance
        - 60-79: Good confidence - most data present, likely relevant
        - 40-59: Moderate confidence - some gaps but worth trying
        - 20-39: Low confidence - missing key data
        - 0-19: Very low confidence or hard pass
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
        titles_include = [t.lower() for t in project.get("titles_include", [])]
        titles_exclude = [t.lower() for t in project.get("titles_exclude", [])]
        exclusions = [e.lower() for e in project.get("exclusions", [])]
        keywords = [k.lower() for k in project.get("keywords", [])]
        company_size_min = project.get("company_size_min")

        # ============ HARD PASS CHECKS (only explicit exclusions) ============
        hard_pass = False
        title_lower = title.lower()
        company_lower = company.lower()

        for excluded in titles_exclude:
            if excluded and excluded in title_lower:
                hard_pass = True
                reasons.append(f"EXCLUDE: title contains '{excluded}'")

        for exclusion in exclusions:
            if exclusion and exclusion in company_lower:
                hard_pass = True
                reasons.append(f"EXCLUDE: company matches '{exclusion}'")

        if hard_pass:
            return (True, 0.0, reasons, {"hard_pass_reason": reasons})

        # ============ CONFIDENCE-BASED SCORING ============

        # 1. DATA COMPLETENESS (0-30 points)
        completeness_score, completeness_reasons = cls._score_data_completeness(
            full_name, title, company, email, linkedin_url, region
        )
        scores["data_completeness"] = completeness_score
        reasons.extend(completeness_reasons)

        # 2. REACHABILITY (0-25 points)
        reachability_score, reachability_reasons = cls._score_reachability(
            email, linkedin_url
        )
        scores["reachability"] = reachability_score
        reasons.extend(reachability_reasons)

        # 3. RELEVANCE CONFIDENCE (0-45 points) - includes title match
        relevance_score, relevance_reasons = cls._score_relevance_confidence(
            title, company, keywords, titles_include
        )
        scores["relevance"] = relevance_score
        reasons.extend(relevance_reasons)

        # 4. COMPANY SIGNALS (0-15 points)
        company_score, company_reasons = cls._score_company_signals(
            company, company_size, company_size_min
        )
        scores["company"] = company_score
        reasons.extend(company_reasons)

        # Calculate total
        total_score = sum(scores.values())

        scoring_details = {
            "component_scores": scores,
            "total": total_score,
            "recommendation": cls._get_recommendation(total_score),
            "confidence_level": cls._get_confidence_level(total_score),
        }

        return (False, total_score, reasons, scoring_details)

    @classmethod
    def _score_data_completeness(
        cls,
        full_name: str,
        title: str,
        company: str,
        email: str,
        linkedin_url: str,
        region: str,
    ) -> Tuple[float, List[str]]:
        """Score based on how complete the candidate data is."""
        reasons = []
        score = 0.0

        # Name (required - 5 points)
        if full_name and len(full_name.split()) >= 2:
            score += 5
            reasons.append("name: full name present (5pts)")
        elif full_name:
            score += 2
            reasons.append("name: partial name (2pts)")
        else:
            reasons.append("name: missing (0pts)")

        # Title (important - 8 points)
        if title and len(title) > 3:
            score += 8
            reasons.append("title: present (8pts)")
        else:
            reasons.append("title: missing (0pts)")

        # Company (important - 8 points)
        if company and len(company) > 2:
            score += 8
            reasons.append("company: present (8pts)")
        else:
            reasons.append("company: missing (0pts)")

        # Email (critical - 5 points, scored separately in reachability)
        # LinkedIn (valuable - 4 points)
        if linkedin_url:
            score += 4
            reasons.append("linkedin: present (4pts)")

        # Region (nice to have - 5 points)
        if region:
            score += 5
            reasons.append("region: present (5pts)")

        return (score, reasons)

    @classmethod
    def _score_reachability(
        cls, email: str, linkedin_url: str
    ) -> Tuple[float, List[str]]:
        """Score based on how confident we are we can reach them."""
        reasons = []
        score = 0.0

        # Email is critical
        if email:
            # Check email quality
            if "@" in email and "." in email.split("@")[-1]:
                # Looks like valid email format
                if cls._is_business_email(email):
                    score += 20
                    reasons.append("email: business email (20pts)")
                else:
                    score += 12
                    reasons.append("email: personal email (12pts)")
            else:
                score += 5
                reasons.append("email: questionable format (5pts)")
        else:
            reasons.append("email: missing (0pts)")

        # LinkedIn as backup contact
        if linkedin_url and "linkedin.com" in linkedin_url.lower():
            score += 5
            reasons.append("linkedin: valid URL (5pts)")

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
    def _score_relevance_confidence(
        cls, title: str, company: str, keywords: List[str], titles_include: List[str]
    ) -> Tuple[float, List[str]]:
        """
        Score how confident we are the person is relevant.

        Scores based on:
        - Title match against target titles (most important!)
        - Keyword overlap in title/company
        - Having a substantive role
        """
        reasons = []
        score = 0.0
        title_lower = title.lower()
        company_lower = company.lower()
        combined = f"{title_lower} {company_lower}"

        # TITLE MATCH (up to 25 points) - most important for relevance!
        if titles_include:
            title_matched = False
            for target_title in titles_include:
                # Check if target title appears in candidate's title
                if target_title in title_lower:
                    score += 25
                    reasons.append(f"title_match: '{target_title}' matches (25pts)")
                    title_matched = True
                    break
                # Also check if main words overlap (e.g., "CCO" matches "Chief Commercial Officer")
                target_words = set(target_title.split())
                title_words = set(title_lower.split())
                overlap = target_words & title_words
                if len(overlap) >= 2 or (len(overlap) >= 1 and len(target_words) == 1):
                    score += 20
                    reasons.append(f"title_match: partial match '{' '.join(overlap)}' (20pts)")
                    title_matched = True
                    break

            if not title_matched:
                reasons.append("title_match: no match to target titles (0pts)")

        # Keyword matches (up to 15 points) - check individual words too
        if keywords:
            keyword_matches = []
            for k in keywords:
                # Check full phrase
                if k in combined:
                    keyword_matches.append(k)
                else:
                    # Check individual words in keyword phrase
                    keyword_words = k.split()
                    for kw in keyword_words:
                        if len(kw) > 3 and kw in combined:
                            keyword_matches.append(kw)
                            break

            if keyword_matches:
                unique_matches = list(set(keyword_matches))
                match_score = min(15, len(unique_matches) * 5)
                score += match_score
                reasons.append(f"keywords: {len(unique_matches)} matches ({match_score}pts)")
            else:
                reasons.append("keywords: no match (0pts)")
        else:
            score += 10
            reasons.append("keywords: none specified (10pts)")

        # Title substance check (up to 5 points)
        if title:
            substantive_indicators = [
                "director", "manager", "head", "lead", "chief", "vp",
                "president", "founder", "owner", "cco", "cro", "cmo",
                "specialist", "senior", "principal", "executive", "officer"
            ]
            if any(ind in title_lower for ind in substantive_indicators):
                score += 5
                reasons.append("title_substance: senior role (5pts)")

        return (score, reasons)

    @classmethod
    def _score_company_signals(
        cls,
        company: str,
        company_size: Optional[int],
        company_size_min: Optional[int],
    ) -> Tuple[float, List[str]]:
        """Score based on company signals."""
        reasons = []
        score = 0.0

        # Company exists
        if company:
            score += 5
            reasons.append("company: identified (5pts)")

        # Company size
        if company_size_min:
            if company_size and company_size >= company_size_min:
                score += 10
                reasons.append(f"company_size: {company_size} meets minimum (10pts)")
            elif company_size:
                # Below minimum but we have data
                ratio = company_size / company_size_min
                partial = int(5 * ratio)
                score += partial
                reasons.append(f"company_size: {company_size} below minimum ({partial}pts)")
            else:
                # Unknown size - give partial credit
                score += 5
                reasons.append("company_size: unknown (5pts)")
        else:
            # No size requirement
            score += 5
            reasons.append("company_size: no requirement (5pts)")

        return (score, reasons)

    @classmethod
    def _get_recommendation(cls, score: float) -> str:
        """Get outreach recommendation based on confidence score."""
        if score >= 80:
            return "HIGH CONFIDENCE - Verified data, reach out"
        elif score >= 60:
            return "GOOD CONFIDENCE - Data looks solid, include in outreach"
        elif score >= 40:
            return "MODERATE CONFIDENCE - Some gaps, but worth trying"
        elif score >= 20:
            return "LOW CONFIDENCE - Missing key data, review manually"
        else:
            return "VERY LOW CONFIDENCE - Likely missing critical data"

    @classmethod
    def _get_confidence_level(cls, score: float) -> str:
        """Get simple confidence level label."""
        if score >= 80:
            return "high"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "moderate"
        elif score >= 20:
            return "low"
        else:
            return "very_low"
