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

- People link enforcement (PersonInImage is stored in sidecar/XMP; not yet
  linked to Immich people on the server).
- **Faces ingestion fix (upload-side):** Immich/another source locates faces —
  we only upload them. Evidence gathered via the download command
  (downloads/19580128.jpg.meta.json): faces ARE stored server-side
  (face_regions=2, valid PIXEL boxes, source_type=machine-learning, named
  people). rating=5 / favorite=True / album='My Album' all round-trip. So the
  `faces: 0` bug is on the UPLOAD / XMP-WRITE side, not download.
  **CORRECTED (download investigation):** the download-side XMP is actually
  MWG-correct and round-trips fine. The asymmetry: `generate_mwg_regions`
  (xmp.py) sets `AppliedToDimensions` = the ORIGINAL asset size (e.g. 2560×3412)
  but normalizes each box by the face's per-region `image_width/height`, which
  on download is the 1440×1919 RESIZED PREVIEW Immich ran ML on. The downloaded
  .meta.json keeps raw pixel boxes tied to 1440×1919; the .xmp re-normalizes to
  2560×3412. Both internally consistent. So the upload XMP is spec-correct —
  the `faces: 0` gap is almost certainly SERVER-SIDE: Immich's ML face pipeline
  detects on the 1440 preview and stores faces against that preview size, and
  on upload either ignores MWG-RS regions from sidecars or can't reconcile
  them against the preview it processes. Open question: should
  `AppliedToDimensions` match the PREVIEW (1440×1919), not the original?
- Asset delete command (to clean up test uploads).

## Recently built

- **Albums application**: `--album NAME` (repeatable) now resolves via
  `ImmichClient.apply_albums` — `GET /albums` lookup (case-insensitive),
  `POST /albums` create if missing, `PUT /albums/{id}/assets` to add. Single-
  image scope only (no batch/race handling yet). Mirrors desktop AlbumResolver.
- **Download command** (`immich-cli download ASSET_ID [--out DIR]`, default
  `./downloads`): `POST /download/archive` (zip) → extract image via stdlib
  `zipfile` → `GET /assets/{id}` + `GET /faces?id=` + `GET /albums?assetId=`
  → write `<image>.<ext>.meta.json` (+ `<image>.<ext>.xmp` sidecar for
  stars/people) via `meta_export.generate_meta_export`. Ported from the
  desktop app's `core/meta_export.py` (same `MetaExport` v1 schema + the
  "box tipping" guard that drops degenerate/out-of-bounds face boxes).
  New module `src/immich_cli/meta_export.py` (uses CLI's `xmp.generate_xmp_sidecar`).
  Use this to investigate the faces gap on the two real photos.
- **Windows `.exe` build: working via Nuitka** (replaces PyInstaller, which
  was dropped). `build_windows.py` compiles `src/immich_cli` with
  `--python-flag=-m` (runs `immich_cli.__main__`) → native `immich-cli.exe`.
  Dev dep is `nuitka[onefile]` (pulls zstandard for compression). `[tool.nuitka]`
  in pyproject.toml + `docs/windows-build.md`. **Must run on Windows with MSVC**
  — Nuitka can't cross-compile a Windows exe from Linux. Verified: `__main__.exe`
  built and `--help` ran correctly; approach B (package dir + -m) adopted for
  proper `immich-cli.exe` naming.
  **Gotcha (sync staleness):** `files-to-copy.txt` is a STATIC list that the
  Windows copy script reads. If it predates a new module, that module is NOT
  copied and `uv run` (or the exe) fails with `ModuleNotFoundError`
  (e.g. `immich_cli.meta_export` was missing until the list was regenerated).
  Fix: regenerate the list before each sync. `gen-files.ps1` (in repo root)
  collects all project `.py` files and writes `files-to-copy.txt` — run it
  (or have winclirun.ps1 call it) before copying. The Nuitka `.exe` is also a
  static compile, so after `src/` changes rebuild it with
  `uv run ./build_windows.py` if you use the exe; for testing, `uv run` uses
  live source and needs no rebuild. `downloads/` is gitignored (test output).

## Faces investigation — state + next experiment (2026-07-20)

- **Two test images deleted + people cleared (VERIFIED CLEAN):** the user
  deleted `19580128.jpg` and `19580328.jpg` (asset IDs
  `00b19997-969d-42c8-b320-03a215338044`, `02cee462-531e-475c-97d0-c50eba4f9518`)
  and their people from the server. `scripts/check_people_cleared.py` (READ-ONLY;
  checks `GET /people` + `GET /faces` for the two person IDs/names) printed
  nothing found → CLEARED. Person IDs:
  - Alfred Czaczkes  → `020b92cd-ac8b-487a-b726-e79706fc81d1`
  - Benjamin Czaczkes → `13df863a-20fb-490a-8851-734a0cfc80ae`
- **Next experiment (user running on WINDOWS):** re-upload the two .jpg files
  from `downloads/` WITH their `.xmp` sidecars, after STOPPING the server's
  background jobs (face-detection / metadata-extraction) so Immich can't
  overwrite what we send. Goal: see if `GET /faces?id={asset}` shows
  `faces > 0` and, if so, what `source_type` they carry (sidecar-ingested vs
  server ML). The user prefers to do this on Windows (can pause jobs via admin
  UI / docker pause microservices). NOTE: Linux side has no further action.
- **Experiment caveats to watch:**
  - Re-uploading the SAME .jpg (same checksum) may be deduplicated as a
    duplicate, not a fresh asset → use copies / slightly changed exports.
  - Even if faces appear, check `source_type` + whether person IDs/names match
    the sidecar, to prove the sidecar was ingested (not server ML).
  - Open dimension question: downloaded faces are stored against the 1440×1919
    preview; our upload XMP uses `AppliedToDimensions` = original (2560×3412).
    If sidecar regions ARE honored, test whether `AppliedToDimensions` should
    instead match the preview size Immich processes.
- **Ratings/stars note:** correctly captured on download — nested under
  `exif.rating` (NOT a top-level key) and exported as `<xmp:Rating>` in the
  XMP sidecar. 19580128 had rating=5 (exported); 19580328 had rating=null
  (correctly omitted). The open issue is UPLOAD-side: Immich's async
  metadata-extraction overwrites `rating` from file EXIF, so a
  `PUT /assets/{id}` rating returns null. To survive upload, the file itself
  must carry the rating (XMP `<xmp:Rating>` feeds ExifTool/Immich on ingest).
- **Useful endpoints (from OpenAPI):** `GET /people`, `GET /people/{id}`,
  `DELETE /people/{id}`, `GET /faces`, `DELETE /faces/{id}`, `GET /faces?id=`,
  `POST /download/archive`, `POST /jobs/{id}/stop` (job control — desktop app
  can stop jobs via API; on Windows the user may just pause microservices).

## Faces experiment — RESULT (2026-07-20, Windows run)

- **XMP sidecar IS ingested on upload.** User uploaded ONE of the two test
  pictures (with the `.xmp` sidecar containing normalized MWG-RS regions +
  `iptc-core:PersonInImage` names), after the `check_people_cleared.py` script
  confirmed the server was clear. With ALL jobs stopped (face generation off),
  Immich **found the faces from the sidecar** and kept their names — almost
  certainly because the names live in the XMP (`mwg-rs:Name` /
  `iptc-core:PersonInImage`), so no separate DB memory was needed.
- **DUPLICATE-FACES problem (root cause found):** user then let Immich run its
  background jobs. Immich's ML face-detection re-detected the SAME two faces
  and added **two NEW unnamed faces at the identical positions**. Result: the
  one picture now shows **4 faces (2 named-from-XMP + 2 unnamed-from-ML)** when
  it physically has only 2. Immich does NOT dedupe sidecar-provided regions
  against its own ML detection — it treats them as independent. (Immich isn't
  "confused"/erroring; it just has redundant face records.)
- **Next step user is taking:** re-download the asset to inspect the
  round-trip (does the download now return 4 face_regions? do the named ones
  carry `source_type` distinguishing sidecar vs ML?). Not yet observed.
- **Implication for the `faces: 0` mystery:** SOLVED on the ingest question —
  normalized MWG-RS regions in the sidecar DO get ingested (when jobs are
  stopped, at least). The remaining pain is Immich's ML re-detection creating
  duplicates, not our XMP being ignored. So the earlier "server ignores XMP"
  hypothesis is WRONG; the real issue is dedupe/merge on Immich's side.
- **Open dimension question still stands:** sidecar used
  `AppliedToDimensions` = original (2560×3412) and was ingested fine, so the
  preview-vs-original mismatch did NOT block ingestion this time. Keep watching
  whether ML-generated boxes (preview-sized) vs sidecar boxes (original-sized)
  cause coordinate drift on the 4-face download.

## Design note — XMP is source of truth, not the JSON export

- **User directive:** prefer keeping our metadata in the **XMP sidecar**, NOT
  the JSON `.meta.json` export. "We need a database of some sort, but one that
  can go UP to Immich — and from what I see, all the JSON gives us is
  heartache." The JSON (`MetaExport` v1) is useful for inspection/round-trip
  debugging but should NOT be the system of record we rely on.
- **Rationale observed:** the XMP sidecar is what Immich actually ingests
  (faces + names came through from XMP alone). The JSON is a derived snapshot
  that doesn't round-trip cleanly and causes more confusion than value as a
  store. So: treat XMP as canonical; JSON = debug/export only.
- **Action item (not yet done):** reconsider whether `meta_export` /
  `--meta-json` should remain a primary output, or be demoted to a debug aid.
  No code change yet — note for next session.
