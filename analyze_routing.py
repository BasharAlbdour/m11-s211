"""Consolidated routing analysis report writer.

Reads the routing fixture, drives each question through the live router,
pulls per-service `/metrics`, and writes `routing-analysis-report.md` with:
- Routing accuracy against the fixture's `expected` labels
- Per-service request volume + p95 latency from `/metrics`
- One identified routing pattern (e.g., backend imbalance)
- A short cross-service correlation paragraph

Honors Track — TODO implementations required.
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def load_fixture(path: str) -> list[dict[str, str]]:
    """Read the routing fixture's questions list."""
    with open(path) as f:
        payload = json.load(f)
    return payload["questions"]


def drive_router(router_base: str, questions: list[dict[str, str]]) -> list[dict[str, Any]]:
    """POST each question to the router; return the list of routing decisions.

    TODO: implement.
    - For each q, POST {"question": q["question"]} to {router_base}/route.
    - Collect the returned decision (target + request_id).
    - Pair each decision with q["expected"] for accuracy scoring.
    """
    raise NotImplementedError("TODO: implement drive_router()")


def routing_accuracy(decisions: list[dict[str, Any]]) -> float:
    """Return the fraction of decisions whose `target` matches `expected`.

    TODO: implement.
    """
    raise NotImplementedError("TODO: implement routing_accuracy()")


def fetch_metrics(base_url: str) -> str:
    """GET {base_url}/metrics and return the OpenMetrics text body.

    TODO: implement.
    """
    raise NotImplementedError("TODO: implement fetch_metrics()")


def render_report(
    decisions: list[dict[str, Any]],
    accuracy: float,
    service_metrics: dict[str, str],
    report_path: str,
) -> None:
    """Write the consolidated `routing-analysis-report.md`.

    Required sections:
    - "## Routing Accuracy" (with the accuracy number)
    - "## Per-Service Metrics" (volume + p95 per service)
    - "## Routing Pattern" (one observed pattern, e.g., "70% routed to rag")
    - "## Cross-Service Correlation" (one paragraph)

    TODO: implement.
    """
    raise NotImplementedError("TODO: implement render_report()")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="M11 Stretch-Thu routing analysis")
    p.add_argument("--fixture", required=True)
    p.add_argument("--router-base", required=True)
    p.add_argument("--ner-kg-base", required=True)
    p.add_argument("--rag-base", required=True)
    p.add_argument("--report-out", default="routing-analysis-report.md")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    questions = load_fixture(args.fixture)
    decisions = drive_router(args.router_base, questions)
    accuracy = routing_accuracy(decisions)
    service_metrics = {
        "router": fetch_metrics(args.router_base),
        "ner-kg": fetch_metrics(args.ner_kg_base),
        "rag": fetch_metrics(args.rag_base),
    }
    render_report(decisions, accuracy, service_metrics, args.report_out)
    print(f"Wrote {args.report_out} (accuracy={accuracy:.3f})")


if __name__ == "__main__":
    main()
