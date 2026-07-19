"""Metadata model for the Immich CLI.

A portable, dependency-free analogue of the desktop app's ``MetaExport``
dataclass. Carries everything we can express in an XMP sidecar plus the fields
the server ingests natively (description, GPS) or that we apply client-side
after upload (tags, rating, favorite, archive).

See ``docs/cli-upload-baseline.md`` for the field → XMP namespace mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FaceRegion:
    """A single named face region.

    ``bounding_box`` uses absolute pixel coordinates (x1, y1, x2, y2); the XMP
    generator converts these to MWG normalized coordinates.
    """

    person_name: str
    bounding_box: dict[str, float] = field(
        default_factory=lambda: {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 0.0}
    )
    image_width: int = 0
    image_height: int = 0


@dataclass
class Metadata:
    """Structured metadata for one asset.

    All fields optional; only populated fields are emitted into the XMP
    sidecar. ``width``/``height`` are used to normalize face regions.
    """

    # -- Description / GPS (ingested natively from the sidecar) --
    description: str = ""
    gps_lat: float | None = None
    gps_lon: float | None = None
    city: str = ""
    state: str = ""
    country: str = ""

    # -- Social --
    tags: list[str] = field(default_factory=list)
    albums: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)

    # -- Rating / flags (applied client-side after upload) --
    rating: int | None = None  # 0-5 stars, -1 rejected, None unrated
    is_favorite: bool = False
    is_archived: bool = False

    # -- Camera / EXIF (cosmetic, written to XMP) --
    camera_make: str = ""
    camera_model: str = ""
    lens_model: str = ""
    iso: int | None = None
    f_number: float | None = None
    focal_length: float | None = None
    exposure_time: str = ""
    date_taken: str = ""

    # -- Faces (ingested natively from the sidecar) --
    face_regions: list[FaceRegion] = field(default_factory=list)

    # -- Image dimensions (for face normalization) --
    width: int = 0
    height: int = 0

    # -- Video duration in milliseconds (sent on POST /assets) --
    duration_ms: int = 0

    def to_xmp_dict(self) -> dict:
        """Flatten to the flat dict shape ``generate_xmp_sidecar`` expects.

        Returns
        -------
        dict
            Flat metadata dict with only populated fields set.
        """
        d: dict = {}
        if self.tags:
            d["tags"] = list(self.tags)
        if self.albums:
            d["albums"] = list(self.albums)
        if self.people:
            d["people_names"] = list(self.people)
        if self.gps_lat is not None:
            d["gps_lat"] = self.gps_lat
        if self.gps_lon is not None:
            d["gps_lon"] = self.gps_lon
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
        if self.lens_model:
            d["lens_model"] = self.lens_model
        if self.iso is not None:
            d["iso"] = self.iso
        if self.f_number is not None:
            d["f_number"] = self.f_number
        if self.focal_length is not None:
            d["focal_length"] = self.focal_length
        if self.exposure_time:
            d["exposure_time"] = self.exposure_time
        if self.date_taken:
            d["date_taken"] = self.date_taken
        if self.rating is not None:
            d["rating"] = self.rating
        if self.width:
            d["width"] = self.width
        if self.height:
            d["height"] = self.height
        if self.face_regions:
            d["face_regions"] = [
                {
                    "person_name": fr.person_name,
                    "bounding_box": fr.bounding_box,
                    "image_width": fr.image_width or self.width,
                    "image_height": fr.image_height or self.height,
                }
                for fr in self.face_regions
            ]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Metadata:
        """Build a ``Metadata`` from a MetaExport-shaped ``.meta.json`` dict.

        Tolerates both nested (``tags: list[dict]``) and flat (``tags:
        list[str]``) forms, and the ``flags`` / ``gps`` / ``camera`` sub-objects
        the desktop app emits.
        """
        gps = data.get("gps") or {}
        camera = data.get("camera") or {}
        flags = data.get("flags") or {}
        location = data.get("location") or {}

        raw_tags = data.get("tags", [])
        if raw_tags and isinstance(raw_tags[0], dict):
            tags = [t.get("value") or t.get("name", "") for t in raw_tags]
        else:
            tags = list(raw_tags)

        raw_albums = data.get("albums", [])
        if raw_albums and isinstance(raw_albums[0], dict):
            albums = [a.get("album_name", "") for a in raw_albums]
        else:
            albums = list(raw_albums)

        raw_faces = data.get("face_regions", [])
        face_regions = [
            FaceRegion(
                person_name=f.get("person_name", ""),
                bounding_box=f.get("bounding_box", {}),
                image_width=f.get("image_width", 0),
                image_height=f.get("image_height", 0),
            )
            for f in raw_faces
        ]

        return cls(
            description=data.get("description", ""),
            gps_lat=gps.get("latitude"),
            gps_lon=gps.get("longitude"),
            city=location.get("city", ""),
            state=location.get("state", ""),
            country=location.get("country", ""),
            tags=[t for t in tags if t],
            albums=[a for a in albums if a],
            people=list(data.get("people", [])),
            rating=(data.get("exif") or {}).get("rating"),
            is_favorite=bool(flags.get("is_favorite", False)),
            is_archived=bool(flags.get("is_archived", False)),
            camera_make=camera.get("make", ""),
            camera_model=camera.get("model", ""),
            lens_model=camera.get("lens_model", ""),
            iso=camera.get("iso"),
            f_number=camera.get("f_number"),
            focal_length=camera.get("focal_length"),
            exposure_time=camera.get("exposure_time", ""),
            date_taken=(data.get("exif") or {}).get("date_time_original", ""),
            face_regions=face_regions,
            width=data.get("width") or 0,
            height=data.get("height") or 0,
        )
