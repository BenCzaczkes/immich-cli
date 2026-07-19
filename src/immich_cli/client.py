"""Immich HTTP client (HTTPX) for the CLI.

Wraps the subset of the Immich API the CLI needs:

* ``POST /assets`` — upload an asset with an optional XMP sidecar.
* ``GET /tags`` / ``POST /tags`` / ``PUT /assets/bulk`` — resolve and apply
  tags client-side (Immich does NOT read tags from the sidecar).
* ``PUT /assets/{id}`` — apply favorite / rating / archive (stub-ready).

Auth is header-based (``X-API-Key``). The upload protocol follows
``docs/cli-upload-baseline.md``.
"""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

import httpx

from immich_cli.models import Metadata
from immich_cli.xmp import generate_xmp_sidecar

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# How many leading bytes of a binary (image/video) request/response body to log.
# Binary bodies are never logged in full — only this head, so the trace shows
# it is media plus the total size.
BINARY_HEAD_BYTES = 64


def _redact_headers(headers: httpx.Headers) -> str:
    """Render request/response headers for logging, redacting the API key."""
    parts = []
    for name, value in headers.items():
        if name.lower() == "x-api-key":
            parts.append(f"{name}: <redacted>")
        else:
            parts.append(f"{name}: {value}")
    return "; ".join(parts)


def _body_preview(content: bytes, content_type: str | None) -> str:
    """Return a body preview honoring the text-vs-binary policy.

    * Text / JSON / XMP: returned in full (no truncation).
    * Binary (image/video): only the first ``BINARY_HEAD_BYTES`` are shown,
      plus the total size, so the trace proves media was sent/received.
    """
    if content_type and (
        content_type.startswith("image/")
        or content_type.startswith("video/")
        or content_type.startswith("application/octet-stream")
        or content_type.startswith("multipart/")
    ):
        head = content[:BINARY_HEAD_BYTES]
        try:
            head_repr = head.decode("utf-8", "replace")
        except Exception:  # pragma: no cover
            head_repr = repr(head)
        return f"<binary {len(content)} bytes; head: {head_repr!r}>"
    # Text: decode and return in full.
    try:
        return content.decode("utf-8", "replace")
    except Exception:  # pragma: no cover
        return repr(content)


def _log_request(request: httpx.Request) -> None:
    """HTTPX request hook: trace everything going up."""
    ct = request.headers.get("content-type")
    body = request.read()
    preview = _body_preview(body, ct)
    logger.debug(
        "HTTP >>> %s %s\n  headers: %s\n  body: %s",
        request.method,
        request.url,
        _redact_headers(request.headers),
        preview,
    )


def _log_response(response: httpx.Response) -> None:
    """HTTPX response hook: trace everything coming down."""
    # Reading the body also populates ``.elapsed`` (timing) for the log line.
    body = response.read()
    ct = response.headers.get("content-type")
    preview = _body_preview(body, ct)
    try:
        elapsed_ms = response.elapsed.total_seconds() * 1000
    except RuntimeError:
        elapsed_ms = 0.0
    logger.debug(
        "HTTP <<< %s %s -> %d (%.0f ms)\n  headers: %s\n  body: %s",
        response.request.method,
        response.request.url,
        response.status_code,
        elapsed_ms,
        _redact_headers(response.headers),
        preview,
    )


class ImmichError(Exception):
    """Raised for non-2xx Immich API responses."""


class ImmichClient:
    """Minimal Immich API client for asset upload + tag application."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        """Initialize the client.

        Parameters
        ----------
        base_url:
            Server base URL, e.g. ``https://immich.example.com/api``. The
            ``/api`` suffix is required (the server serves the REST API there).
        api_key:
            Immich API key (sent as the ``X-API-Key`` header).
        timeout:
            Per-request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            event_hooks={"request": [_log_request], "response": [_log_response]},
        )

    def __enter__(self) -> ImmichClient:
        """Enter the context manager (returns self)."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit the context manager, closing the HTTPX client."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTPX client."""
        self._client.close()

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #

    def upload(
        self,
        file_path: str | Path,
        metadata: Metadata | None = None,
        sidecar_path: str | Path | None = None,
    ) -> dict:
        """Upload a single asset, generating/applying its XMP sidecar.

        Parameters
        ----------
        file_path:
            Path to the asset on disk.
        metadata:
            Optional :class:`Metadata`. If set and no ``sidecar_path`` is given,
            an XMP sidecar is generated from it (to a temp file) and uploaded as
            ``sidecarData``. Videos never get a sidecar.
        sidecar_path:
            Optional explicit ``.xmp`` sidecar to upload instead of generating
            one. Takes precedence over ``metadata``.

        Returns
        -------
        dict
            The JSON response body (``{"assetId": ..., "duplicate": ...}``).
        """
        file_path = Path(file_path)
        is_video = file_path.suffix.lower() in VIDEO_EXTENSIONS

        files: dict[str, tuple[str, bytes, str]] = {
            "assetData": (
                file_path.name,
                file_path.read_bytes(),
                "application/octet-stream",
            )
        }

        # Resolve the sidecar bytes (explicit > generated > none).
        sidecar_bytes: bytes | None = None
        sidecar_source = "none"
        if sidecar_path is not None:
            sidecar_bytes = Path(sidecar_path).read_bytes()
            sidecar_source = f"explicit:{sidecar_path}"
        elif metadata is not None and not is_video:
            xmp = generate_xmp_sidecar(str(file_path), metadata.to_xmp_dict())
            sidecar_bytes = xmp.encode("utf-8")
            sidecar_source = "generated"
        logger.debug(
            "upload: file=%s is_video=%s sidecar_source=%s sidecar_bytes=%s",
            file_path,
            is_video,
            sidecar_source,
            len(sidecar_bytes) if sidecar_bytes else 0,
        )
        # Log the generated XMP sidecar text in full (it is text metadata, not
        # binary media, so per policy it is not truncated).
        if sidecar_bytes is not None:
            logger.debug("upload: generated XMP sidecar:\n%s", sidecar_bytes.decode("utf-8"))
        if sidecar_bytes is not None and not sidecar_bytes.startswith(
            "﻿".encode()
        ):
            sidecar_bytes = "﻿".encode() + sidecar_bytes

        if sidecar_bytes is not None:
            files["sidecarData"] = (
                file_path.name + ".xmp",
                sidecar_bytes,
                "application/octet-stream",
            )

        data: dict[str, str] = {
            "fileCreatedAt": _iso_now(),
            "fileModifiedAt": _iso_now(),
            "isFavorite": "true" if (metadata and metadata.is_favorite) else "false",
            "visibility": "archive" if (metadata and metadata.is_archived) else "timeline",
            "duration": "0" if is_video else str(int(metadata.duration_ms if metadata else 0)),
        }

        r = self._client.post("/assets", files=files, data=data)
        if r.status_code >= 400:
            raise ImmichError(f"Upload failed ({r.status_code}): {r.text[:500]}")
        return r.json()

    # ------------------------------------------------------------------ #
    # Tags (client-side; Immich does NOT read tags from the sidecar)
    # ------------------------------------------------------------------ #

    def apply_tags(self, asset_id: str, tag_names: list[str]) -> None:
        """Resolve *tag_names* and link them to *asset_id*.

        Matches case-insensitively against existing server tags; creates any
        missing tags (hierarchy-aware: ``A/B`` creates ``B`` parented to ``A``),
        then bulk-links the leaf ids to the asset.

        Parameters
        ----------
        asset_id:
            The uploaded asset's id.
        tag_names:
            Tag names to resolve and apply (may be hierarchical).
        """
        if not tag_names:
            return

        existing = self._get_tag_lookup()
        leaf_ids: list[str] = []
        to_create: list[str] = []

        for name in tag_names:
            name = (name or "").strip()
            if not name:
                continue
            tag_id = _resolve_existing(existing, name)
            if tag_id:
                leaf_ids.append(tag_id)
            else:
                to_create.append(name)

        for name in to_create:
            leaf_ids.append(self._create_tag_hierarchy(name, existing))

        leaf_ids = list(dict.fromkeys(leaf_ids))  # dedupe, preserve order
        if not leaf_ids:
            return

        # Immich bulk-tag endpoint: PUT /tags/assets with tagIds + assetIds.
        r = self._client.put(
            "/tags/assets",
            json={
                "tagIds": leaf_ids,
                "assetIds": [asset_id],
            },
        )
        if r.status_code >= 400:
            raise ImmichError(f"Tag apply failed ({r.status_code}): {r.text[:500]}")

    # ------------------------------------------------------------------ #
    # Albums (get-or-create, then add the asset)
    # ------------------------------------------------------------------ #

    def apply_albums(self, asset_id: str, album_names: list[str]) -> None:
        """Resolve *album_names* and add *asset_id* to each.

        Mirrors the desktop app's AlbumResolver flow (single-image scope, so
        no concurrent-duplicate-creation race to manage):

        1. ``GET /albums`` -> build a case-insensitive name -> id map.
        2. For each name: reuse the existing id, or ``POST /albums`` to create
           it (preserving the exact name passed).
        3. ``PUT /albums/{id}/assets`` with ``{"ids": [asset_id]}``.

        Parameters
        ----------
        asset_id:
            The uploaded asset's id.
        album_names:
            Album names to resolve and add the asset to.
        """
        names = [n.strip() for n in album_names if n and n.strip()]
        if not names:
            return

        existing = self._get_album_lookup()
        album_ids: list[str] = []
        for name in names:
            album_id = existing.get(name.lower())
            if album_id:
                logger.debug("apply_albums: reusing existing album '%s' (%s)", name, album_id)
                album_ids.append(album_id)
                continue
            album_id = self._create_album(name)
            logger.debug("apply_albums: created album '%s' (%s)", name, album_id)
            album_ids.append(album_id)

        album_ids = list(dict.fromkeys(album_ids))  # dedupe, preserve order
        if not album_ids:
            return
        self.add_asset_to_album(album_ids, asset_id)

    def _get_album_lookup(self) -> dict[str, str]:
        """Return a lower-cased albumName -> id map from ``GET /albums``."""
        r = self._client.get("/albums")
        if r.status_code >= 400:
            raise ImmichError(f"Album list failed ({r.status_code}): {r.text[:500]}")
        lookup: dict[str, str] = {}
        for album in r.json():
            name = (album.get("albumName") or "").strip().lower()
            album_id = album.get("id")
            if name and album_id:
                lookup[name] = album_id
        return lookup

    def _create_album(self, name: str) -> str:
        """Create an album named *name* (exact casing) and return its id."""
        r = self._client.post("/albums", json={"albumName": name})
        if r.status_code >= 400:
            # Already exists (e.g. concurrent) — reuse by name.
            reuse = self._get_album_lookup().get(name.lower())
            if reuse:
                return reuse
            raise ImmichError(f"Album create failed ({r.status_code}): {r.text[:500]}")
        album_id = r.json().get("id")
        if not album_id:
            raise ImmichError("Album create returned no id")
        return album_id

    def add_asset_to_album(self, album_ids: list[str], asset_id: str) -> None:
        """Add *asset_id* to each album in *album_ids* (PUT /albums/{id}/assets)."""
        for album_id in album_ids:
            r = self._client.put(
                f"/albums/{album_id}/assets",
                json={"ids": [asset_id]},
            )
            if r.status_code >= 400:
                raise ImmichError(
                    f"Album add failed ({r.status_code}): {r.text[:500]}"
                )

    def _get_tag_lookup(self) -> dict[str, str]:
        """Return a lower-cased tag-value/name → id map from ``GET /tags``."""
        r = self._client.get("/tags")
        if r.status_code >= 400:
            raise ImmichError(f"Tag list failed ({r.status_code}): {r.text[:500]}")
        lookup: dict[str, str] = {}
        for tag in r.json():
            value = (tag.get("value") or "").strip().lower()
            name = (tag.get("name") or "").strip().lower()
            tag_id = tag.get("id")
            if not tag_id:
                continue
            if value:
                lookup[value] = tag_id
            if name:
                lookup[name] = tag_id
        return lookup

    def _create_tag_hierarchy(self, name: str, existing: dict[str, str]) -> str:
        """Create a (possibly hierarchical) tag and return the leaf id."""
        segments = [s for s in name.split("/") if s]
        parent_id: str | None = None
        leaf_id = ""
        for seg in segments:
            found = _resolve_existing(existing, seg)
            if found:
                leaf_id = found
                parent_id = found
                continue
            r = self._client.post("/tags", json={"name": seg, "parentId": parent_id})
            if r.status_code >= 400:
                # Likely already exists — reuse the existing id.
                reuse = _resolve_existing(self._get_tag_lookup(), seg)
                if reuse:
                    leaf_id = reuse
                    parent_id = reuse
                    continue
                raise ImmichError(f"Tag create failed ({r.status_code}): {r.text[:500]}")
            leaf_id = r.json().get("id")
            parent_id = leaf_id
        return leaf_id

    # ------------------------------------------------------------------ #
    # Stubs for future extension (see docs/cli-upload-baseline.md §6)
    # ------------------------------------------------------------------ #

    def apply_flags(self, asset_id: str, metadata: Metadata) -> None:
        """Apply favorite / rating / archive via ``PUT /assets/{id}``.

        NOTE: v1 focuses on upload + tags. This is wired but intentionally
        minimal — extend as needed.
        """
        body: dict = {}
        if metadata.is_favorite:
            body["isFavorite"] = True
        if metadata.rating is not None:
            body["rating"] = metadata.rating
        if metadata.is_archived:
            body["visibility"] = "archive"
        if not body:
            return
        r = self._client.put(f"/assets/{asset_id}", json=body)
        if r.status_code >= 400:
            raise ImmichError(f"Flag apply failed ({r.status_code}): {r.text[:500]}")

    # ------------------------------------------------------------------ #
    # Download (for inspecting an existing asset, e.g. faces investigation)
    # ------------------------------------------------------------------ #

    def download_asset(
        self, asset_id: str, dest_path: str | Path, original: bool = True
    ) -> Path:
        """Download an asset's bytes to *dest_path*.

        Used to pull an existing Immich asset locally so its metadata (e.g.
        face regions) can be inspected — Immich (or another source) locates
        faces; we only upload them. Downloads the original rendition by
        default (``GET /assets/{id}/original``); pass ``original=False`` for
        the thumbnail.

        Parameters
        ----------
        asset_id:
            The asset id to download.
        dest_path:
            File path to write the bytes to.
        original:
            If True, fetch the original; otherwise the thumbnail.

        Returns
        -------
        Path
            The path the bytes were written to.
        """
        endpoint = f"/assets/{asset_id}/original" if original else f"/assets/{asset_id}/thumbnail"
        r = self._client.get(endpoint)
        if r.status_code >= 400:
            raise ImmichError(f"Download failed ({r.status_code}): {r.text[:500]}")
        dest_path = Path(dest_path)
        dest_path.write_bytes(r.content)
        logger.debug("download_asset: wrote %d bytes -> %s", len(r.content), dest_path)
        return dest_path


def _iso_now() -> str:
    """Return the current UTC time as Immich's expected ISO-8601 string."""
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _resolve_existing(lookup: dict[str, str], name: str) -> str | None:
    """Find an existing tag id for *name* (exact or hierarchical leaf)."""
    key = name.strip().lower()
    if key in lookup:
        return lookup[key]
    suffix = "/" + key
    for value, tag_id in lookup.items():
        if value.endswith(suffix):
            return tag_id
    return None
