# Known Issues — Immich ingestion behavior

These were discovered during the live-upload smoke test against a real Immich
server (run from the CLI). They are **server-side Immich behaviors**, not bugs
in the CLI's request construction (except where noted). Tracked here so we can
investigate why metadata does not always land as expected.

**Context:** the desktop app hit the same class of problems with the Immich API
(see `docs/IMMICH_FACE_XMP_NOTES.md` in the desktop repo). This is not a smooth
edge — Immich's metadata handling is inconsistent across field types.

## 1. Faces (MWG regions) are not ingested — OPEN

- The CLI generates a valid XMP sidecar with `mwg-rs:Regions` (named regions,
  normalized `stArea` coordinates, `AppliedToDimensions`). Verified well-formed
  and parses.
- After upload, the asset reports `faces: 0` on the server.
- GPS, people, and description (sometimes) DO ingest from the same sidecar, so
  the sidecar is being read — but face regions specifically are dropped.
- **To investigate:** confirm the exact MWG schema Immich's exiftool ingest
  expects (region naming, `rdf:parseType` usage, whether `exif:GPS*` vs
  `mwg-rs` wins), and whether a separate `POST /faces` is required despite the
  desktop app having removed that path. Repro: upload an image with
  `face_regions` set and check `GET /assets/{id}` `.faces`.

## 2. `description` and `rating` are overwritten by metadata extraction — OPEN

- Setting `description` / `rating` via `PUT /assets/{id}` returns `200` but the
  values come back `null` after Immich's async **metadata-extraction job**
  finishes.
- Hypothesis: the extraction job overwrites `description` and `rating` from the
  file's EXIF/XMP. Our test images have no EXIF description/rating, so they
  reset to null. GPS and people (also XMP-sourced) survive, suggesting Immich
  reads GPS/people from the sidecar but NOT description/rating.
- API-set `isFavorite` is a user flag and is NOT touched by extraction → it
  persists correctly.
- **To investigate:** test with a real photo that has EXIF `ImageDescription`
  and `rating` to see if extraction preserves them; determine whether Immich
  reads `dc:description` / `xmp:Rating` from the sidecar at all. Repro: upload
  with `description` + `rating`, poll `GET /assets/{id}` at 3/8/15s.

## 3. Metadata-extraction race — mitigation

- Reads immediately after upload (or even after several seconds) can return
  partially-extracted state. `tags` applied client-side via `PUT /tags/assets`
  were flaky on a metadata-rich asset but **reliable** on a minimal asset with a
  longer poll (verified present at 5/10/20s).
- **Mitigation in CLI:** none yet. If we need deterministic verification, poll
  `GET /assets/{id}` until `exifInfo` is populated, or accept eventual
  consistency. Not a CLI bug.

## What works (verified)

- `POST /assets` auth + upload (minimal and metadata-rich).
- XMP sidecar ingested for **GPS** and **people**.
- Client-side **tag** application via `PUT /tags/assets` (fixed — was wrongly
  calling `PUT /assets/bulk`; see commit that added `tests/test_client.py`).
- Client-side **isFavorite** via `PUT /assets/{id}`.

## Test assets created during smoke test

Named like `immich-cli smoke test - please delete` / `immich-cli-tagcheck`.
These remain on the server and should be deleted manually (the CLI has no
delete command yet).
