"""router service — classifies a question and forwards to the right backend.

Exposes:
- POST /route      — classify + forward; returns the backend's response plus the routing decision
- GET  /metrics    — Prometheus text format
- GET  /decisions  — recent routing decisions (in-memory log, for analyze_routing.py)

Honors Track — TODO implementations required. The starter wires the FastAPI
surface, instrumentation, the shared request-id header, and the in-memory
decision log; learners implement the classifier and the backend call.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

SERVICE = os.environ.get("SERVICE_NAME", "router")
NER_KG_URL = os.environ.get("NER_KG_URL", "http://ner-kg:8000")
RAG_URL = os.environ.get("RAG_URL", "http://rag:8000")

app = FastAPI()

REQUESTS = Counter(
    "service_requests_total", "Requests per endpoint", ["service", "endpoint", "status"]
)
LATENCY = Histogram(
    "service_request_latency_seconds",
    "Request latency by endpoint",
    ["service", "endpoint"],
)
ROUTING_DECISIONS = Counter(
    "router_decisions_total", "Routing decisions by target backend", ["target"]
)

# In-memory routing decision log. Bounded to keep memory predictable in CI.
_DECISIONS: deque[dict] = deque(maxlen=1000)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    LATENCY.labels(SERVICE, request.url.path).observe(time.perf_counter() - start)
    REQUESTS.labels(SERVICE, request.url.path, str(response.status_code)).inc()
    response.headers["x-request-id"] = request_id
    return response


class RouteIn(BaseModel):
    question: str


Target = Literal["ner-kg", "rag"]


def classify_question(question: str) -> Target:
    """Return the backend that should answer this question.

    TODO: implement.
    - Recommended starting point: a rule-based classifier (entity-extraction
      questions, KG-shape questions → 'ner-kg'; open-ended factual questions →
      'rag'). Document your rules in architecture.md.
    - You may also fit a small ML classifier; the rubric grades principled
      rationale either way.
    """
    raise NotImplementedError("TODO: implement classify_question()")


async def forward_to_backend(target: Target, question: str, request_id: str) -> dict:
    """Forward the question to the chosen backend; return its JSON.

    TODO: implement.
    - 'ner-kg' has /extract and /kg/query — pick the right one for the question.
    - 'rag' has /rag/answer.
    - Propagate the x-request-id header so the backend's logs/metrics correlate.
    """
    raise NotImplementedError("TODO: implement forward_to_backend()")


@app.post("/route")
async def route(payload: RouteIn, request: Request) -> dict:
    request_id = request.state.request_id
    target = classify_question(payload.question)
    ROUTING_DECISIONS.labels(target).inc()
    backend_response = await forward_to_backend(target, payload.question, request_id)
    decision = {
        "request_id": request_id,
        "question": payload.question,
        "target": target,
        "ts": time.time(),
    }
    _DECISIONS.append(decision)
    return {"decision": decision, "backend_response": backend_response}


@app.get("/decisions")
def decisions(limit: int = 1000) -> dict:
    return {"decisions": list(_DECISIONS)[-limit:]}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
