"""Click command-line interface for immich-cli."""

from __future__ import annotations

import json
import logging
import os
import sys
import zipfile
from pathlib import Path

import click

from immich_cli.client import ImmichClient, ImmichError
from immich_cli.logging_setup import configure_logging, redact_api_key
from immich_cli.meta_export import generate_meta_export
from immich_cli.models import Metadata

log = logging.getLogger(__name__)


def _echo_command_line() -> None:
    """Log the exact invocation (API key redacted) for debugging.

    Echoes ``sys.argv`` as a single line so misbehaviour is reproducible from
    the trace. The key is masked wherever it appears (``--api-key VALUE`` or
    the ``IMMICH_API_KEY`` env var, if the option was omitted on the CLI).
    """
    argv = list(sys.argv)
    masked = redact_api_key(argv)
    env_key = os.environ.get("IMMICH_API_KEY")
    env_note = "" if env_key is None else " [IMMICH_API_KEY env present]"
    log.debug("command line:%s %s", " ".join(masked), env_note)


def _help_requested() -> bool:
    """Return True if a --help / -h flag appears anywhere in the CLI args.

    Lets `upload --help` (or `immich-cli --help`) render without requiring
    credentials, which are only needed to actually run an upload.
    """
    return any(arg in ("--help", "-h") for arg in sys.argv[1:])


def _discover_xmp(file: Path) -> Path | None:
    """Find a sidecar XMP next to ``file``.

    Tries the image convention ``<file.name>.xmp`` (e.g. ``19580128.jpg.xmp``)
    first, then the bare-stem form ``<stem>.xmp`` (e.g. ``19580128.xmp``).
    Returns the first existing path, else ``None``.
    """
    candidates = [file.with_name(file.name + ".xmp"), file.with_suffix(".xmp")]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


@click.group()
@click.option(
    "--server",
    envvar="IMMICH_SERVER",
    help="Immich server base URL (e.g. https://immich.example.com/api). "
         "Env: IMMICH_SERVER.",
)
@click.option(
    "--api-key",
    envvar="IMMICH_API_KEY",
    help="Immich API key (X-API-Key). Env: IMMICH_API_KEY.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Mirror the full debug trace to the console (stderr).",
)
@click.option(
    "--log",
    "log_file",
    type=click.Path(dir_okay=False, path_type=str),
    default=None,
    help="Write the full debug trace to this file.",
)
@click.pass_context
def main(
    ctx: click.Context,
    server: str | None,
    api_key: str | None,
    verbose: bool,
    log_file: str | None,
) -> None:
    """Upload assets (with XMP metadata) to an Immich server.

    ENVIRONMENT VARIABLES (alternative to the --server / --api-key flags):
      IMMICH_SERVER   server base URL, e.g. https://immich.example.com/api
      IMMICH_API_KEY  Immich API key (sent as the X-API-Key header)

    OPTION PLACEMENT:
      Global options (--server, --api-key, --verbose, --log) go BEFORE the
      command. Command options (--album, --tag, --description, --gps, ...) go
      AFTER the command and its FILE argument. Example shows the split.

    EXAMPLE:
      immich-cli --log trace.log \
          --server https://immich.example.com/api --api-key YOUR_KEY \
          upload photo.jpg \
          --description "Holiday" --tag Family --tag "Places/Paris" --gps 48.85,2.35

    DEBUG TRACING (opt-in, silent by default):
      --verbose   mirror the full debug trace to the console (stderr)
      --log FILE  write the full debug trace to FILE (API key redacted)
      On startup the exact command line is echoed to the trace with the
      API key masked, for reproducible debugging.
    """
    configure_logging(verbose=verbose, log_file=log_file)
    _echo_command_line()
    # Credentials are required to actually run a command, but not to show
    # help. Let --help (group or subcommand) render without them.
    help_requested = bool(ctx.params.get("help")) or _help_requested()
    if not help_requested and (not server or not api_key):
        raise click.UsageError(
            "Both --server and --api-key are required "
            "(or set IMMICH_SERVER / IMMICH_API_KEY)."
        )
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    ctx.obj["api_key"] = api_key
    log.debug("CLI start: server=%s verbose=%s log_file=%s", server, verbose, log_file)


@main.command("upload")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--meta-json", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="MetaExport-shaped .meta.json to load metadata from.")
@click.option("--xmp", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Use this pre-existing .xmp sidecar instead of generating one.")
@click.option("--description", help="Asset description (dc:description).")
@click.option("--tag", "tags", multiple=True, help="Tag to apply (repeatable). Hierarchical: A/B.")
@click.option("--album", "albums", multiple=True, help="Album name (repeatable). Created if missing, then the asset is added to it.")
@click.option("--person", "people", multiple=True, help="Person name (iptc-core:PersonInImage).")
@click.option("--gps", help="GPS as 'lat,lon' (decimal degrees), e.g. 48.8566,2.3522.")
@click.option("--rating", type=click.IntRange(-1, 5), default=None, help="Star rating -1..5.")
@click.option("--favorite", is_flag=True, help="Mark as favorite.")
@click.option("--archive", is_flag=True, help="Upload as archived (visibility=archive).")
@click.option("--no-tags", is_flag=True, help="Skip client-side tag application.")
@click.pass_context
def upload(
    ctx: click.Context,
    file: Path,
    meta_json: Path | None,
    xmp: Path | None,
    description: str | None,
    tags: tuple[str, ...],
    albums: tuple[str, ...],
    people: tuple[str, ...],
    gps: str | None,
    rating: int | None,
    favorite: bool,
    archive: bool,
    no_tags: bool,
) -> None:
    """Upload FILE to Immich, attaching metadata via an XMP sidecar.

    OPTION PLACEMENT: every option below is a COMMAND option and must appear
    AFTER the command and its FILE argument, e.g.:
        immich-cli upload PHOTO.JPG --album "Trip" --tag Family
    The connection options (--server, --api-key) and debug tracing (--verbose,
    --log) are GLOBAL options and go BEFORE the `upload` command instead.
    Run `immich-cli --help` for the global options and a full example.
    """
    log.debug("upload command: file=%s meta_json=%s xmp=%s", file, meta_json, xmp)
    if xmp is None:
        discovered = _discover_xmp(file)
        if discovered is not None:
            xmp = discovered
            log.debug("auto-discovered XMP sidecar: %s", xmp)
        else:
            log.debug("no XMP sidecar found next to %s (tried %s.jpg.xmp / .xmp)",
                      file, file.stem)
    metadata = _build_metadata(
        meta_json, description, tags, albums, people, gps, rating, favorite, archive
    )
    log.debug(
        "metadata: description=%r tags=%s albums=%s people=%s gps=(%s,%s) "
        "rating=%s favorite=%s archive=%s face_regions=%d",
        metadata.description,
        metadata.tags,
        metadata.albums,
        metadata.people,
        metadata.gps_lat,
        metadata.gps_lon,
        metadata.rating,
        metadata.is_favorite,
        metadata.is_archived,
        len(metadata.face_regions),
    )

    try:
        with ImmichClient(ctx.obj["server"], ctx.obj["api_key"]) as client:
            result = client.upload(file, metadata=metadata, sidecar_path=xmp)
            asset_id = result.get("assetId") or result.get("id")
            duplicate = result.get("duplicate", False)
            log.debug("upload result: %s", result)
            click.echo(f"Uploaded: {file.name} -> assetId={asset_id} duplicate={duplicate}")

            if not no_tags and metadata.tags:
                client.apply_tags(asset_id, list(metadata.tags))
                log.debug("applied %d tag(s)", len(metadata.tags))
                click.echo(f"Applied {len(metadata.tags)} tag(s).")

            if metadata.albums:
                client.apply_albums(asset_id, list(metadata.albums))
                log.debug("applied %d album(s)", len(metadata.albums))
                click.echo(f"Added to {len(metadata.albums)} album(s): {', '.join(metadata.albums)}")

            if metadata.is_favorite or metadata.rating is not None or metadata.is_archived:
                client.apply_flags(asset_id, metadata)
                log.debug("applied flags (favorite/rating/archive)")
    except ImmichError as exc:
        log.error("upload failed: %s", exc)
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    log.debug("upload command finished")


def _build_metadata(
    meta_json: Path | None,
    description: str | None,
    tags: tuple[str, ...],
    albums: tuple[str, ...],
    people: tuple[str, ...],
    gps: str | None,
    rating: int | None,
    favorite: bool,
    archive: bool,
) -> Metadata:
    """Merge a .meta.json file (if any) with inline CLI flags."""
    meta = Metadata()
    if meta_json is not None:
        meta = Metadata.from_dict(json.loads(Path(meta_json).read_text(encoding="utf-8")))

    if description:
        meta.description = description
    if tags:
        meta.tags = list(tags)
    if albums:
        # Albums are written into the sidecar for round-trip; full album
        # application is a v1 stub (see docs/cli-upload-baseline.md §6).
        meta.albums = list(albums)
    if people:
        meta.people = list(people)
    if gps:
        try:
            lat_s, lon_s = gps.split(",")
            meta.gps_lat = float(lat_s.strip())
            meta.gps_lon = float(lon_s.strip())
        except ValueError as exc:
            raise click.BadParameter(f"--gps must be 'lat,lon': {exc}") from exc
    if rating is not None:
        meta.rating = rating
    if favorite:
        meta.is_favorite = True
    if archive:
        meta.is_archived = True
    return meta


def _extract_archive(zip_path: Path, out_dir: Path) -> Path:
    """Extract a downloaded Immich archive (zip) and return the image path.

    Immich's ``/download/archive`` returns a zip; for a single asset it
    contains one image file. We extract everything into *out_dir* and return
    the first non-meta file found (images/videos). If the zip holds more than
    one candidate we log the full entry list and still return the first.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        log.debug("download archive entries: %s", names)
        zf.extractall(out_dir)
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
                  ".tif", ".tiff", ".heic", ".heif",
                  ".mp4", ".mov", ".avi", ".mkv", ".webm"}
    candidates = [
        out_dir / n for n in names
        if Path(n).suffix.lower() in image_exts and not Path(n).name.startswith("__MACOSX")
    ]
    if not candidates:
        # Fall back to any file that isn't an OS helper.
        candidates = [
            out_dir / n for n in names
            if not n.startswith("__MACOSX") and not n.endswith("/")
        ]
    if not candidates:
        raise ImmichError(f"Download archive contained no files: {names}")
    if len(candidates) > 1:
        log.warning("download archive had %d files; using %s", len(candidates), candidates[0])
    return candidates[0]


@main.command("download")
@click.argument("asset_id", type=str)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("downloads"),
    show_default=True,
    help="Directory to write the extracted asset + .meta.json + .xmp into.",
)
@click.pass_context
def download(ctx: click.Context, asset_id: str, out_dir: Path) -> None:
    """Download ASSET_ID and write its metadata locally.

    Pulls a single asset from Immich (as a zip), extracts the image, then
    fetches its full metadata (asset object, faces, albums) and writes:

      * <image>.<ext>.meta.json  -- rich, server-shaped metadata
      * <image>.<ext>.xmp         -- sidecar (stars + people) when present

    This mirrors the desktop app's download structure and is the tool used to
    inspect what Immich actually stored (e.g. why uploaded faces report 0).

    OPTION PLACEMENT: --out is a COMMAND option (after the asset id). The
    connection/debug options (--server, --api-key, --verbose, --log) are
    GLOBAL and go BEFORE the `download` command.
    """
    try:
        with ImmichClient(ctx.obj["server"], ctx.obj["api_key"]) as client:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            zip_path = out_dir / f"{asset_id}.zip"
            log.debug("download: fetching archive for %s", asset_id)
            client.download_archive(asset_id, zip_path)
            click.echo(f"Downloaded archive: {zip_path}")

            image_path = _extract_archive(zip_path, out_dir)
            log.debug("download: extracted image -> %s", image_path)
            click.echo(f"Extracted asset: {image_path.name}")

            asset_data = client.get_asset(asset_id)
            faces_data = client.get_faces(asset_id)
            albums_data = client.get_albums_for_asset(asset_id)
            log.debug(
                "download: asset type=%s faces=%d albums=%d",
                asset_data.get("type"), len(faces_data), len(albums_data),
            )

            meta_path = generate_meta_export(
                asset_id, asset_data, image_path, faces_data, albums_data
            )
            click.echo(f"Wrote metadata: {meta_path}")
            click.echo(
                f"Summary: faces={len(faces_data)} albums={len(albums_data)} "
                f"rating={asset_data.get('exifInfo', {}).get('rating')} "
                f"favorite={asset_data.get('isFavorite')}"
            )
    except ImmichError as exc:
        log.error("download failed: %s", exc)
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    log.debug("download command finished")


if __name__ == "__main__":  # pragma: no cover
    main()
