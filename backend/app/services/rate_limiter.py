import time
import random

from app.config import settings
from app.workers.queue import redis_conn


class RateLimiter:
    """Redis-based rate limiting service for email sending."""

    @staticmethod
    def get_domain_from_email(email: str) -> str:
        """Extract domain from email address."""
        return email.split('@')[-1].lower()

    @staticmethod
    def can_send_to_domain(domain: str) -> bool:
        """Check if sending to domain is within rate limit."""
        key = f"rate_limit:domain:{domain}:hour"
        count = redis_conn.get(key)
        current_count = int(count) if count else 0
        return current_count < settings.rate_limit_per_domain_per_hour

    @staticmethod
    def increment_domain_count(domain: str):
        """Increment domain send counter with automatic expiry."""
        key = f"rate_limit:domain:{domain}:hour"
        redis_conn.incr(key)
        # Set expiry only if not already set
        if redis_conn.ttl(key) == -1:
            redis_conn.expire(key, 3600)

    @staticmethod
    def apply_jitter_delay():
        """Apply random jitter delay before sending."""
        delay = random.randint(
            settings.rate_limit_jitter_min_seconds,
            settings.rate_limit_jitter_max_seconds
        )
        time.sleep(delay)
