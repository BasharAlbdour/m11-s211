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
import re
import time
import uuid
 
from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel
from starlette.responses import Response
 
SERVICE = os.environ.get("SERVICE_NAME", "rag")
app = FastAPI()
 
# Structured logger -- emits one JSON line per request that includes the
# X-Request-ID so cross-service logs can be joined by id (Task 4 in the
# learner guide).
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(SERVICE)
 
 
REGISTRY = CollectorRegistry()
 
REQUESTS = Counter(
    "service_requests_total", "Requests per endpoint", ["service", "endpoint", "status"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "service_request_latency_seconds",
    "Request latency by endpoint",
    ["service", "endpoint"],
    registry=REGISTRY,
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
 
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "how", "what", "why", "does", "do", "did", "should", "would", "could",
    "i", "me", "my", "this", "that", "of", "in", "on", "for", "to", "and",
    "or", "vs", "versus", "between", "about", "walk", "through", "think",
    "describe", "explain", "summarize", "role",
}
 
_TOKEN_RE = re.compile(r"[a-z0-9]+")
 
 
def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}
 
 
_CORPUS = [
    {
        "id": "attention-mechanism",
        "keywords": {"transformer", "attention", "self-attention", "query",
                     "key", "value", "softmax", "heads"},
        "answer": (
            "Transformer attention lets each token look at every other token "
            "in the sequence and weigh how relevant each one is. Each token "
            "is projected into a query, key, and value vector; the query is "
            "compared against every key (via a dot product, scaled and "
            "passed through softmax) to produce attention weights, which are "
            "then used to combine the value vectors into that token's new "
            "representation. Multi-head attention runs several of these in "
            "parallel with different learned projections so the model can "
            "capture different types of relationships at once."
        ),
    },
    {
        "id": "micro-vs-macro-f1",
        "keywords": {"micro", "macro", "f1", "precision", "recall",
                     "class", "imbalance", "average"},
        "answer": (
            "Micro-F1 pools all true/false positives and negatives across "
            "classes before computing precision and recall, so it's "
            "dominated by the performance on frequent classes -- effectively "
            "an accuracy-like number on imbalanced data. Macro-F1 computes "
            "F1 per class and then averages those scores unweighted, so a "
            "rare class counts as much as a common one. Macro-F1 is the "
            "harsher, more informative metric when minority-class "
            "performance matters; micro-F1 is more forgiving on skewed "
            "label distributions."
        ),
    },
    {
        "id": "latency-load-profiling",
        "keywords": {"latency", "load", "profiling", "inference", "service",
                     "throughput", "percentile", "p95", "p99"},
        "answer": (
            "Latency and load profiling for an inference service are "
            "complementary, not interchangeable: latency profiling measures "
            "how long individual requests take (usually as percentiles -- "
            "p50/p95/p99 -- since averages hide tail behavior), while load "
            "profiling measures how the service holds up as request volume "
            "increases, looking for the point where latency percentiles "
            "start climbing or error rates rise. A service can look fine "
            "under light single-request testing but degrade sharply under "
            "concurrent load, so both need to be measured together to know "
            "the service's real operating envelope."
        ),
    },
    {
        "id": "histograms-vs-summaries",
        "keywords": {"prometheus", "histogram", "histograms", "summary",
                     "summaries", "latency", "aggregate", "quantile"},
        "answer": (
            "Prometheus histograms bucket observations into configurable "
            "ranges and expose cumulative counts per bucket, which lets "
            "quantiles be computed after the fact and, critically, "
            "aggregated across instances at query time. Summaries compute "
            "quantiles client-side per instance, so those quantiles can't be "
            "meaningfully averaged or combined across replicas -- a summary "
            "from one pod says nothing valid about the fleet-wide p95. For "
            "latency in a multi-instance service, histograms are preferred "
            "because they preserve the ability to aggregate correctly."
        ),
    },
    {
        "id": "router-role-multiagent",
        "keywords": {"router", "role", "multi-agent", "orchestrator",
                     "tool", "selection", "classify", "dispatch"},
        "answer": (
            "In a multi-agent system, a router sits in front of specialized "
            "backends or tools and decides which one should handle an "
            "incoming request -- effectively the system's tool-selection "
            "step. It classifies the request (rule-based or learned), "
            "forwards it to the chosen backend, and is also the natural "
            "place to attach cross-cutting concerns like a shared "
            "correlation id, since every request passes through it before "
            "fanning out. A well-instrumented router is what makes an "
            "otherwise opaque multi-service pipeline debuggable."
        ),
    },
    {
        "id": "rag-grounding-rate",
        "keywords": {"rag", "grounding", "grounded", "groundedness", "rate",
                     "computed", "citation", "source", "hallucination"},
        "answer": (
            "RAG grounding rate measures what fraction of a generated "
            "answer's claims are actually supported by the retrieved "
            "context, rather than invented by the model. A common way to "
            "compute it is to check, for each answer (or each sentence in "
            "it), whether its content can be traced back to the retrieved "
            "passages -- via lexical overlap, entailment scoring, or citation "
            "matching -- and report the fraction that pass. A low grounding "
            "rate signals the model is filling gaps from its own knowledge "
            "instead of the retrieved sources, which is the failure mode RAG "
            "is meant to prevent."
        ),
    },
    {
        "id": "vector-vs-keyword-retrieval",
        "keywords": {"vector", "keyword", "retrieval", "dense", "sparse",
                     "bm25", "embedding", "semantic", "hybrid"},
        "answer": (
            "Keyword retrieval (e.g. BM25) matches documents based on exact "
            "or near-exact term overlap with the query, so it's precise for "
            "specific terms, names, and codes but misses paraphrases or "
            "synonyms. Vector (dense embedding) retrieval matches on "
            "semantic similarity, so it can find relevant passages that "
            "share meaning but not wording -- at the cost of sometimes "
            "surfacing topically-similar but non-answering text. In "
            "practice, hybrid search that combines both signals tends to "
            "outperform either alone."
        ),
    },
]
 
_GROUNDING_DECLINE = (
    "I don't have a grounded source for this question in my current corpus, "
    "so I can't answer it reliably."
)
_MIN_OVERLAP = 1  # require at least one meaningful shared keyword to answer
 
 
def answer_question(question: str) -> dict:
    q_tokens = _tokenize(question)
    best_doc = None
    best_score = 0
    for doc in _CORPUS:
        score = len(q_tokens & doc["keywords"])
        if score > best_score:
            best_score = score
            best_doc = doc
 
    if best_doc is None or best_score < _MIN_OVERLAP:
        return {"answer": _GROUNDING_DECLINE, "sources": []}
 
    return {"answer": best_doc["answer"], "sources": [best_doc["id"]]}
 
@app.post("/rag/answer")
def answer(payload: AnswerIn) -> dict:
    """TODO: implement RAG answer.
 
    Return {"answer": "...", "sources": [...]} or the canonical decline string
    when no grounded source is available.
    """
    return answer_question(payload.question)
 
 
@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)