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
import re
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

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


_NER_KG_KEYWORDS = {
    "extract", "entity", "entities", "people", "organization", "organizations",
    "companies", "company", "product", "products", "mentioned", "acquired",
    "supplier", "suppliers", "parent", "knowledge", "graph", "type",
    "ceo", "cto", "founder", "founded", "headquartered", "hq", "makes",
}

_RAG_KEYWORDS = {
    "summarize", "explain", "describe", "difference", "why", "role", "think",
    "walk", "grounding", "vector", "keyword", "retrieval", "histogram",
    "histograms", "summary", "summaries", "f1", "micro", "macro", "latency",
    "prometheus", "router", "multi", "agent", "attention", "transformer",
    "load", "profiling",
}

def classify_question(question: str) -> Target:
    """Return the backend that should answer this question.

    TODO: implement.
    - Recommended starting point: a rule-based classifier (entity-extraction
      questions, KG-shape questions → 'ner-kg'; open-ended factual questions →
      'rag'). Document your rules in architecture.md.
    - You may also fit a small ML classifier; the rubric grades principled
      rationale either way.
    """
    tokens = _tokenize(question)
    ner_score = len(tokens & _NER_KG_KEYWORDS)
    rag_score = len(tokens & _RAG_KEYWORDS)
    if ner_score > rag_score:
        return "ner-kg"
    return "rag"

_KG_QUERY_KEYWORDS = {
    "who", "ceo", "founder", "founded", "parent", "headquartered",
    "makes", "acquired", "supplier", "suppliers", "knowledge", "graph",
}

_REL_KEYWORDS = {
    "CEO": {"ceo"},
    "FOUNDER_OF": {"founder", "founded"},
    "MAKES": {"makes", "product", "products"},
    "HEADQUARTERED_IN": {"headquartered", "hq"},
}

_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b")
_QUESTION_STOPWORDS = {
    "Who", "What", "Which", "Where", "When", "Why", "How",
    "Return", "Extract", "Find", "List", "Describe", "Explain",
    "Summarize", "Walk", "According", "ORGANIZATION",
}


def _looks_like_kg_query(question: str) -> bool:
    tokens = _tokenize(question)
    return bool(tokens & _KG_QUERY_KEYWORDS)


def _extract_entity_name(question: str) -> str | None:
    candidates = [
        m.group() for m in _PROPER_NOUN_RE.finditer(question)
        if m.group() not in _QUESTION_STOPWORDS
    ]
    return candidates[-1] if candidates else None


def _build_cypher(question: str) -> str:
    tokens = _tokenize(question)
    rel = None
    for rel_type, kws in _REL_KEYWORDS.items():
        if tokens & kws:
            rel = rel_type
            break

    name = _extract_entity_name(question)
    rel_clause = f":{rel}" if rel else "r"
    node_clause = f'a {{name: "{name}"}}' if name else "a"
    return f"MATCH ({node_clause})-[{rel_clause}]->(b) RETURN a, b"


async def forward_to_backend(target: Target, question: str, request_id: str) -> dict:
    """Forward the question to the chosen backend; return its JSON.

    TODO: implement.
    - 'ner-kg' has /extract and /kg/query — pick the right one for the question.
    - 'rag' has /rag/answer.
    - Propagate the x-request-id header so the backend's logs/metrics correlate.
    """
    headers = {"x-request-id": request_id}
    async with httpx.AsyncClient(timeout=10.0) as client:
        if target == "rag":
            resp = await client.post(
                f"{RAG_URL}/rag/answer", json={"question": question}, headers=headers
            )
        else:
            if _looks_like_kg_query(question):
                resp = await client.post(
                    f"{NER_KG_URL}/kg/query",
                    json={"cypher": _build_cypher(question)},
                    headers=headers,
                )
            else:
                resp = await client.post(
                    f"{NER_KG_URL}/extract", json={"text": question}, headers=headers
                )
        resp.raise_for_status()
        return resp.json()


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