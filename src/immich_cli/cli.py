"""Click command-line interface for immich-cli."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from immich_cli.client import ImmichClient, ImmichError
from immich_cli.models import Metadata


@click.group()
@click.option(
    "--server",
    envvar="IMMICH_SERVER",
    help="Immich server base URL (e.g. https://immich.example.com/api).",
)
@click.option(
    "--api-key",
    envvar="IMMICH_API_KEY",
    help="Immich API key (X-API-Key). Defaults to $IMMICH_API_KEY.",
)
@click.pass_context
def main(ctx: click.Context, server: str | None, api_key: str | None) -> None:
    """Upload assets (with XMP metadata) to an Immich server."""
    if not server or not api_key:
        raise click.UsageError(
            "Both --server and --api-key are required "
            "(or set IMMICH_SERVER / IMMICH_API_KEY)."
        )
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    ctx.obj["api_key"] = api_key


@main.command("upload")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--meta-json", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="MetaExport-shaped .meta.json to load metadata from.")
@click.option("--xmp", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Use this pre-existing .xmp sidecar instead of generating one.")
@click.option("--description", help="Asset description (dc:description).")
@click.option("--tag", "tags", multiple=True, help="Tag to apply (repeatable). Hierarchical: A/B.")
@click.option("--album", "albums", multiple=True, help="Album name (stored in sidecar; v1 stub).")
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
    """Upload FILE to Immich, attaching metadata via an XMP sidecar."""
    metadata = _build_metadata(
        meta_json, description, tags, albums, people, gps, rating, favorite, archive
    )

    try:
        with ImmichClient(ctx.obj["server"], ctx.obj["api_key"]) as client:
            result = client.upload(file, metadata=metadata, sidecar_path=xmp)
            asset_id = result.get("assetId") or result.get("id")
            duplicate = result.get("duplicate", False)
            click.echo(f"Uploaded: {file.name} -> assetId={asset_id} duplicate={duplicate}")

            if not no_tags and metadata.tags:
                client.apply_tags(asset_id, list(metadata.tags))
                click.echo(f"Applied {len(metadata.tags)} tag(s).")

            if metadata.is_favorite or metadata.rating is not None or metadata.is_archived:
                client.apply_flags(asset_id, metadata)
    except ImmichError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


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


if __name__ == "__main__":  # pragma: no cover
    main()
