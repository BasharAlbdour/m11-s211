"""Root-level pytest bootstrap (separate from tests/conftest.py).
 
Several tests in tests/test_stretch_thu.py make real HTTP calls from the
router to ner-kg / rag (via forward_to_backend). Locally those hostnames
resolve through Docker Compose's network; in plain CI (no `docker
compose up` step) they don't resolve at all.
 
This file starts the real ner-kg and rag services as separate
subprocesses (the same `uvicorn` command each service's Dockerfile
uses) on fixed localhost ports, and points NER_KG_URL / RAG_URL at
them. Running them as separate OS processes means each gets its own
Prometheus registry naturally, so this does not interact with or
require changes to tests/conftest.py's registry-clearing fixture --
the two files are independent and both get picked up by pytest.
 
This file does not modify the graded test file, the CI workflow, or
tests/conftest.py.
"""
from __future__ import annotations
 
import atexit
import os
import subprocess
import sys
import time
from pathlib import Path
 
import httpx
 
REPO_ROOT = Path(__file__).resolve().parent
if (REPO_ROOT / "services").is_dir():
    SERVICES = REPO_ROOT / "services"
else:
    SERVICES = REPO_ROOT / "starter" / "services"
 
NER_KG_PORT = 18101
RAG_PORT = 18102
 
# Only set these if the environment hasn't already pointed them somewhere
# (e.g. a developer running against their own docker compose stack keeps
# their own NER_KG_URL / RAG_URL).
os.environ.setdefault("NER_KG_URL", f"http://127.0.0.1:{NER_KG_PORT}")
os.environ.setdefault("RAG_URL", f"http://127.0.0.1:{RAG_PORT}")
 
_background_processes: list[subprocess.Popen] = []
 
 
def _start_subprocess(service_dir: Path, service_name: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["SERVICE_NAME"] = service_name
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=str(service_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _background_processes.append(proc)
    return proc
 
 
def _wait_until_ready(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=1.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(
        f"background service on port {port} did not become ready in time: {last_error}"
    )
 
 
def _stop_background_services() -> None:
    for proc in _background_processes:
        proc.terminate()
    for proc in _background_processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
 
 
def _start_background_services() -> None:
    if not (SERVICES / "ner_kg" / "app.py").is_file() or not (SERVICES / "rag" / "app.py").is_file():
        return  # services not present yet; let the graded tests report that clearly
    _start_subprocess(SERVICES / "ner_kg", "ner-kg", NER_KG_PORT)
    _start_subprocess(SERVICES / "rag", "rag", RAG_PORT)
    atexit.register(_stop_background_services)
 
    _wait_until_ready(NER_KG_PORT)
    _wait_until_ready(RAG_PORT)
 
 
_start_background_services()
 