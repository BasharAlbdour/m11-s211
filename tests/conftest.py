"""Stretch-Thu 11 autograder conftest.

The autograder imports three FastAPI services in the same process
(ner_kg, rag, router). Each service declares its Prometheus metrics at
module scope against the default REGISTRY -- importing more than one
service in one process would raise:

    ValueError: Duplicated timeseries in CollectorRegistry

unless the registry is wiped between imports. This autouse fixture
clears the default REGISTRY before each test so a clean instance is
available for the test's service import.

Same pattern as the M11 Drill autograder. The learner's service code
is correct (module-level metrics is what the M11 reading teaches);
this fixture exists to keep the test harness isolation honest.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Wipe the default prometheus_client REGISTRY before each test."""
    try:
        from prometheus_client import REGISTRY
    except ImportError:
        yield
        return

    for collector in list(REGISTRY._collector_to_names.keys()):
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    yield
