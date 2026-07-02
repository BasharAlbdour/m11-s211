# Multi-Service Routing Analysis Report

## Routing Accuracy

Routing accuracy on the held-out fixture: **100.00%** (15/15 correct, floor is 80%).

## Per-Service Metrics

| Service | Requests | Errors | Error Rate | p95 Latency (s) |
|---|---|---|---|---|
| router | 28 | 0 | 0.00% | 0.0750 |
| ner-kg | 22 | 0 | 0.00% | 0.0050 |
| rag | 20 | 0 | 0.00% | 0.0050 |

## Routing Pattern

- 53.3% of requests routed to **ner-kg** (8/15)
- 46.7% of requests routed to **rag** (7/15)

## Cross-Service Correlation

Each routing decision carries the `request_id` the router generates for that request. The router forwards this id on to the chosen backend via the `X-Request-ID` header, and every backend echoes the same id on its own structured log line, so filtering `docker compose logs` for one request-id shows a continuous trace across router → backend for that request. Sample request ids captured during this run: e2bbd83f-abe0-481a-bfc8-35b6fb771014, b0e67b99-2869-4b34-b72c-44b2b454b425, 0acb523c-455b-4dac-965e-b48d1c991a59.
