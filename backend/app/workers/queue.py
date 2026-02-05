import redis
from rq import Queue

from app.config import settings

# Initialize Redis connection
redis_conn = redis.from_url(settings.redis_url)

# Create queues
default_queue = Queue("default", connection=redis_conn)
