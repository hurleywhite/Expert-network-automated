from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rq import Worker
from rq.job import Job
from rq.registry import FailedJobRegistry, FinishedJobRegistry

from app.deps import verify_api_key
from app.routers import projects, candidates, drafts, webhooks, sourcing, interviews
from app.workers.queue import redis_conn, default_queue

app = FastAPI(
    title="Expert Outreach API",
    description="Production-grade expert outreach system with LLM drafting and anti-hallucination guardrails",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router)
app.include_router(candidates.router)
app.include_router(drafts.router)
app.include_router(webhooks.router)
app.include_router(sourcing.router)
app.include_router(interviews.router, prefix="/interviews", tags=["interviews"])


@app.get("/")
def root():
    return {
        "service": "Expert Outreach API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/admin/workers", dependencies=[Depends(verify_api_key)])
def get_worker_status():
    """Get worker observability metrics."""
    # Get active workers
    workers = Worker.all(connection=redis_conn)
    worker_info = [{
        "name": w.name,
        "state": w.get_state(),
        "current_job": w.get_current_job_id(),
        "successful_job_count": w.successful_job_count,
        "failed_job_count": w.failed_job_count,
    } for w in workers]

    # Queue stats
    queue_length = len(default_queue)

    # Failed jobs
    failed_registry = FailedJobRegistry(queue=default_queue)
    failed_job_ids = failed_registry.get_job_ids()
    failed_jobs = []
    for job_id in failed_job_ids[:10]:  # Limit to 10 most recent
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            failed_jobs.append({
                "id": job.id,
                "func_name": job.func_name,
                "exc_info": job.exc_info,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            })
        except:
            pass

    finished_registry = FinishedJobRegistry(queue=default_queue)

    return {
        "workers": worker_info,
        "queue": {
            "name": default_queue.name,
            "length": queue_length,
            "finished_count": len(finished_registry),
            "failed_count": len(failed_job_ids),
        },
        "failed_jobs": failed_jobs,
    }
