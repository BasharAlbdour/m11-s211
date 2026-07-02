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
import re
from typing import Any

import httpx


def load_fixture(path: str) -> list[dict[str, str]]:
    """Read the routing fixture's questions list."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload["questions"]


def drive_router(router_base: str, questions: list[dict[str, str]]) -> list[dict[str, Any]]:
    """POST each question to the router; return the list of routing decisions.

    Each returned dict pairs the router's actual routing decision (target,
    request_id) with the fixture's expected label so routing_accuracy() can
    score it directly.
    """
    decisions: list[dict[str, Any]] = []
    with httpx.Client(timeout=10.0) as client:
        for q in questions:
            resp = client.post(f"{router_base}/route", json={"question": q["question"]})
            resp.raise_for_status()
            body = resp.json()
            decision = body.get("decision", {})
            decisions.append({
                "question": q["question"],
                "expected": q["expected"],
                "target": decision.get("target"),
                "request_id": decision.get("request_id"),
            })
    return decisions


def routing_accuracy(decisions: list[dict[str, Any]]) -> float:
    """Return the fraction of decisions whose `target` matches `expected`."""
    if not decisions:
        return 0.0
    correct = sum(1 for d in decisions if d.get("target") == d.get("expected"))
    return correct / len(decisions)


def fetch_metrics(base_url: str) -> str:
    """GET {base_url}/metrics and return the OpenMetrics text body."""
    resp = httpx.get(f"{base_url}/metrics", timeout=10.0)
    resp.raise_for_status()
    return resp.text


_METRIC_LINE_RE = re.compile(r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>[^}]*)\}\s+(?P<value>[-\d.eE+]+)\s*$')


def _parse_metric_lines(text: str) -> list[dict[str, Any]]:
    """Parse OpenMetrics text into a flat list of {name, labels, value}."""
    parsed: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_LINE_RE.match(line)
        if not m:
            continue
        labels: dict[str, str] = {}
        for kv in m.group("labels").split(","):
            kv = kv.strip()
            if not kv or "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            labels[k.strip()] = v.strip().strip('"')
        parsed.append({"name": m.group("name"), "labels": labels, "value": float(m.group("value"))})
    return parsed


def _summarize_service_metrics(text: str) -> dict[str, Any]:
    """Reduce a service's raw /metrics text to request volume, error rate,
    and an approximate p95 latency (from the cumulative histogram buckets).
    """
    lines = _parse_metric_lines(text)

    total_requests = 0.0
    error_requests = 0.0
    for line in lines:
        if line["name"] == "service_requests_total":
            total_requests += line["value"]
            status = line["labels"].get("status", "")
            if not status.startswith("2"):
                error_requests += line["value"]

    buckets: dict[str, float] = {}
    for line in lines:
        if line["name"] == "service_request_latency_seconds_bucket":
            le = line["labels"].get("le", "+Inf")
            buckets[le] = buckets.get(le, 0.0) + line["value"]

    def _le_key(le: str) -> float:
        return float("inf") if le == "+Inf" else float(le)

    p95_latency = None
    if buckets:
        ordered = sorted(buckets, key=_le_key)
        bucket_total = buckets[ordered[-1]]
        if bucket_total > 0:
            threshold = 0.95 * bucket_total
            for le in ordered:
                if buckets[le] >= threshold:
                    p95_latency = _le_key(le)
                    break

    error_rate = (error_requests / total_requests) if total_requests else 0.0
    return {
        "requests": total_requests,
        "errors": error_requests,
        "error_rate": error_rate,
        "p95_latency_seconds": p95_latency,
    }


def render_report(
    decisions: list[dict[str, Any]],
    accuracy: float,
    service_metrics: dict[str, str],
    report_path: str,
) -> None:
    """Write the consolidated `routing-analysis-report.md`."""
    lines: list[str] = []

    lines.append("# Multi-Service Routing Analysis Report")
    lines.append("")

    lines.append("## Routing Accuracy")
    lines.append("")
    correct = sum(1 for d in decisions if d.get("target") == d.get("expected"))
    lines.append(
        f"Routing accuracy on the held-out fixture: **{accuracy:.2%}** "
        f"({correct}/{len(decisions)} correct, floor is 80%)."
    )
    lines.append("")

    lines.append("## Per-Service Metrics")
    lines.append("")
    lines.append("| Service | Requests | Errors | Error Rate | p95 Latency (s) |")
    lines.append("|---|---|---|---|---|")
    for service, text in service_metrics.items():
        summary = _summarize_service_metrics(text)
        p95 = (
            f"{summary['p95_latency_seconds']:.4f}"
            if summary["p95_latency_seconds"] is not None
            else "n/a"
        )
        lines.append(
            f"| {service} | {summary['requests']:.0f} | {summary['errors']:.0f} | "
            f"{summary['error_rate']:.2%} | {p95} |"
        )
    lines.append("")

    lines.append("## Routing Pattern")
    lines.append("")
    target_counts: dict[str, int] = {}
    for d in decisions:
        target = d.get("target") or "unknown"
        target_counts[target] = target_counts.get(target, 0) + 1
    total_decisions = len(decisions) or 1
    for target, count in sorted(target_counts.items(), key=lambda kv: -kv[1]):
        pct = count / total_decisions
        lines.append(f"- {pct:.1%} of requests routed to **{target}** ({count}/{total_decisions})")
    lines.append("")

    lines.append("## Cross-Service Correlation")
    lines.append("")
    sample_ids = [d.get("request_id") for d in decisions if d.get("request_id")][:3]
    sample_str = ", ".join(sample_ids) if sample_ids else "none captured in this run"
    lines.append(
        "Each routing decision carries the `request_id` the router generates for that "
        "request. The router forwards this id on to the chosen backend via the "
        "`X-Request-ID` header, and every backend echoes the same id on its own "
        "structured log line, so filtering `docker compose logs` for one request-id "
        "shows a continuous trace across router → backend for that request. Sample "
        f"request ids captured during this run: {sample_str}."
    )
    lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


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