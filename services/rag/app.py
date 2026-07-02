"""rag service — answers questions over a small grounded corpus.

Exposes:
- POST /rag/answer — RAG answer endpoint
- GET  /metrics    — Prometheus text format

Honors Track — TODO implementations required.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

SERVICE = os.environ.get("SERVICE_NAME", "rag")
app = FastAPI()

# Structured logger -- emits one JSON line per request that includes the
# X-Request-ID so cross-service logs can be joined by id (Task 4 in the
# learner guide).
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(SERVICE)


REQUESTS = Counter(
    "service_requests_total", "Requests per endpoint", ["service", "endpoint", "status"]
)
LATENCY = Histogram(
    "service_request_latency_seconds",
    "Request latency by endpoint",
    ["service", "endpoint"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    LATENCY.labels(SERVICE, request.url.path).observe(elapsed_ms / 1000.0)
    REQUESTS.labels(SERVICE, request.url.path, str(response.status_code)).inc()
    response.headers["x-request-id"] = request_id
    logger.info(json.dumps({
        "service": SERVICE,
        "request_id": request_id,
        "path": request.url.path,
        "status": response.status_code,
        "latency_ms": round(elapsed_ms, 3),
    }))
    return response


class AnswerIn(BaseModel):
    question: str


@app.post("/rag/answer")
def answer(_: AnswerIn) -> dict:
    """TODO: implement RAG answer.

    Return {"answer": "...", "sources": [...]} or the canonical decline string
    when no grounded source is available.
    """
    raise NotImplementedError("TODO: implement /rag/answer")


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
