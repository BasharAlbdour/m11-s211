# Multi-Service Routing Analysis Report

## Routing Accuracy

Routing accuracy on the held-out fixture: **100.00%** (15/15 correct, floor is 80%).

## Per-Service Metrics

| Service | Requests | Errors | Error Rate | p95 Latency (s) |
|---|---|---|---|---|
| router | 38 | 0 | 0.00% | 0.0750 |
| ner-kg | 32 | 0 | 0.00% | 0.0100 |
| rag | 30 | 0 | 0.00% | 0.0050 |

## Routing Pattern

- 53.3% of requests routed to **ner-kg** (8/15)
- 46.7% of requests routed to **rag** (7/15)

## Cross-Service Correlation

Each routing decision carries the `request_id` the router generates for that request. The router forwards this id on to the chosen backend via the `X-Request-ID` header, and every backend echoes the same id on its own structured log line, so filtering `docker compose logs` for one request-id shows a continuous trace across router → backend for that request. Sample request ids captured during this run: 81052b8f-b51a-4f61-8e70-9ea9f06f41e0, 483f1c6c-5a4d-4edb-a463-3b2653728dd5, 4b547351-2673-467e-8526-011387b9acc5.
