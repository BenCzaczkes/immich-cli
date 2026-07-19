# immich-cli — Project Memory

**What this is:** A standalone, uv-managed command-line tool to upload assets
(photos/videos) to an Immich server with an XMP sidecar and client-side tag
application. Built on **HTTPX** + **Click**. It is **independent** of the
`immich-desktop` app (no PyQt import). Python `>=3.12,<3.13`.

**Why this file exists:** a focused memory for THIS project so a fresh session
can read `immich-cli/MEMORY.md` and continue without re-deriving context. It is
deliberately separate from the desktop app's `memories/` and `.pi/` memory.

---

## Quick orientation

- Repo: `https://github.com/BenCzaczkes/immich-cli` (public; was private, may
  be toggled). Local clone at `/workspace/immich-cli/`.
- Layout: `src/immich_cli/` → `models.py` (Metadata + FaceRegion), `xmp.py`
  (stdlib-only XMP sidecar generator), `client.py` (ImmichClient, HTTPX),
  `cli.py` (Click commands), `logging_setup.py` (tracing), `__main__.py`.
- Tests: `tests/test_xmp.py` (XMP generation), `tests/test_client.py`
  (tag endpoint wiring, mocked transport). Offline only.
- Docs: `docs/cli-upload-baseline.md` (wire protocol + portable XMP),
  `docs/KNOWN_ISSUES.md` (Immich ingestion gaps).

## Commands

```bash
uv sync                       # install
uv run pytest -q              # 10 offline tests
uv run ruff check src/ tests/ # lint
immich-cli upload FILE --server URL --api-key KEY [--description --tag --gps --rating --favorite --meta-json --xmp --no-tags]
immich-cli --verbose upload ...          # trace to console
immich-cli --log trace.log upload ...    # trace to file (both composable)
```
Env vars: `IMMICH_SERVER`, `IMMICH_API_KEY` (avoid passing key on command line).

## Key decisions / history

- **Tracing:** stdlib `logging` + HTTPX request/response event hooks. Flags
  `--verbose` (console) and `--log FILE` (file), both DEBUG, silent by default.
  Body policy: **text/JSON/XMP logged in full; binary (image/video/multipart)
  logged as head + size only**. `X-API-Key` header is **redacted** in logs.
  Generated XMP sidecar logged as text in full.
- **Tag application bug (fixed):** `apply_tags` must call `PUT /tags/assets`
  with `{"tagIds":[...],"assetIds":[...]}`. An earlier wrong call to
  `PUT /assets/bulk` with `{"tags":...}` 400'd (`Invalid UUID`). Regression
  tests added in `tests/test_client.py`.
- **Float lint fix:** tests use `pytest.approx` for GPS floats (ruff SIM113).
- **Baseline doc:** `docs/cli-upload-baseline.md` in the DESKTOP repo is the
  protocol reference this project was scaffolded from.
- **CI:** `.github/workflows/ci.yml` — `astral-sh/setup-uv`, ruff + pytest,
  triggers on push/PR to `main`.

## Known Immich ingestion issues (see docs/KNOWN_ISSUES.md)

Verified against a live server during smoke tests:
- **Faces (MWG regions):** uploaded but server reports `faces: 0` — NOT
  ingested. Open / needs investigation.
- **description & rating:** set via `PUT /assets/{id}` returns 200 but come
  back `null` after Immich's async metadata-extraction job overwrites them
  from the file's EXIF (our synthetic test images have none). GPS and people
  (XMP-sourced) survive; `isFavorite` (user flag) persists.
- **Extraction race:** reads right after upload can show partial state; poll
  `GET /assets/{id}` (3/8/15s) for eventual consistency. Tags applied
  client-side via `PUT /tags/assets` are reliable on a minimal asset.

## Server access (for live testing)

- From THIS Linux environment, the Immich Docker container is reachable at
  `http://host.docker.internal:2283/api` (NOT `localhost`/`127.0.0.1` — those
  are refused here). On Windows it may be `localhost:2283` depending on mapping.
- API key is provided at runtime (env var or `--api-key`); do NOT hardcode it
  in the repo or this file. The server is a temporary/safe test instance.
- Test artifacts created during smoke tests are named like
  `immich-cli smoke test - delete me` / `immich-cli-tagcheck` /
  `immich-cli-logtest` — delete manually (no delete command exists yet).

## Current git state (as of last session)

- On `main`. Local commits ahead of `origin/main` (push done from Windows):
  the tag-endpoint fix + KNOWN_ISSUES note + the tracing system are committed
  locally. Verify with `git log --oneline` / `git status` on session start.
- If you see unpushed commits, push from the environment that holds GitHub
  credentials (`git push origin main`).

## What's NOT built yet (possible next steps)

- Albums application (currently sidecar-only stub), people link enforcement.
- Faces ingestion fix (likely XMP schema or `POST /faces` investigation).
- Asset delete command (to clean up test uploads).
- PyInstaller Windows executable build.
