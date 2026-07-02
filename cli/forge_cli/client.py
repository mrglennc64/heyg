"""HTTP client + agent-friendly output contract.

Contract (mirrors HeyGen's CLI conventions so agent skills port directly):
- ALL structured output is JSON on stdout, one document per invocation.
- Human/progress noise goes to stderr only.
- Stable exit codes:
    0  success
    1  API/network error
    2  usage error (bad flags, missing file)
    3  job reached a failed state
    4  timeout while waiting
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

EXIT_OK, EXIT_API, EXIT_USAGE, EXIT_FAILED, EXIT_TIMEOUT = 0, 1, 2, 3, 4

BASE_URL = os.environ.get("FORGE_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("FORGE_API_KEY", "")


def emit(obj: dict, code: int = EXIT_OK) -> None:
    json.dump(obj, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)


def die(message: str, code: int = EXIT_API) -> None:
    emit({"error": message}, code)


def info(message: str) -> None:
    print(message, file=sys.stderr)


def client() -> httpx.Client:
    if not API_KEY:
        die("FORGE_API_KEY environment variable is not set", EXIT_USAGE)
    return httpx.Client(
        base_url=BASE_URL,
        headers={"X-Api-Key": API_KEY},
        timeout=httpx.Timeout(30.0, read=120.0),
    )


def request(method: str, path: str, **kwargs) -> dict:
    try:
        with client() as c:
            r = c.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        die(f"cannot reach gateway at {BASE_URL}: {exc}")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        die(f"HTTP {r.status_code}: {detail}")
    return r.json()


def wait_for_job(job_id: str, timeout_sec: int, poll_sec: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        status = request("GET", f"/api/v1/jobs/{job_id}")
        state = status["status"]
        info(f"job {job_id}: {state} ({status.get('progress', 0):.0%})")
        if state == "completed":
            return status
        if state == "failed":
            emit(status, EXIT_FAILED)
        time.sleep(poll_sec)
    emit({"error": "timeout", "job_id": job_id}, EXIT_TIMEOUT)
