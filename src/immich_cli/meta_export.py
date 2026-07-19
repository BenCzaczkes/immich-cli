"""Metadata export for downloaded Immich assets (round-trip structure).

Ported from the desktop app's ``core/meta_export.py`` so the CLI can recreate
the same local structure: for a downloaded asset we write a
``<image>.<ext>.meta.json`` (rich, server-shaped metadata) plus an
``<image>.<ext>.xmp`` sidecar (stars + people + faces) that round-trips back
into an XMP-aware consumer or a re-upload.

The face-region handling deliberately **drops corrupt boxes** (see
``from_json`` / ``from_asset_bundle``): Immich's ML face detection returns
records with empty/all-zero boxes, and the legacy ``POST /faces`` path emitted
x100-scaled boxes (e.g. x2=45600 on a 480px image). Writing those back into
XMP would corrupt the round-trip, so we skip degenerate / inverted / out-of-
bounds regions. This is the "box tipping" guard.

Adapted to the CLI: uses ``immich_cli.xmp.generate_xmp_sidecar`` (which expects
the same flat dict shape as ``MetaExport.to_xmp_dict``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from immich_cli.xmp import generate_xmp_sidecar

log = logging.getLogger(__name__)


@dataclass
class TagInfo:
    """Full tag information from Immich (TagResponseDto)."""

    id: str = ""
    parent_id: str = ""
    name: str = ""
    value: str = ""  # Full path (e.g. "Nature/Flowers/Roses")
    color: str = ""


@dataclass
class AlbumInfo:
    """Full album information from Immich (AlbumResponseDto subset)."""

    id: str = ""
    album_name: str = ""
    description: str = ""


@dataclass
class FaceRegion:
    """Face region data from Immich (AssetFaceResponseDto + PersonResponseDto)."""

    person_name: str
    person_id: str = ""
    source_type: str = ""  # "machine-learning" / "exif" / "manual"
    bounding_box: dict = field(
        default_factory=lambda: {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
    )
    image_width: int = 0
    image_height: int = 0


@dataclass
class MetaExport:
    """Structured metadata for a single asset.

    Written to ``<filename>.meta.json`` alongside downloaded assets.
    Schema ``version`` is 1 for forward compatibility.
    """

    version: int = 1

    # -- Asset-level fields --
    asset_id: str = ""
    asset_type: str = ""
    original_filename: str = ""
    original_mime_type: str = ""
    file_created_at: str = ""
    file_modified_at: str = ""
    local_date_time: str = ""
    created_at: str = ""
    updated_at: str = ""
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    live_photo_video_id: str = ""
    is_offline: bool = False
    is_edited: bool = False
    resized: bool = False
    duplicate_id: str = ""
    checksum: str = ""
    owner_id: str = ""
    library_id: str = ""

    # -- Description --
    description: str = ""

    # -- Social --
    tags: list[TagInfo] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    albums: list[AlbumInfo] = field(default_factory=list)

    # -- GPS --
    latitude: float | None = None
    longitude: float | None = None
    city: str = ""
    state: str = ""
    country: str = ""

    # -- Camera / EXIF --
    camera_make: str = ""
    camera_model: str = ""
    camera_lens_model: str = ""
    exposure_time: str = ""
    f_number: float | None = None
    iso: int | None = None
    focal_length: float | None = None

    # -- Additional EXIF fields --
    exif_image_width: int | None = None
    exif_image_height: int | None = None
    file_size_in_byte: int | None = None
    orientation: str = ""
    date_time_original: str = ""
    modify_date: str = ""
    time_zone: str = ""
    projection_type: str = ""
    rating: int | None = None

    # -- Flags --
    is_favorite: bool = False
    is_archived: bool = False

    # -- Face regions --
    face_regions: list[FaceRegion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "original_filename": self.original_filename,
            "original_mime_type": self.original_mime_type,
            "file_created_at": self.file_created_at,
            "file_modified_at": self.file_modified_at,
            "local_date_time": self.local_date_time,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "live_photo_video_id": self.live_photo_video_id,
            "is_offline": self.is_offline,
            "is_edited": self.is_edited,
            "resized": self.resized,
            "duplicate_id": self.duplicate_id,
            "checksum": self.checksum,
            "owner_id": self.owner_id,
            "library_id": self.library_id,
            "description": self.description,
            "tags": [
                {
                    "id": t.id,
                    "parent_id": t.parent_id,
                    "name": t.name,
                    "value": t.value,
                    "color": t.color,
                }
                for t in self.tags
            ],
            "people": self.people,
            "albums": [
                {"id": a.id, "album_name": a.album_name, "description": a.description}
                for a in self.albums
            ],
            "gps": (
                {"latitude": self.latitude, "longitude": self.longitude}
                if self.latitude is not None
                else None
            ),
            "camera": {
                "make": self.camera_make,
                "model": self.camera_model,
                "lens_model": self.camera_lens_model,
                "exposure_time": self.exposure_time,
                "f_number": self.f_number,
                "iso": self.iso,
                "focal_length": self.focal_length,
            },
            "exif": {
                "image_width": self.exif_image_width,
                "image_height": self.exif_image_height,
                "file_size_in_byte": self.file_size_in_byte,
                "orientation": self.orientation,
                "date_time_original": self.date_time_original,
                "modify_date": self.modify_date,
                "time_zone": self.time_zone,
                "projection_type": self.projection_type,
                "rating": self.rating,
            },
            "location": {
                "city": self.city,
                "state": self.state,
                "country": self.country,
            },
            "flags": {
                "is_favorite": self.is_favorite,
                "is_archived": self.is_archived,
            },
            "face_regions": [
                {
                    "person_name": fr.person_name,
                    "person_id": fr.person_id,
                    "source_type": fr.source_type,
                    "bounding_box": fr.bounding_box,
                    "image_width": fr.image_width,
                    "image_height": fr.image_height,
                }
                for fr in self.face_regions
            ],
        }

    def to_xmp_dict(self) -> dict[str, Any]:
        """Flatten to the dict shape expected by ``generate_xmp_sidecar``.

        Returns only populated fields; empty if nothing XMP-relevant is set.
        """
        d: dict[str, Any] = {}

        tags = [t.value or t.name for t in self.tags if (t.value or t.name)]
        if tags:
            d["tags"] = tags

        albums = [a.album_name for a in self.albums if a.album_name]
        if albums:
            d["albums"] = albums

        people = [p for p in self.people if p]
        if people:
            d["people_names"] = people

        if self.latitude is not None:
            d["gps_lat"] = self.latitude
        if self.longitude is not None:
            d["gps_lon"] = self.longitude

        if self.city:
            d["city"] = self.city
        if self.state:
            d["state"] = self.state
        if self.country:
            d["country"] = self.country

        if self.description:
            d["description"] = self.description

        if self.camera_make:
            d["camera_make"] = self.camera_make
        if self.camera_model:
            d["camera_model"] = self.camera_model
        if self.camera_lens_model:
            d["camera_lens_model"] = self.camera_lens_model
        if self.exposure_time:
            d["exposure_time"] = self.exposure_time
        if self.f_number is not None:
            d["f_number"] = self.f_number
        if self.iso is not None:
            d["iso"] = self.iso
        if self.focal_length is not None:
            d["focal_length"] = self.focal_length

        if self.rating is not None:
            d["rating"] = self.rating

        if self.date_time_original:
            d["date_taken"] = self.date_time_original

        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height

        if self.face_regions:
            d["face_regions"] = [
                {
                    "person_name": fr.person_name,
                    "person_id": fr.person_id,
                    "source_type": fr.source_type,
                    "bounding_box": fr.bounding_box,
                    "image_width": fr.image_width,
                    "image_height": fr.image_height,
                }
                for fr in self.face_regions
            ]

        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a human-readable UTF-8 JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> MetaExport:
        """Load a MetaExport from a JSON string (reverse of ``to_dict``)."""
        data = json.loads(json_str)

        file_version = data.get("version", 1)
        if file_version > 1:
            log.warning(
                "Meta file version %d is newer than supported (1); "
                "some fields may not be parsed correctly",
                file_version,
            )

        gps = data.get("gps") or {}
        camera = data.get("camera") or {}
        location = data.get("location") or {}
        flags = data.get("flags") or {}
        exif_extra = data.get("exif") or {}

        raw_tags = data.get("tags", [])
        if raw_tags and isinstance(raw_tags[0], str):
            tags = [TagInfo(name=t, value=t) for t in raw_tags if t]
        elif raw_tags and isinstance(raw_tags[0], dict):
            tags = [
                TagInfo(
                    id=t.get("id", ""),
                    parent_id=t.get("parent_id", ""),
                    name=t.get("name", ""),
                    value=t.get("value", ""),
                    color=t.get("color", ""),
                )
                for t in raw_tags
            ]
        else:
            tags = []

        raw_albums = data.get("albums", [])
        if raw_albums and isinstance(raw_albums[0], str):
            albums = [AlbumInfo(album_name=a) for a in raw_albums if a]
        elif raw_albums and isinstance(raw_albums[0], dict):
            albums = [
                AlbumInfo(
                    id=a.get("id", ""),
                    album_name=a.get("album_name", ""),
                    description=a.get("description", ""),
                )
                for a in raw_albums
            ]
        else:
            albums = []

        # Face regions: skip degenerate / inverted / out-of-bounds boxes (the
        # "box tipping" guard). See module docstring.
        raw_faces = data.get("face_regions", [])
        face_regions: list[FaceRegion] = []
        asset_w = data.get("width") or 0
        asset_h = data.get("height") or 0
        for f in raw_faces:
            bb = f.get("bounding_box") or {}
            try:
                x1 = float(bb.get("x1", 0))
                y1 = float(bb.get("y1", 0))
                x2 = float(bb.get("x2", 0))
                y2 = float(bb.get("y2", 0))
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue  # degenerate / all-zero / inverted
            fw = f.get("image_width") or asset_w
            fh = f.get("image_height") or asset_h
            if fw and fh and (x2 > fw or y2 > fh):
                log.warning(
                    "Skipping face region for '%s': box (%s,%s,%s,%s) exceeds "
                    "image dimensions %dx%d",
                    f.get("person_name", ""), x1, y1, x2, y2, fw, fh,
                )
                continue
            face_regions.append(
                FaceRegion(
                    person_name=f.get("person_name", ""),
                    person_id=f.get("person_id", ""),
                    source_type=f.get("source_type", ""),
                    bounding_box={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    image_width=f.get("image_width", 0),
                    image_height=f.get("image_height", 0),
                )
            )

        return cls(
            version=data.get("version", 1),
            asset_id=data.get("asset_id", ""),
            asset_type=data.get("asset_type", ""),
            original_filename=data.get("original_filename", ""),
            original_mime_type=data.get("original_mime_type", ""),
            file_created_at=data.get("file_created_at", ""),
            file_modified_at=data.get("file_modified_at", ""),
            local_date_time=data.get("local_date_time", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            width=data.get("width"),
            height=data.get("height"),
            duration=data.get("duration"),
            live_photo_video_id=data.get("live_photo_video_id", ""),
            is_offline=data.get("is_offline", False),
            is_edited=data.get("is_edited", False),
            resized=data.get("resized", False),
            duplicate_id=data.get("duplicate_id", ""),
            checksum=data.get("checksum", ""),
            owner_id=data.get("owner_id", ""),
            library_id=data.get("library_id", ""),
            description=data.get("description", ""),
            tags=tags,
            people=data.get("people", []),
            albums=albums,
            latitude=gps.get("latitude"),
            longitude=gps.get("longitude"),
            city=location.get("city", ""),
            state=location.get("state", ""),
            country=location.get("country", ""),
            camera_make=camera.get("make", ""),
            camera_model=camera.get("model", ""),
            camera_lens_model=camera.get("lensModel", ""),
            exposure_time=camera.get("exposure_time", ""),
            f_number=camera.get("f_number"),
            iso=camera.get("iso"),
            focal_length=camera.get("focal_length"),
            exif_image_width=exif_extra.get("image_width"),
            exif_image_height=exif_extra.get("image_height"),
            file_size_in_byte=exif_extra.get("file_size_in_byte"),
            orientation=exif_extra.get("orientation", ""),
            date_time_original=exif_extra.get("date_time_original", ""),
            modify_date=exif_extra.get("modify_date", ""),
            time_zone=exif_extra.get("time_zone", ""),
            projection_type=exif_extra.get("projection_type", ""),
            rating=exif_extra.get("rating"),
            is_favorite=flags.get("is_favorite", False),
            is_archived=flags.get("is_archived", False),
            face_regions=face_regions,
        )

    @classmethod
    def from_asset_bundle(
        cls,
        asset_id: str,
        asset_data: dict[str, Any],
        faces_data: list[dict] | None = None,
        albums_data: list[dict] | None = None,
    ) -> MetaExport:
        """Build a MetaExport from an asset metadata bundle.

        Parameters
        ----------
        asset_id:
            The asset ID.
        asset_data:
            Full asset object from ``GET /assets/{id}``.
        faces_data:
            Face data from ``GET /faces?id={id}``.
        albums_data:
            Album data from ``GET /albums?assetId={id}`` (full objects).
        """
        exif = asset_data.get("exifInfo") or {}

        tags = [
            TagInfo(
                id=tag.get("id", ""),
                parent_id=tag.get("parentId", ""),
                name=tag.get("name", ""),
                value=tag.get("value", tag.get("name", "")),
                color=tag.get("color", ""),
            )
            for tag in asset_data.get("tags", [])
            if isinstance(tag, dict) and (tag.get("value") or tag.get("name"))
        ]

        people = [
            person.get("name", "")
            for person in asset_data.get("people", [])
            if isinstance(person, dict) and person.get("name")
        ] + [
            person for person in asset_data.get("people", []) if isinstance(person, str)
        ]
        if faces_data:
            face_people = {
                face.get("person", {}).get("name", "")
                for face in faces_data
                if face.get("person", {}).get("name")
            }
            people = list(set(people) | face_people)

        albums = [
            AlbumInfo(
                id=a.get("id", ""),
                album_name=a.get("albumName", ""),
                description=a.get("description", ""),
            )
            for a in (albums_data or [])
            if isinstance(a, dict)
        ]

        face_regions = [
            FaceRegion(
                person_name=face.get("person", {}).get("name", ""),
                person_id=face.get("person", {}).get("id", ""),
                source_type=face.get("sourceType", ""),
                bounding_box={
                    "x1": face.get("boundingBoxX1", 0),
                    "y1": face.get("boundingBoxY1", 0),
                    "x2": face.get("boundingBoxX2", 0),
                    "y2": face.get("boundingBoxY2", 0),
                },
                image_width=face.get("imageWidth", 0),
                image_height=face.get("imageHeight", 0),
            )
            for face in (faces_data or [])
        ]

        description = exif.get("description", "") or asset_data.get("description", "") or ""

        return cls(
            asset_id=asset_id,
            asset_type=asset_data.get("type", ""),
            original_filename=asset_data.get("originalFileName", ""),
            original_mime_type=asset_data.get("originalMimeType", ""),
            file_created_at=asset_data.get("fileCreatedAt", ""),
            file_modified_at=asset_data.get("fileModifiedAt", ""),
            local_date_time=asset_data.get("localDateTime", ""),
            created_at=asset_data.get("createdAt", ""),
            updated_at=asset_data.get("updatedAt", ""),
            width=asset_data.get("width"),
            height=asset_data.get("height"),
            duration=asset_data.get("duration"),
            live_photo_video_id=asset_data.get("livePhotoVideoId", ""),
            is_offline=asset_data.get("isOffline", False),
            is_edited=asset_data.get("isEdited", False),
            resized=asset_data.get("resized", False),
            duplicate_id=asset_data.get("duplicateId", ""),
            checksum=asset_data.get("checksum", ""),
            owner_id=asset_data.get("ownerId", ""),
            library_id=asset_data.get("libraryId", ""),
            description=description,
            tags=tags,
            people=people,
            albums=albums,
            latitude=exif.get("latitude"),
            longitude=exif.get("longitude"),
            city=exif.get("city", ""),
            state=exif.get("state", ""),
            country=exif.get("country", ""),
            camera_make=exif.get("make", ""),
            camera_model=exif.get("model", ""),
            camera_lens_model=exif.get("lensModel", ""),
            exposure_time=exif.get("exposureTime", ""),
            f_number=exif.get("f_number"),
            iso=exif.get("iso"),
            focal_length=exif.get("focalLength"),
            exif_image_width=exif.get("exifImageWidth"),
            exif_image_height=exif.get("exifImageHeight"),
            file_size_in_byte=exif.get("fileSizeInByte"),
            orientation=exif.get("orientation", ""),
            date_time_original=exif.get("dateTimeOriginal", ""),
            modify_date=exif.get("modifyDate", ""),
            time_zone=exif.get("timeZone", ""),
            projection_type=exif.get("projectionType", ""),
            rating=exif.get("rating"),
            is_favorite=asset_data.get("isFavorite", False),
            is_archived=asset_data.get("isArchived", False),
            face_regions=face_regions,
        )


def generate_meta_export(
    asset_id: str,
    asset_data: dict[str, Any],
    download_path: Path,
    faces_data: list[dict] | None = None,
    albums_data: list[dict] | None = None,
) -> Path:
    """Generate ``.meta.json`` (+ ``.xmp`` sidecar when rating/people set).

    Writes ``<download_path>.<ext>.meta.json`` and, when the asset carries a
    star rating or people, ``<download_path>.<ext>.xmp`` alongside it.

    Parameters
    ----------
    asset_id:
        The asset ID.
    asset_data:
        Full asset object from ``GET /assets/{id}``.
    download_path:
        Path to the extracted/downloaded image file.
    faces_data:
        Face data from ``GET /faces?id={id}``.
    albums_data:
        Album data from ``GET /albums?assetId={id}``.

    Returns
    -------
    Path
        Path to the generated ``.meta.json`` file.
    """
    meta = MetaExport.from_asset_bundle(asset_id, asset_data, faces_data, albums_data)
    meta_path = download_path.with_suffix(download_path.suffix + ".meta.json")
    meta_path.write_text(meta.to_json(), encoding="utf-8")
    log.info("Generated .meta.json for %s at %s", asset_id, meta_path)

    if meta.rating is not None or meta.people:
        sidecar_path = download_path.with_suffix(download_path.suffix + ".xmp")
        xmp_content = generate_xmp_sidecar(str(download_path), meta.to_xmp_dict())
        sidecar_path.write_text(xmp_content, encoding="utf-8")
        log.info(
            "Generated XMP sidecar (stars=%s, people=%d) for %s at %s",
            meta.rating, len(meta.people), asset_id, sidecar_path,
        )

    return meta_path


__all__ = [
    "AlbumInfo",
    "FaceRegion",
    "MetaExport",
    "TagInfo",
    "generate_meta_export",
]
