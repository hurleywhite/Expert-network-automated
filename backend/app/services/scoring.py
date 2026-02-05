from typing import Dict, List, Tuple, Any


class ScoringService:
    """Service for scoring candidates against project criteria"""

    @staticmethod
    def score_candidate(
        candidate: Dict[str, Any],
        project: Dict[str, Any],
    ) -> Tuple[bool, float, List[str]]:
        """
        Score a candidate against project criteria.

        Returns: (hard_pass, score, reasons)
        """
        reasons = []
        hard_pass = False
        score = 0.0

        # Extract criteria
        titles_include = project.get("titles_include", [])
        titles_exclude = project.get("titles_exclude", [])
        regions = project.get("regions", [])
        company_size_min = project.get("company_size_min")
        keywords = project.get("keywords", [])
        exclusions = project.get("exclusions", [])

        candidate_title = (candidate.get("title") or "").lower()
        candidate_company = (candidate.get("company") or "").lower()
        candidate_region = candidate.get("region") or ""
        candidate_company_size = candidate.get("company_employee_count")

        # HARD PASS FILTERS
        # Title exclusions
        if titles_exclude:
            for excluded in titles_exclude:
                if excluded.lower() in candidate_title:
                    hard_pass = True
                    reasons.append(f"excluded_title:{excluded}")

        # Exclusions (company keywords)
        if exclusions:
            for exclusion in exclusions:
                if exclusion.lower() in candidate_company:
                    hard_pass = True
                    reasons.append(f"excluded_company:{exclusion}")

        # If hard pass, return early
        if hard_pass:
            return (True, 0.0, reasons)

        # SCORING
        # Title match (40 points)
        if titles_include:
            title_match = False
            for required_title in titles_include:
                if required_title.lower() in candidate_title:
                    title_match = True
                    score += 40
                    reasons.append(f"title_match:{required_title}")
                    break
            if not title_match:
                reasons.append("title_no_match")
        else:
            # If no title requirements, give partial credit
            score += 20

        # Region match (20 points)
        if regions:
            if candidate_region in regions:
                score += 20
                reasons.append(f"region_match:{candidate_region}")
            else:
                reasons.append("region_no_match")
        else:
            score += 10

        # Company size (10 points)
        if company_size_min and candidate_company_size:
            if candidate_company_size >= company_size_min:
                score += 10
                reasons.append("company_size_ok")
            else:
                reasons.append("company_size_too_small")
        else:
            score += 5

        # Keywords match (30 points total, divided among matches)
        if keywords:
            keyword_matches = []
            combined_text = f"{candidate_title} {candidate_company}".lower()
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    keyword_matches.append(keyword)

            if keyword_matches:
                keyword_score = min(30, len(keyword_matches) * 10)
                score += keyword_score
                reasons.append(f"keywords_match:{','.join(keyword_matches)}")
            else:
                reasons.append("keywords_no_match")
        else:
            score += 15

        return (False, score, reasons)
