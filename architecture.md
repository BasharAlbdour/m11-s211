# Architecture Write-up: Monolith vs. Microservices for the M11 Stack
 
## What changed
 
The Module 10 backend was a single FastAPI process that handled entity
extraction, KG lookups, and RAG answering in one codebase, one deploy unit,
and one `/metrics` endpoint. This stretch splits that into three services —
`ner-kg` (extraction + KG query), `rag` (grounded Q&A), and a thin `router`
that classifies each incoming question and forwards it to the right
backend — composed with Docker Compose on a shared network, each exposing
its own `/metrics` and correlating logs via a shared `X-Request-ID`.
 
## What the split bought us
 
**Independent failure and scaling domains.** If the RAG corpus lookup gets
slow or starts erroring, `ner-kg` keeps serving unaffected — in the
monolith, a stuck request handler in one code path could still starve
shared resources (thread pool, event loop) for the other. Here, each
service has its own process, its own Uvicorn worker, its own
`CollectorRegistry`.
 
**Per-domain observability.** Each service's `/metrics` reports only its
own request volume, latency, and error rate. That's a real improvement
over one undifferentiated counter — I can see at a glance whether load or
errors are concentrated in extraction, retrieval, or routing, rather than
inferring it from log greping.
 
**A concrete stand-in for the "tool selection" problem.** The router's
`classify_question()` step is functionally identical to what an LLM agent
does when it picks which tool to call. Building it as a separate,
independently testable service — with its own accuracy metric against a
held-out fixture — is a more honest rehearsal for the capstone's
orchestration layer than a single `if/elif` inside a monolith would be.
Treating it as its own testable unit also surfaced a real bug: an early
version of the keyword rules missed "who is the CEO of X"-style questions
entirely (no keyword overlap with either backend, so it fell through to
the `rag` default and got a grounding-decline instead of a real answer).
Because the classifier lives behind its own function boundary with a
dedicated fixture, that was a one-line fix once caught — the fixture now
scores 15/15 (100%) against the graded questions.
 
**Clearer ownership boundaries.** `ner_kg/app.py` only knows about entities
and KG triples; `rag/app.py` only knows about the grounded corpus. Neither
imports the other. That decoupling made both easier to reason about in
isolation than the equivalent functions living side-by-side in one file.
 
## What it cost
 
**A real network hop, and the failure modes that come with it.** Every
`/route` call now makes a blocking `httpx` request to a backend over the
Docker network. That's latency the monolith never paid, and it's a new
failure mode — DNS resolution failing, a backend not being healthy yet
(which is why `router` has `depends_on: condition: service_healthy` on
both backends), or a backend timing out — that a single-process call stack
simply couldn't produce. Running `analyze_routing.py` against the live
stack made this concrete: the router's own p95 latency (75ms) was several
times higher than either backend's p95 in isolation (`ner-kg` at 10ms,
`rag` at 5ms) — the difference is almost entirely the extra hop plus the
backend's own processing time, stacked on top of the router's.
 
**Debugging is no longer "read one stack trace."** Diagnosing a bad
request now means correlating log lines across three separate processes.
The `X-Request-ID` header (generated once at the router, forwarded on the
outbound call, echoed by both backends) is what makes that tractable —
without it, `docker compose logs` for a single request would just be three
interleaved, unrelated-looking JSON lines.
 
**More moving parts to build and operate.** Three Dockerfiles instead of
one, three health checks, a shared Docker network, and — a bug I actually
hit while building this — three services each registering a metric named
`service_requests_total`. Prometheus's client library keeps a single
global default registry, so importing multiple services into one process
(exactly what the autograder does) throws a duplicate-timeseries error
unless each service is given its own private `CollectorRegistry`. That's a
distributed-systems tax the monolith never charged: the same metric name
reused across processes has to be handled deliberately.
 
## The trade-off, for this stack specifically
 
At this scale — a handful of endpoints, a small corpus, no independent
scaling requirements yet — a monolith would genuinely be simpler to build,
deploy, and debug, and I don't think decomposition pays for itself on
performance or reliability grounds alone here. What it *does* buy, and
what justifies it for this stretch, is the practice: a router that
classifies and forwards, cross-service correlation via a shared request
id, and per-service instrumentation are exactly the primitives a
multi-agent orchestrator needs. The cost of this split is infrastructure
and coordination overhead; the payoff is a debuggable, extensible pattern
that a real monolith-with-more-features would eventually be forced to
adopt anyway.