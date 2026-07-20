#!/usr/bin/env python3
"""Pause Immich's heavy ML/generation job queues (mirrors desktop executor).

Stops the same job queues the desktop app pauses before a bulk upload, so the
server doesn't run face-detection / recognition / metadata extraction while you
upload (and so it can't re-detect faces already provided via an XMP sidecar).

    IMMICH_SERVER=http://host.docker.internal:2283/api \
    IMMICH_API_KEY=xxxx \
    uv run python scripts/pause_jobs.py

Endpoint (per immich_desktop/core/network_client.set_job_command):
    PUT /jobs/{job_name}  body {"command": "pause", "force": true}

Best-effort: a failure on one job is logged and the rest are still attempted.
Re-running is safe — already-paused jobs are just re-paused.
"""

from __future__ import annotations

import os
import sys

import httpx

# Same set the desktop app pauses (immich_desktop/upload/executor.py).
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


def pause_job(base_url: str, key: str, job: str) -> bool:
    r = httpx.put(
        f"{base_url}/jobs/{job}",
        headers={"X-API-Key": key},
        json={"command": "pause", "force": True},
        timeout=30.0,
    )
    if r.status_code >= 400:
        print(f"  FAILED to pause {job}: {r.status_code} {r.text[:200]}")
        return False
    print(f"  paused {job}")
    return True


def main() -> None:
    base_url, key = _get_env()
    print(f"Pausing {len(HEAVY_JOBS)} Immich job queues on {base_url} ...")
    ok = 0
    for job in HEAVY_JOBS:
        if pause_job(base_url, key, job):
            ok += 1
    print(f"\nDone: {ok}/{len(HEAVY_JOBS)} jobs paused.")
    if ok < len(HEAVY_JOBS):
        sys.exit(1)


if __name__ == "__main__":
    main()
