"""Celery app factory with per-stage queue routing.

Each GPU service consumes exactly one queue; routing is by task-name prefix so
the gateway can compose canvases without importing worker code.
"""
from celery import Celery

from .config import settings

TASK_ROUTES = {
    "voice.*": {"queue": "voice"},
    "avatar.*": {"queue": "avatar"},
    "lipsync.*": {"queue": "lipsync"},
    "compositor.*": {"queue": "compositor"},
}


def make_celery(name: str) -> Celery:
    app = Celery(name, broker=settings().redis_url, backend=settings().redis_url)
    app.conf.update(
        task_routes=TASK_ROUTES,
        task_acks_late=True,                  # requeue on worker crash (OOM etc.)
        worker_prefetch_multiplier=1,         # GPU tasks: never hoard
        task_reject_on_worker_lost=True,
        result_expires=7 * 24 * 3600,
        task_serializer="json",
        accept_content=["json"],
        broker_transport_options={"visibility_timeout": 3600},
    )
    return app
