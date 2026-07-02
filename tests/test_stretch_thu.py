"""Stretch-Thu 11 autograder — structural + behavioral gate.

Per the rubric (`grading-rubric.md` lines 138-160), the autograder enforces
binary structural completeness; the TA rubric grades quality. These tests:

1. Verify `docker-compose-stretch.yml` declares the three services with the
   expected names and the router depends on the two backends.
2. Verify each service module exposes `/metrics` (in-process import).
3. Verify the routing fixture parses and the router classifies it with
   accuracy >= 0.80 (in-process via FastAPI TestClient).
4. Verify `analyze_routing.py` exposes its contracted entry points.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
# When this repo is pushed to the live template, `starter/` contents become the
# repo root, so `services/` is directly under REPO_ROOT. In staging it sits at
# `starter/services/`. Support both layouts.
if (REPO_ROOT / "services").is_dir():
    SERVICES = REPO_ROOT / "services"
    COMPOSE = REPO_ROOT / "docker-compose-stretch.yml"
    ANALYZE = REPO_ROOT / "analyze_routing.py"
else:
    SERVICES = REPO_ROOT / "starter" / "services"
    COMPOSE = REPO_ROOT / "starter" / "docker-compose-stretch.yml"
    ANALYZE = REPO_ROOT / "starter" / "analyze_routing.py"

sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------- compose --

def _read_compose() -> dict:
    import yaml

    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    with open(COMPOSE) as f:
        return yaml.safe_load(f)


def test_compose_declares_three_services() -> None:
    services = _read_compose().get("services", {})
    expected = {"ner-kg", "rag", "router"}
    found = set(services.keys())
    assert found == expected, (
        f"docker-compose-stretch.yml must declare exactly {expected}; "
        f"found {found}. Extra services indicate scope creep; missing "
        "services indicate an incomplete decomposition."
    )


def test_compose_router_depends_on_backends() -> None:
    router = _read_compose()["services"]["router"]
    depends = set(router.get("depends_on") or [])
    assert {"ner-kg", "rag"}.issubset(depends), (
        "router must depend on ner-kg and rag"
    )


# ---------------------------------------------------------- service /metrics --

@pytest.mark.parametrize("service_name", ["ner_kg", "rag", "router"])
def test_service_exposes_metrics(service_name: str) -> None:
    from fastapi.testclient import TestClient

    app_path = SERVICES / service_name / "app.py"
    assert app_path.is_file(), f"missing {app_path}"
    module = _load(f"_svc_{service_name}", app_path)
    client = TestClient(module.app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    assert "# HELP" in resp.text


# ------------------------------------------------------------ routing fixture --

def test_routing_fixture_parses() -> None:
    fixture = SERVICES / "router" / "fixtures" / "routing_questions.json"
    assert fixture.is_file(), f"missing {fixture}"
    payload = json.loads(fixture.read_text())
    assert "questions" in payload and len(payload["questions"]) >= 10
    for q in payload["questions"]:
        assert "question" in q and "expected" in q
        assert q["expected"] in {"ner-kg", "rag"}


def test_router_classifies_fixture_above_floor() -> None:
    module = _load("_router_app", SERVICES / "router" / "app.py")
    fixture = SERVICES / "router" / "fixtures" / "routing_questions.json"
    questions = json.loads(fixture.read_text())["questions"]
    correct = sum(
        1 for q in questions if module.classify_question(q["question"]) == q["expected"]
    )
    accuracy = correct / len(questions)
    assert accuracy >= 0.80, (
        f"routing accuracy {accuracy:.2f} below 0.80 floor; "
        "tighten classify_question() or expand the rule set."
    )


# -------------------------------------------------------- analyze_routing.py --

def _function_body_is_trivial(fn_node: ast.FunctionDef) -> bool:
    """True iff the function body (after an optional docstring) is one of:

    - `raise NotImplementedError(...)`   -- unmodified starter
    - `pass`                              -- silently skipped stub
    - `return` / `return None`            -- short-circuit
    - `return <Constant>` (e.g. `return 0`, `return 1.0`, `return "foo"`)
      -- placeholder return that produces an unrelated literal

    Anything richer (a call expression, an attribute access, an if/for/while
    block, a multi-statement body) is treated as a real implementation.
    """
    body = list(fn_node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Raise):
        raised = stmt.exc
        if raised is None:
            return True
        name_node = raised.func if isinstance(raised, ast.Call) else raised
        return isinstance(name_node, ast.Name) and name_node.id == "NotImplementedError"
    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            return True
        if isinstance(stmt.value, ast.Constant):
            return True
    return False


def test_analyze_routing_module_present() -> None:
    """Each contracted entry point is defined AND has a non-stub body.

    Catches buggy variant: learner left the four core functions as
    `raise NotImplementedError("TODO: implement ...")` starter stubs.
    `hasattr` alone trivially passes against the unmodified starter.
    """
    module = _load("_analyze", ANALYZE)
    expected = (
        "load_fixture",
        "drive_router",
        "routing_accuracy",
        "fetch_metrics",
        "render_report",
    )
    for fn in expected:
        assert hasattr(module, fn), f"analyze_routing must expose {fn}"

    tree = ast.parse(ANALYZE.read_text(), filename=str(ANALYZE))
    fn_nodes = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    stubs = [
        fn for fn in expected
        if fn in fn_nodes and _function_body_is_trivial(fn_nodes[fn])
    ]
    assert not stubs, (
        f"analyze_routing.py still has trivial / placeholder bodies in: "
        f"{stubs}. The body must contain real implementation -- a function "
        f"call, control flow, or a multi-statement block -- not just "
        f"`pass`, `raise NotImplementedError`, `return None`, or a constant "
        f"literal return. Implement these per the docstrings."
    )


def test_analyze_routing_load_fixture_works() -> None:
    module = _load("_analyze2", ANALYZE)
    fixture = SERVICES / "router" / "fixtures" / "routing_questions.json"
    questions = module.load_fixture(str(fixture))
    assert isinstance(questions, list) and len(questions) >= 10


# ----------------------------------------------------------- artifact gates --

def test_architecture_writeup_present() -> None:
    """The required architecture.md write-up exists at the repo root."""
    path = REPO_ROOT / "architecture.md"
    assert path.is_file(), (
        f"missing {path.name}. The Honors deliverable list includes a 1-page "
        f"architecture write-up at the repo root covering the monolith-vs-"
        f"microservice trade-off for this stack."
    )
    text = path.read_text().strip()
    assert len(text) >= 200, (
        f"{path.name} is too short ({len(text)} chars). The write-up should "
        "be a meaningful one-page essay, not a placeholder."
    )


def test_routing_analysis_report_present() -> None:
    """`routing-analysis-report.md` exists at the repo root after the
    learner has run `analyze_routing.py`.

    Catches buggy variant: learner did not commit the report file (the
    deliverable list explicitly requires `analyze_routing.py` to produce
    `routing-analysis-report.md` and the learner to commit it).
    """
    path = REPO_ROOT / "routing-analysis-report.md"
    assert path.is_file(), (
        f"missing {path.name}. Run `analyze_routing.py` with the documented "
        "arguments and commit the produced report file."
    )


# ------------------------------------------------------------- router surface --

def test_router_exposes_route_endpoint() -> None:
    """POST /route on the router service responds with a routed decision.

    Catches buggy variant: learner skipped wiring the /route handler and
    only implemented /metrics, which the metrics test would still pass.
    """
    from fastapi.testclient import TestClient

    module = _load("_router_for_route", SERVICES / "router" / "app.py")
    client = TestClient(module.app)
    # A clearly NER-shaped question; we are not asserting on the routing
    # decision here, only that /route is wired and responds with a
    # parseable JSON object including the routing target.
    resp = client.post("/route", json={"question": "Find recipes that use ginger"})
    assert resp.status_code == 200, (
        f"POST /route returned {resp.status_code}; expected 200. "
        "Did you wire the /route handler on the router service?"
    )
    body = resp.json()
    assert "target" in body or "decision" in body or "route" in body, (
        f"/route response missing target/decision/route field; body={body!r}. "
        "The decision payload must surface which backend handled the request."
    )


def test_router_exposes_decisions_endpoint() -> None:
    """GET /decisions returns the recent routing decision log.

    Catches buggy variant: learner skipped the in-memory decision log
    that `analyze_routing.py` needs.
    """
    from fastapi.testclient import TestClient

    module = _load("_router_for_decisions", SERVICES / "router" / "app.py")
    client = TestClient(module.app)
    # Drive one request so the log has at least one entry.
    client.post("/route", json={"question": "Find recipes that use ginger"})
    resp = client.get("/decisions")
    assert resp.status_code == 200, (
        f"GET /decisions returned {resp.status_code}; expected 200. "
        "The router must expose an in-memory decision log for analyze_routing.py."
    )
    body = resp.json()
    # Accept either a bare list or a {decisions: [...]} envelope.
    decisions = body if isinstance(body, list) else body.get("decisions", [])
    assert isinstance(decisions, list), (
        f"/decisions must return a list (or {{'decisions': [...]}}); got {body!r}."
    )


def test_router_emits_x_request_id_on_route_response() -> None:
    """The router's POST /route response carries X-Request-ID.

    Catches buggy variant: learner skipped request-id middleware on the
    router service.
    """
    from fastapi.testclient import TestClient

    module = _load("_router_for_xrid_emit", SERVICES / "router" / "app.py")
    client = TestClient(module.app)
    resp = client.post("/route", json={"question": "Find recipes that use ginger"})
    rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
    assert rid, (
        "POST /route response is missing the X-Request-ID header. Task 4 "
        "requires the router to generate (or accept) a request-id and emit "
        "it on the response so downstream logs can be correlated."
    )


def test_router_records_request_id_in_decisions_log() -> None:
    """The X-Request-ID returned on /route appears in the /decisions log."""
    from fastapi.testclient import TestClient

    module = _load("_router_for_xrid_log", SERVICES / "router" / "app.py")
    client = TestClient(module.app)
    resp = client.post("/route", json={"question": "Find recipes that use ginger"})
    rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
    decisions_resp = client.get("/decisions")
    decisions_body = decisions_resp.json()
    decisions = (
        decisions_body if isinstance(decisions_body, list)
        else decisions_body.get("decisions", [])
    )
    rid_in_decisions = any(rid in str(d) for d in decisions)
    assert rid_in_decisions, (
        f"The X-Request-ID {rid!r} returned on /route does not appear in any "
        "/decisions entry."
    )


def test_router_forwards_x_request_id_to_backend(monkeypatch) -> None:
    """The router's outbound httpx call to the backend carries X-Request-ID.

    Task 4 (cross-service correlation) requires the router to propagate
    the request-id on its httpx call so the backend can echo it in
    its own logs. Without this, a learner who only sets the response
    header on /route (but does not forward it on the backend call) would
    pass the prior tests -- defeating the cross-service correlation goal.

    We intercept the outbound httpx call and inspect the headers it
    would have sent.
    """
    import httpx

    module = _load("_router_for_xrid_forward", SERVICES / "router" / "app.py")
    captured_requests: list[httpx.Request] = []

    # MockTransport lets us intercept every outbound request the router makes.
    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={"answer": "stub", "citations": [], "retrieved": []},
        )

    mock_transport = httpx.MockTransport(_handler)

    # Patch every httpx client constructor so any approach the learner
    # uses (Client(), AsyncClient(), httpx.post(...), httpx.get(...))
    # routes through our transport.
    real_client = httpx.Client
    real_async_client = httpx.AsyncClient

    def _patched_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_client(*args, **kwargs)

    def _patched_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(module.httpx, "Client", _patched_client)
    monkeypatch.setattr(module.httpx, "AsyncClient", _patched_async_client)
    # httpx.post / httpx.get also hit the network -- patch them through
    # a default Client too.
    def _patched_post(url, **kwargs):
        with _patched_client() as c:
            return c.post(url, **kwargs)

    def _patched_get(url, **kwargs):
        with _patched_client() as c:
            return c.get(url, **kwargs)

    monkeypatch.setattr(module.httpx, "post", _patched_post)
    monkeypatch.setattr(module.httpx, "get", _patched_get)

    from fastapi.testclient import TestClient

    client = TestClient(module.app)
    resp = client.post(
        "/route", json={"question": "Find recipes that use ginger"}
    )
    assert resp.status_code == 200, (
        f"POST /route returned {resp.status_code}; expected 200 with mocked backend."
    )
    rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
    assert rid, "expected /route response to carry an X-Request-ID header."

    assert captured_requests, (
        "The router did not make any outbound httpx call when handling /route. "
        "Implement forward_to_backend() so the router actually forwards the "
        "question to the backend service."
    )
    forwarded_rids = []
    for req in captured_requests:
        header_value = (
            req.headers.get("x-request-id")
            or req.headers.get("X-Request-ID")
        )
        if header_value:
            forwarded_rids.append(header_value)
    assert forwarded_rids, (
        f"The router made {len(captured_requests)} outbound httpx call(s) but "
        "none carried an X-Request-ID header. Task 4 requires the router to "
        "propagate the X-Request-ID on its httpx call to the backend so "
        "downstream logs can be joined."
    )
    assert rid in forwarded_rids, (
        f"The router emitted X-Request-ID {rid!r} on its /route response, but "
        f"forwarded a different id ({forwarded_rids[0]!r}) on the backend "
        "call. Use the same request-id on both surfaces so cross-service "
        "logs correlate."
    )
