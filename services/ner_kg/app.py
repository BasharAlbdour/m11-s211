"""ner-kg service — extracts entities and answers KG queries.

Exposes:
- POST /extract   — entity extraction from a text
- POST /kg/query  — small KG lookup
- GET  /metrics   — Prometheus text format

Honors Track — TODO implementations required. The starter wires the FastAPI
surface, instrumentation, and the request-id header echo; learners implement
the actual extraction + KG logic.
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

SERVICE = os.environ.get("SERVICE_NAME", "ner-kg")
app = FastAPI()

# Structured logger -- emits one JSON line per request that includes the
# X-Request-ID so cross-service logs can be joined by id (Task 4 in the
# learner guide). The handler ships configured at INFO; the middleware
# below writes one log line per response.
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


class ExtractIn(BaseModel):
    text: str


class KgQueryIn(BaseModel):
    cypher: str


@app.post("/extract")
def extract(_: ExtractIn) -> dict:
    """TODO: implement entity extraction.

    Return a dict like {"entities": [{"text": ..., "label": ...}, ...]}.
    """
    raise NotImplementedError("TODO: implement /extract")


@app.post("/kg/query")
def kg_query(_: KgQueryIn) -> dict:
    """TODO: implement KG lookup.

    Return a dict like {"rows": [...]}.
    """
    raise NotImplementedError("TODO: implement /kg/query")


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
