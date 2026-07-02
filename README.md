# Module 11 — Stretch (Thu, Honors Track): Distributed Observability Router

Decompose the M10 backend into three coordinated services — `ner-kg`, `rag`, and `router` — each with its own `/metrics`. The router classifies incoming questions and routes to the right backend. A shared request-id flows across services. `analyze_routing.py` consolidates the per-service metrics + per-decision logs into a multi-service evaluation report.

**Repo:** standalone template (`m11-s211`). Branch: `stretch-thu-observability-router`.

**Honors Track — multi-agent scaffolding.** Eligibility is set in TalentLMS: completed all core Module 11 work, On Track or Advanced, attending consistently. Pair collaboration is permitted (split `router` from one backend across 2 learners).

---

## What you ship

1. `docker-compose-stretch.yml` — declares `ner-kg`, `rag`, `router` as three independent services on a shared network.
2. `services/ner_kg/app.py` — FastAPI service exposing `/extract`, `/kg/query`, and `/metrics`. (TODO: real handlers.)
3. `services/rag/app.py` — FastAPI service exposing `/rag/answer` and `/metrics`. (TODO.)
4. `services/router/app.py` — FastAPI service exposing `/route` (classifies a question, forwards to a backend) and `/metrics`. Generates a shared `request-id` per request and logs the routing decision. (TODO.)
5. `services/router/fixtures/routing_questions.json` — small held-out fixture used to evaluate routing accuracy.
6. `analyze_routing.py` — reads per-service `/metrics` + the router's per-decision logs and writes `routing-analysis-report.md`.
7. A 1-page architecture write-up (`architecture.md`) covering the monolith-vs-microservice trade-off as it applies to *this* stack.

---

## Setup

Branch from the template:

```bash
git checkout -b stretch-thu-observability-router
python3.11 -m venv .venv         # use 3.11 — pydantic 2.6 does not build on 3.13
source .venv/bin/activate
pip install -r requirements.txt
```

Bring up all three services with the stretch compose:

```bash
docker compose -f docker-compose-stretch.yml up --build -d
```

The compose file binds:

- `ner-kg` → `http://localhost:8101`
- `rag`    → `http://localhost:8102`
- `router` → `http://localhost:8100`

Send a request through the router:

```bash
curl -X POST http://localhost:8100/route \
    -H 'content-type: application/json' \
    -d '{"question": "Who is the CEO of OpenAI?"}'
```

Run the routing analysis:

```bash
python analyze_routing.py \
    --fixture services/router/fixtures/routing_questions.json \
    --router-base http://localhost:8100 \
    --ner-kg-base http://localhost:8101 \
    --rag-base http://localhost:8102 \
    --report-out routing-analysis-report.md
```

---

## Tests

```bash
pytest tests/ -v
```

The autograder gates:

- `docker-compose-stretch.yml` defines exactly three services with the expected names.
- Each service exposes `/metrics` returning OpenMetrics text format.
- The router classifies the held-out fixture with accuracy ≥ 0.80.
- `analyze_routing.py` runs end-to-end and produces `routing-analysis-report.md`.

---

## License

This repository is provided for educational use only. See [LICENSE](LICENSE) for terms.

You may clone and modify this repository for personal learning and practice, and reference code you wrote here in your professional portfolio. Redistribution outside this course is not permitted.
