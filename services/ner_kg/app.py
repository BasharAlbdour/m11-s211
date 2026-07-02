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
 
SERVICE = os.environ.get("SERVICE_NAME", "ner-kg")
app = FastAPI()
 
# Structured logger -- emits one JSON line per request that includes the
# X-Request-ID so cross-service logs can be joined by id (Task 4 in the
# learner guide). The handler ships configured at INFO; the middleware
# below writes one log line per response.
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
 
 
class ExtractIn(BaseModel):
    text: str
 
 
class KgQueryIn(BaseModel):
    cypher: str
 
_ORG_SUFFIXES = (
    "Inc", "Inc.", "Corp", "Corp.", "LLC", "Ltd", "Ltd.", "Co", "Co.",
    "Company", "Labs", "Technologies", "Group", "Foundation",
)
_PERSON_TITLES = {"Mr", "Mrs", "Ms", "Dr", "Prof"}
_GPE_KNOWN = {
    "Amman", "Jordan", "Cottbus", "Frankfurt", "Germany", "Oman", "Algeria",
    "Saudi Arabia", "London", "Paris", "Tokyo", "New York", "California",
    "San Francisco",
}
_ORG_KNOWN = {"NATO", "OpenAI", "Anthropic", "IBM", "Bank of America"}
_STOPWORDS_INITIAL = {"The", "A", "An", "This", "That", "She", "He", "They", "We", "It", "I"}
_JOINER_STOP = {"CEO", "CTO", "President", "Founder"}
 
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)*\b")
_JOIN_RE = re.compile(r"\s+(of|the|&)\s+")
 
def _classify_span(span: str) -> str:
    words = span.split()
    if span in _ORG_KNOWN:
        return "ORG"
    if span in _GPE_KNOWN:
        return "GPE"
    if any(span.endswith(suf) or span == suf for suf in _ORG_SUFFIXES):
        return "ORG"
    if words and words[0].rstrip(".") in _PERSON_TITLES:
        return "PERSON"
    if span.isupper() and len(span) > 1:
        return "ORG"
    if len(words) == 2 and all(w[0].isupper() and w[1:].islower() for w in words):
        return "PERSON"
    return "MISC"
 
def extract_entities(text: str) -> list[dict]:
    raw_spans = []
    for match in _PROPER_NOUN_RE.finditer(text):
        span = match.group().strip()
        if not span:
            continue
        if span in _STOPWORDS_INITIAL:
            continue
        raw_spans.append({"text": span, "start": match.start(), "end": match.end()})
 
    merged: list[dict] = []
    i = 0
    while i < len(raw_spans):
        cur = raw_spans[i]
        j = i + 1
        while j < len(raw_spans):
            gap = text[cur["end"]:raw_spans[j]["start"]]
            if _JOIN_RE.fullmatch(gap) and cur["text"].split()[-1] not in _JOINER_STOP:
                cur = {
                    "text": text[cur["start"]:raw_spans[j]["end"]],
                    "start": cur["start"],
                    "end": raw_spans[j]["end"],
                }
                j += 1
            else:
                break
        merged.append({**cur, "label": _classify_span(cur["text"])})
        i = j
    return merged
 
_KG_TRIPLES = [
    {"subject": "OpenAI", "relation": "CEO", "object": "Sam Altman"},
    {"subject": "Anthropic", "relation": "CEO", "object": "Dario Amodei"},
    {"subject": "Sam Altman", "relation": "FOUNDER_OF", "object": "OpenAI"},
    {"subject": "Dario Amodei", "relation": "FOUNDER_OF", "object": "Anthropic"},
    {"subject": "Anthropic", "relation": "MAKES", "object": "Claude"},
    {"subject": "OpenAI", "relation": "MAKES", "object": "GPT-4"},
    {"subject": "Anthropic", "relation": "HEADQUARTERED_IN", "object": "San Francisco"},
    {"subject": "OpenAI", "relation": "HEADQUARTERED_IN", "object": "San Francisco"},
]
 
_REL_RE = re.compile(r"\[:([A-Za-z_]+)\]")
_NAME_RE = re.compile(r"""name:\s*["']([^"']+)["']""")
 
 
def run_kg_query(cypher: str) -> list[dict]:
    rel_match = _REL_RE.search(cypher)
    name_match = _NAME_RE.search(cypher)
 
    rows = _KG_TRIPLES
    if rel_match:
        rel_type = rel_match.group(1).upper()
        rows = [r for r in rows if r["relation"] == rel_type]
    if name_match:
        name = name_match.group(1)
        rows = [r for r in rows if name in (r["subject"], r["object"])]
    return rows
 
@app.post("/extract")
def extract(payload: ExtractIn) -> dict:
    """TODO: implement entity extraction.
    Return a dict like {"entities": [{"text": ..., "label": ...}, ...]}.
    """
    return {"entities": extract_entities(payload.text)}
 
 
@app.post("/kg/query")
def kg_query(payload: KgQueryIn) -> dict:
    """TODO: implement KG lookup.
    Return a dict like {"rows": [...]}.
    """
    return {"rows": run_kg_query(payload.cypher)}
 
 
@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)