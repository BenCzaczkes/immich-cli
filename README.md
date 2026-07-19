# immich-cli

<!-- CI status badge (replace OWNER/repo with the GitHub slug if/when the repo is public) -->
[![CI](https://github.com/BenCzaczkes/immich-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/BenCzaczkes/immich-cli/actions/workflows/ci.yml)

A **standalone command-line tool** to upload assets (photos/videos) to an
Immich server, attaching complete metadata via an XMP sidecar. Built on
[HTTPX](https://www.python-httpx.org/) and [Click](https://click.palletsprojects.com/).

This is an independent project — it does **not** import the desktop app. The
upload protocol and XMP format follow `docs/cli-upload-baseline.md` in the
desktop app repo.

## Features

- Upload a file to `POST /assets` with `X-API-Key` auth.
- Generate a standards-compliant XMP sidecar (stdlib `xml.etree`, no PyQt)
  carrying tags, description, GPS, people, rating, and face regions.
- Apply tags client-side after upload (`GET /tags` → `POST /tags` →
  `PUT /assets/bulk`), because Immich does **not** read tags from the sidecar.
- Description and GPS are imported by Immich natively from the sidecar.
- Faces ride in the sidecar as `mwg-rs:Regions`.

## Install (uv)

```bash
uv sync
```

## Usage

```bash
# Upload a single image with inline metadata
immich-cli upload IMG_0421.jpg \
    --server https://immich.example.com \
    --api-key "$IMMICH_API_KEY" \
    --description "Sunset over the lake" \
    --tag Vacation --tag "Nature/Flowers/Roses" \
    --gps 48.8566,2.3522 \
    --rating 5

# Upload using a .meta.json sidecar (MetaExport-shaped JSON)
immich-cli upload photo.jpg --meta-json photo.jpg.meta.json

# Use a pre-existing .xmp sidecar instead of generating one
immich-cli upload photo.jpg --xmp photo.xmp
```

Set `IMMICH_SERVER` and `IMMICH_API_KEY` env vars to skip the flags.

## Development

```bash
uv sync --all-extras
uv run pytest            # offline unit tests (XMP generation)
uv run ruff check .
```

## Layout

```
src/immich_cli/
  models.py   # Metadata dataclass (portable MetaExport)
  xmp.py      # stdlib XMP sidecar generator
  client.py   # ImmichClient: upload + tag application (HTTPX)
  cli.py      # Click command(s)
  __main__.py # `python -m immich_cli`
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). (This repository is private for the
time being; contribution is by invitation.)
