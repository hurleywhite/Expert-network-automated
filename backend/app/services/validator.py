import re
from typing import Dict, List, Any


class DraftValidator:
    """Validates LLM-generated drafts for hallucination and fact-checking"""

    # Patterns that suggest specific claims requiring factual backing
    RISK_PATTERNS = [
        r"saw your (post|article|paper|blog)",
        r"read your",
        r"your recent (funding|hire|launch|acquisition|announcement|post|article)",
        r"congratulations on",
        r"I (noticed|saw) (that )?you",
        r"your (keynote|talk|presentation|speech) at",
        r"loved your",
        r"impressed by your",
        r"following your work on",
        r"your paper on",
        r"mentioned in (your )?",
    ]

    @staticmethod
    def validate(
        subject: str,
        body: str,
        facts_used: List[str],
        provided_facts: Dict[str, Any],
    ) -> List[str]:
        """
        Validate a draft against provided facts.

        Returns list of risk flags (empty if valid).
        """
        risk_flags = []

        # Check that all facts_used are actually provided
        for fact_key in facts_used:
            if fact_key not in provided_facts:
                risk_flags.append(f"fact_used '{fact_key}' not in provided facts")

        # Check for risk patterns in body
        body_lower = body.lower()
        for pattern in DraftValidator.RISK_PATTERNS:
            if re.search(pattern, body_lower):
                # Check if there's a corresponding fact
                if not DraftValidator._has_supporting_fact(pattern, facts_used, provided_facts):
                    risk_flags.append(
                        f"body contains '{pattern}' but no supporting fact found"
                    )

        # Check for specific entity mentions that aren't backed by facts
        risk_flags.extend(
            DraftValidator._check_specific_mentions(body, facts_used, provided_facts)
        )

        return risk_flags

    @staticmethod
    def _has_supporting_fact(
        pattern: str, facts_used: List[str], provided_facts: Dict[str, Any]
    ) -> bool:
        """Check if there's a fact that could support this pattern"""
        # Keywords that suggest deep, specific knowledge
        deep_knowledge_keywords = [
            "post",
            "article",
            "paper",
            "funding",
            "keynote",
            "talk",
            "presentation",
            "announcement",
        ]

        pattern_lower = pattern.lower()
        for keyword in deep_knowledge_keywords:
            if keyword in pattern_lower:
                # Check if any fact relates to this
                for fact_key in facts_used:
                    fact_value = str(provided_facts.get(fact_key, "")).lower()
                    if keyword in fact_value or keyword in fact_key.lower():
                        return True
                return False
        return True  # If no deep knowledge keyword, allow it

    @staticmethod
    def _check_specific_mentions(
        body: str, facts_used: List[str], provided_facts: Dict[str, Any]
    ) -> List[str]:
        """Check for specific mentions that need fact backing"""
        flags = []

        # Check for specific event/venue mentions
        event_patterns = [
            r"at (\w+) (conference|summit|event)",
            r"in your (.*?) (article|post|paper)",
        ]

        for pattern in event_patterns:
            matches = re.finditer(pattern, body, re.IGNORECASE)
            for match in matches:
                specific_mention = match.group(1)
                # Check if this specific thing is in facts
                found = False
                for fact_key in facts_used:
                    fact_value = str(provided_facts.get(fact_key, ""))
                    if specific_mention.lower() in fact_value.lower():
                        found = True
                        break
                if not found:
                    flags.append(
                        f"body mentions specific '{specific_mention}' but no supporting fact"
                    )

        return flags

    @staticmethod
    def is_safe_to_send(risk_flags: List[str]) -> bool:
        """Determine if a draft is safe to send based on risk flags"""
        return len(risk_flags) == 0
