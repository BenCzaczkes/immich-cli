#!/usr/bin/env python3
"""Verify that specific Immich people/faces are fully cleared from the server.

After deleting the two test images (and their people) from the server, run this
to confirm there are no lingering traces:

    IMMICH_SERVER=http://host.docker.internal:2283/api \
    IMMICH_API_KEY=xxxx \
    uv run python scripts/check_people_cleared.py

It checks:
  1. GET /people  -> look for the target person IDs / names.
  2. GET /faces   -> look for any faces whose personId matches the targets.

This is READ-ONLY. It never deletes anything.

The default target IDs/names come from the two downloaded test images
(19580128.jpg, 19580328.jpg). Override with --person-id / --name as needed.
"""

from __future__ import annotations

import os
import sys

import httpx

# --- Targets derived from downloads/19580128.jpg + 19580328.jpg ---
DEFAULT_PERSON_IDS = [
    "020b92cd-ac8b-487a-b726-e79706fc81d1",  # Alfred Czaczkes
    "13df863a-20fb-490a-8851-734a0cfc80ae",  # Benjamin Czaczkes
]
DEFAULT_NAMES = [
    "Alfred Czaczkes",
    "Benjamin Czaczkes",
]


def _get_env() -> tuple[str, str]:
    server = os.environ.get("IMMICH_SERVER")
    key = os.environ.get("IMMICH_API_KEY")
    if not server or not key:
        sys.exit("ERROR: set IMMICH_SERVER and IMMICH_API_KEY in the environment.")
    return server.rstrip("/"), key


def get_people(base_url: str, key: str) -> list[dict]:
    r = httpx.get(
        f"{base_url}/people",
        headers={"X-API-Key": key},
        timeout=30.0,
    )
    if r.status_code >= 400:
        sys.exit(f"ERROR: GET /people failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def get_faces(base_url: str, key: str) -> list[dict]:
    """GET /faces returns all faces (no id param -> all)."""
    r = httpx.get(
        f"{base_url}/faces",
        headers={"X-API-Key": key},
        timeout=30.0,
    )
    if r.status_code >= 400:
        sys.exit(f"ERROR: GET /faces failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def main() -> None:
    base_url, key = _get_env()

    person_ids = DEFAULT_PERSON_IDS
    names = [n.lower() for n in DEFAULT_NAMES]

    people = get_people(base_url, key)
    faces = get_faces(base_url, key)

    print(f"Server returned {len(people)} people, {len(faces)} faces.\n")

    # --- Check people ---
    found_people = []
    for p in people:
        pid = (p.get("id") or "").lower()
        pname = (p.get("name") or "").lower()
        if pid in {i.lower() for i in person_ids} or pname in names:
            found_people.append(p)

    # --- Check faces carrying those person IDs ---
    found_faces = []
    for f in faces:
        fpid = (f.get("personId") or f.get("person_id") or "").lower()
        if fpid in {i.lower() for i in person_ids}:
            found_faces.append(f)

    print("=== PEOPLE ===")
    if found_people:
        print(f"  FOUND {len(found_people)} target people still present:")
        for p in found_people:
            print(f"    - id={p.get('id')} name={p.get('name')!r}")
    else:
        print("  OK: none of the target people/names remain.")

    print("\n=== FACES ===")
    if found_faces:
        print(f"  FOUND {len(found_faces)} faces still referencing target person IDs:")
        for f in found_faces:
            print(f"    - id={f.get('id')} personId={f.get('personId') or f.get('person_id')}")
    else:
        print("  OK: no faces reference the target person IDs.")

    print("\n=== VERDICT ===")
    if found_people or found_faces:
        print("  NOT CLEARED — traces remain on the server.")
        sys.exit(1)
    print("  CLEARED — people and their faces are fully gone.")


if __name__ == "__main__":
    main()
