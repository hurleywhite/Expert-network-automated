#!/usr/bin/env python
"""
RQ Worker entry point.

Run with: python worker.py
"""
import sys
from rq import Worker

from app.workers.queue import redis_conn, default_queue

if __name__ == "__main__":
    worker = Worker([default_queue], connection=redis_conn)
    print(f"Starting RQ worker for queue: {default_queue.name}")
    worker.work()
