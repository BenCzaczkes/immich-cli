#!/usr/bin/env python3
"""Resume Immich's heavy ML/generation job queues (mirrors desktop executor).

Counterpart to pause_jobs.py. Re-enables the same job queues the desktop app
resumes after a bulk upload. Safe to run unconditionally: jobs the server never
paused (e.g. user-managed) are simply re-resumed; Immich ignores no-op resumes.

    IMMICH_SERVER=http://host.docker.internal:2283/api \
    IMMICH_API_KEY=xxxx \
    uv run python scripts/resume_jobs.py

Endpoint (per immich_desktop/core/network_client.set_job_command):
    PUT /jobs/{job_name}  body {"command": "resume", "force": true}
"""

from __future__ import annotations

import os
import sys

import httpx

# Same set the desktop app pauses/resumes (immich_desktop/upload/executor.py).
# NOTE: no pausable "sidecar" queue exists (SidecarCheck/SidecarWrite/
# SidecarQueueAll are not valid PUT /jobs/{name} names — server returns 400).
HEAVY_JOBS = (
    "facialRecognition",
    "faceDetection",
    "smartSearch",
    "thumbnailGeneration",
    "metadataExtraction",
    "videoConversion",
)


def _get_env() -> tuple[str, str]:
    server = os.environ.get("IMMICH_SERVER")
    key = os.environ.get("IMMICH_API_KEY")
    if not server or not key:
        sys.exit("ERROR: set IMMICH_SERVER and IMMICH_API_KEY in the environment.")
    return server.rstrip("/"), key


def resume_job(base_url: str, key: str, job: str) -> bool:
    r = httpx.put(
        f"{base_url}/jobs/{job}",
        headers={"X-API-Key": key},
        json={"command": "resume", "force": True},
        timeout=30.0,
    )
    if r.status_code >= 400:
        print(f"  FAILED to resume {job}: {r.status_code} {r.text[:200]}")
        return False
    print(f"  resumed {job}")
    return True


def main() -> None:
    base_url, key = _get_env()
    print(f"Resuming {len(HEAVY_JOBS)} Immich job queues on {base_url} ...")
    ok = 0
    for job in HEAVY_JOBS:
        if resume_job(base_url, key, job):
            ok += 1
    print(f"\nDone: {ok}/{len(HEAVY_JOBS)} jobs resumed.")
    if ok < len(HEAVY_JOBS):
        sys.exit(1)


if __name__ == "__main__":
    main()
