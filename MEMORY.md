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

## Faces experiment — RESULT (2026-07-20, Windows runs)

### Run 1 (jobs stopped, then all jobs released) — EARLIER, PARTIALLY WRONG

- **Earlier read was INCORRECT.** First Windows run: uploaded one picture with
  the XMP sidecar, jobs stopped, saw faces; then released jobs and saw 4 faces
  (2 named + 2 unnamed). We concluded "XMP sidecar IS ingested when jobs are
  stopped." **Run 2 below disproves that** — see correction.
- **DUPLICATE-FACES problem (still valid):** releasing jobs made Immich's ML
  face-detection re-detect the same two faces as 2 NEW unnamed faces at the
  identical positions → 4 faces on a 2-face picture. Immich does NOT dedupe
  sidecar-provided regions against its own ML detection. Root cause of the
  duplicates is the ML re-detection, independent of the sidecar.

### Run 2 (CLEAN: ALL 9 job queues paused) — 2026-07-20, trace.log

- Uploaded `19580128.jpg` WITH auto-discovered `.xmp` sidecar (full correct
  XMP: tags, album, GPS, xmp:Rating=5, description, PersonInImage Alfred+
  Benjamin, MWG-RS regions AppliedToDimensions=2560×3412). Server 201
  `{"id":"6dd908df-...","status":"created"}`. Then (with ALL jobs paused)
  downloaded it. **Result: asset came back EMPTY:**
  - `GET /assets/{id}` exifInfo: exifImageWidth/Height NULL, dateTimeOriginal
    NULL, lat/long NULL, description "", rating NULL, city/state/country NULL;
    asset `width`/`height` NULL; `tags: []`, `people: []`; `resized: true`,
    `hasMetadata: true`.
  - `GET /faces?id=` → `[]` (0 faces). `GET /albums?assetId=` → `[]` (0 albums).
- **CORRECTION of Run-1 conclusion:** the XMP sidecar is NOT ingested
  synchronously on upload. With all jobs paused, NOTHING is extracted — not
  even the sidecar. So sidecar (and EXIF) ingestion is done by BACKGROUND
  JOBS, not at upload time. Run 1's "faces seen with jobs stopped" must have
  had a job still running (or were ML faces from a prior state). **The sidecar
  path is `metadataExtraction` / `SidecarWrite`, which only run as jobs.**
- **Implication:** there is NO way to make Immich apply the sidecar without
  running at least the metadata/sidecar jobs. Pausing everything = empty asset.
  Pausing only ML (faceDetection/facialRecognition/smartSearch) but letting
  metadataExtraction+SidecarWrite run should ingest the sidecar's named faces
  + tags/GPS/rating WITHOUT adding ML unnamed duplicates.

### Run 3 (DONE, DEFINITIVE — blank server): metadata extraction ON, ML OFF

- User physically deleted + recreated the Immich server (truly blank, no prior
  memory). Uploaded `New/19580128.jpg` WITH sidecar (asset `6dd908df-...`), then
  released ONLY `metadataExtraction` (sidecar ingest) but kept
  faceDetection/facialRecognition/smartSearch PAUSED. Re-downloaded.
- **RESULT (downloads/19580128.jpg.meta.json, trace 03:09):** sidecar FULLY
  ingested — width/height 2560×3412, date, GPS, description, **rating=5**,
  tags [Benjamin, Alfred] (server-created), people [Alfred+Benjamin]. `GET
  /faces` → **4 faces, ALL `sourceType:"exif"`** linked to the named people
  (NO ML unnamed faces — prediction confirmed). BUT each sidecar face is
  **DOUBLED**: Alfred box (613,627)->(1340,1671) appears twice, Benjamin
  (1514,887)->(2033,1557) twice. Source sidecar had exactly 2 regions, server
  returned 4 → **Immich doubles sidecar faces server-side** (exif-source dup,
  not ML). Boxes correctly original-sized (2560×3412), matching sidecar
  normalized centers. albums=[] (no --album run this time).
- **Conclusion:** the XMP sidecar IS the source of truth and IS ingested (by
  metadataExtraction/sidecar job, not synchronously). Faces stored as exif,
  named, correct coords. Remaining blocker: **Immich duplicates each sidecar
  face** (2 real -> 4 stored). Original-sized AppliedToDimensions is correct
  (no switch to preview needed). Full narrative in
  docs/faces-experiment-report.md.
- **Key takeaway:** `faces: 0` was never "server ignores XMP" — it was (a)
  sidecar needs the metadata/sidecar job to run, and (b) when ML also runs it
  adds MORE unnamed dupes. The pure-sidecar path now shows 4 faces but all
  named/exif, just doubled by Immich.

### Run 4 (DONE): ALL jobs released -> 6 faces

- After Run 3 the user released ALL remaining queues (facialRecognition,
  faceDetection, smartSearch, ...). ML ran; same asset re-downloaded (trace
  03:26). `GET /faces` -> **6 faces**: the 4 exif (Alfred×2, Benjamin×2, same
  IDs/boxes as Run 3, PERSISTED) + **2 NEW machine-learning** faces, unnamed,
  on the 1440×1919 preview — Alfred (345,353)->(754,940), Benjamin
  (852,499)->(1144,876). Those ML boxes are IDENTICAL to the very first
  `00b19997-...` download's boxes (Immich's preview-size ML detection). So ML
  re-found the 2 real faces as 2 new unnamed people; the exif set was NOT
  re-doubled. Net: 2 real faces -> **6 stored** (4 exif-named-doubled + 2
  ML-unnamed). `people` grew to 4 (2 named + 2 unnamed ML). Tags/rating/GPS/
  description still correct. This matches the user's hunch exactly.
- **Full picture:** 2 real faces become 6 = Immich doubles the sidecar regions
  once (exif) AND ML adds one unnamed copy each (preview-sized). Neither side
  de-dupes. The exif-doubling is the sidecar-ingestion bug to chase; the ML
  additions are expected Immich behaviour (no merge with exif faces).
- **Trace file:** `trace.log` in repo root captures Run 2 (upload + download
  with all jobs paused). Note the downloaded `.meta.json` written on Windows is
  NOT in this Linux repo (the old `downloads/19580128.jpg.meta.json` here is the
  earlier 2026-07-19 Linux download, asset `00b19997-...`, not Run 2's
  `6dd908df-...`).
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
