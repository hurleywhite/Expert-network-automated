import pytest

from app.services.validator import DraftValidator


def test_validator_ok_basic_facts():
    """Test that referencing only provided facts passes"""
    subject = "Quick question about your engineering work"
    body = """Hi John,

I hope this email finds you well. I'm reaching out because of your experience as Senior Engineer at Acme Corp.

I'm working on a consulting project and would value your perspective on some challenges we're tackling in this space.

Would you be open to a brief conversation?

Best regards"""

    facts_used = ["candidate.first_name", "candidate.title", "candidate.company"]
    provided_facts = {
        "candidate.first_name": "John",
        "candidate.title": "Senior Engineer",
        "candidate.company": "Acme Corp",
    }

    risk_flags = DraftValidator.validate(subject, body, facts_used, provided_facts)

    assert len(risk_flags) == 0, "Basic fact references should pass validation"


def test_validator_blocks_hallucinated_achievement():
    """Test that referencing non-existent achievements is flagged"""
    subject = "Congrats on your recent funding"
    body = """Hi Jane,

I saw the news about your recent Series B funding round - congratulations!

I'd love to discuss how we might work together.

Best regards"""

    facts_used = ["candidate.first_name"]
    provided_facts = {
        "candidate.first_name": "Jane",
        "candidate.company": "Startup Inc",
    }

    risk_flags = DraftValidator.validate(subject, body, facts_used, provided_facts)

    assert len(risk_flags) > 0, "Should flag mention of funding without supporting fact"
    assert any("recent" in flag.lower() for flag in risk_flags)


def test_validator_blocks_hallucinated_content():
    """Test that referencing non-existent posts/articles is flagged"""
    subject = "Loved your recent article"
    body = """Hi Alice,

I read your recent article on AI safety and found it fascinating.

Your insights on alignment really resonated with me.

Would you be open to a conversation about this?

Best regards"""

    facts_used = ["candidate.first_name"]
    provided_facts = {
        "candidate.first_name": "Alice",
        "candidate.title": "AI Researcher",
    }

    risk_flags = DraftValidator.validate(subject, body, facts_used, provided_facts)

    assert len(risk_flags) > 0, "Should flag mention of article without supporting fact"


def test_validator_blocks_hallucinated_event():
    """Test that referencing non-existent events/talks is flagged"""
    subject = "Following up from your NeurIPS keynote"
    body = """Hi Bob,

I loved your keynote at NeurIPS last month on transformer architectures.

Your explanation of attention mechanisms was brilliant.

Would you have time for a brief chat?

Best regards"""

    facts_used = ["candidate.first_name"]
    provided_facts = {
        "candidate.first_name": "Bob",
        "candidate.title": "ML Researcher",
    }

    risk_flags = DraftValidator.validate(subject, body, facts_used, provided_facts)

    assert len(risk_flags) > 0, "Should flag mention of keynote without supporting fact"


def test_validator_blocks_unused_facts():
    """Test that facts_used must be in provided_facts"""
    subject = "Quick question"
    body = """Hi there,

Just reaching out to connect.

Best regards"""

    facts_used = ["candidate.recent_paper", "candidate.award"]
    provided_facts = {
        "candidate.first_name": "Charlie",
        "candidate.title": "Professor",
    }

    risk_flags = DraftValidator.validate(subject, body, facts_used, provided_facts)

    assert len(risk_flags) >= 2, "Should flag facts_used that aren't in provided_facts"
    assert any("recent_paper" in flag for flag in risk_flags)
    assert any("award" in flag for flag in risk_flags)


def test_validator_is_safe_to_send():
    """Test the is_safe_to_send method"""
    assert DraftValidator.is_safe_to_send([]) is True
    assert DraftValidator.is_safe_to_send(["some_flag"]) is False
    assert DraftValidator.is_safe_to_send(["flag1", "flag2"]) is False
