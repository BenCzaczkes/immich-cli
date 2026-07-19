r"""Portable XMP sidecar generator (stdlib only, no PyQt).

Produces the exact RDF/XML sidecar the Immich server ingests: description and
GPS are read natively; tags/people/rating/faces are written here so the CLI can
apply/round-trip them. Mirrors the desktop app's ``generate_xmp_sidecar``
(``immich_desktop/modules/xmp_manager.py``) but is fully framework-free.

The generated packet MUST begin with a UTF-8 BOM (``\\ufeff``) so Immich's XMP
parser detects UTF-8 and does not fall back to Latin-1 (which mojibakes
non-ASCII text).

See ``docs/cli-upload-baseline.md`` for the field → namespace mapping and the
OpenAPI-backed rationale.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# Register namespace prefixes so ElementTree emits human-readable prefixes
# (mwg-rs:, stArea:, stDim:, dc:, exif: ...) instead of default ns0:/ns1:.
for _prefix, _uri in {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "iptc-core": "http://iptc.org/std/Iptc4xmpCore/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "gps": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "immich": "https://immich.app/schema/1.0/",
    "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#",
}.items():
    ET.register_namespace(_prefix, _uri)

# UTF-8 byte-order mark — required at the very start of the XMP packet.
BOM = "﻿"


def _xml_escape(text: str) -> str:
    """Escape the five XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def decimal_to_exif_gps(
    value: object, positive_ref: str, negative_ref: str
) -> tuple[str | None, str | None]:
    """Convert a decimal coordinate to EXIF DMS + hemisphere reference.

    Parameters
    ----------
    value:
        Decimal degrees (float/int/numeric str). ``None``/``""``/non-numeric
        yields ``(None, None)``.
    positive_ref:
        Reference for non-negative values (e.g. ``"N"`` or ``"E"``).
    negative_ref:
        Reference for negative values (e.g. ``"S"`` or ``"W"``).

    Returns
    -------
    tuple[str | None, str | None]
        ``(dms_value, ref)`` where ``dms_value`` is ``"deg,min,sec"``.
    """
    if value is None or value == "":
        return None, None
    try:
        decimal = float(value)
    except (TypeError, ValueError):
        return None, None

    ref = positive_ref if decimal >= 0 else negative_ref
    decimal = abs(decimal)

    degrees = int(decimal)
    minutes_float = (decimal - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60, 6)
    if seconds >= 60:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1

    seconds_text = f"{seconds:.6f}".rstrip("0").rstrip(".") or "0"
    return f"{degrees},{minutes},{seconds_text}", ref


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def generate_mwg_regions(
    face_regions: list[dict], image_width: int, image_height: int
) -> str:
    """Generate MWG region XML for face regions (ElementTree).

    Converts bounding-box coordinates (x1, y1, x2, y2) to MWG center-based
    normalized coordinates (x, y, w, h) in [0, 1].

    Returns
    -------
    str
        XML string of the ``mwg-rs:Regions`` element, or ``""`` if no valid
        regions.
    """
    if not face_regions or not image_width or not image_height:
        return ""

    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
        "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
        "stArea": "http://ns.adobe.com/xmp/sType/Area#",
    }

    def q(prefix: str, tag: str) -> str:
        return f"{{{ns[prefix]}}}{tag}"

    regions = ET.Element(q("mwg-rs", "Regions"), {q("rdf", "parseType"): "Resource"})

    applied = ET.SubElement(
        regions, q("mwg-rs", "AppliedToDimensions"), {q("rdf", "parseType"): "Resource"}
    )
    ET.SubElement(applied, q("stDim", "w")).text = str(image_width)
    ET.SubElement(applied, q("stDim", "h")).text = str(image_height)
    ET.SubElement(applied, q("stDim", "unit")).text = "pixel"

    region_list = ET.SubElement(regions, q("mwg-rs", "RegionList"))
    bag = ET.SubElement(region_list, q("rdf", "Bag"))

    for face in face_regions:
        person_name = face.get("person_name", "")
        if not person_name:
            continue

        bbox = face.get("bounding_box", {})
        try:
            x1 = float(bbox.get("x1", 0))
            y1 = float(bbox.get("y1", 0))
            x2 = float(bbox.get("x2", 0))
            y2 = float(bbox.get("y2", 0))
        except (TypeError, ValueError):
            continue

        fw = int(face.get("image_width", image_width)) or image_width
        fh = int(face.get("image_height", image_height)) or image_height

        box_w = x2 - x1
        box_h = y2 - y1
        if box_w <= 0 or box_h <= 0 or fw <= 0 or fh <= 0:
            continue

        center_x = _clamp((x1 + box_w / 2) / fw)
        center_y = _clamp((y1 + box_h / 2) / fh)
        norm_w = _clamp(box_w / fw)
        norm_h = _clamp(box_h / fh)

        item = ET.SubElement(bag, q("rdf", "li"), {q("rdf", "parseType"): "Resource"})
        ET.SubElement(item, q("mwg-rs", "Name")).text = person_name
        ET.SubElement(item, q("mwg-rs", "Type")).text = "Face"

        area = ET.SubElement(item, q("mwg-rs", "Area"), {q("rdf", "parseType"): "Resource"})
        ET.SubElement(area, q("stArea", "x")).text = f"{center_x:.6f}"
        ET.SubElement(area, q("stArea", "y")).text = f"{center_y:.6f}"
        ET.SubElement(area, q("stArea", "w")).text = f"{norm_w:.6f}"
        ET.SubElement(area, q("stArea", "h")).text = f"{norm_h:.6f}"
        ET.SubElement(area, q("stArea", "unit")).text = "normalized"

    if len(bag) == 0:
        return ""

    return ET.tostring(regions, encoding="unicode")


def generate_xmp_sidecar(file_path: str, metadata: dict) -> str:
    """Generate a proper XMP sidecar file with RDF/XML structure.

    Parameters
    ----------
    file_path:
        Path to the source file (used only for deriving the sidecar name;
        not read).
    metadata:
        Flat metadata dict. Keys match the field → namespace map: ``tags``,
        ``albums``, ``gps_lat``, ``gps_lon``, ``date_taken``, ``description``,
        ``people_names``, ``rating``, ``camera_make/model/lens``, ``iso``,
        ``f_number``, ``focal_length``, ``exposure_time``, ``city/state/country``,
        ``face_regions``, ``width``, ``height``.

    Returns
    -------
    str
        The XMP content as a string, ready to write to the sidecar file.
    """
    lines = [f'{BOM}<?xpacket begin="{BOM}" id="W5M0MpCehiHzreSzNTczkc9d"?>']
    lines.append(
        '<x:xmpmeta x:xmptk="Immich CLI" '
        'xmlns:x="adobe:ns:meta/" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    )
    lines.append(' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">')
    lines.append('  <rdf:Description rdf:about=""')

    tags = metadata.get("tags", [])
    albums = metadata.get("albums", [])
    gps_lat = metadata.get("gps_lat")
    gps_lon = metadata.get("gps_lon")
    city = metadata.get("city", "")
    state = metadata.get("state", "")
    country = metadata.get("country", "")
    date_taken = metadata.get("date_taken")
    description = metadata.get("description")
    people_names = metadata.get("people_names", [])
    rating = metadata.get("rating")
    face_regions = metadata.get("face_regions", [])

    # Track which namespaces are actually used so we only declare what we need.
    used: set[str] = set()
    if tags:
        used.add("dc")
    if albums:
        used.add("immich")
    if gps_lat is not None or gps_lon is not None:
        used.add("exif")
    if city or state or country:
        used |= {"photoshop", "iptc-core"}
    if date_taken or any(
        metadata.get(k)
        for k in (
            "camera_make",
            "camera_model",
            "lens_model",
            "iso",
            "f_number",
            "focal_length",
            "exposure_time",
        )
    ):
        used.add("exif")
    if description:
        used.add("dc")
    if people_names:
        used.add("iptc-core")
    if rating is not None:
        used.add("photoshop")
    has_regions = bool(face_regions)

    decls: list[str] = []
    if "dc" in used:
        decls.append('xmlns:dc="http://purl.org/dc/elements/1.1/"')
    if "immich" in used:
        decls.append('xmlns:immich="https://immich.app/schema/1.0/"')
    if "exif" in used:
        decls.append('xmlns:exif="http://ns.adobe.com/exif/1.0/"')
    if "iptc-core" in used:
        decls.append('xmlns:iptc-core="http://iptc.org/std/Iptc4xmpCore/1.0/"')
    if "photoshop" in used:
        decls.append('xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"')
    if has_regions:
        decls += [
            'xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"',
            'xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"',
            'xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#"',
        ]

    lines.append(("    " + " ".join(decls) + ">") if decls else ">")

    # -- Tags → dc:subject (RDF Bag) --
    if tags:
        lines.append("   <dc:subject>")
        lines.append("    <rdf:Bag>")
        for tag in tags:
            lines.append(f"     <rdf:li>{_xml_escape(tag)}</rdf:li>")
        lines.append("    </rdf:Bag>")
        lines.append("   </dc:subject>")

    # -- Albums → immich:albums (RDF Bag) --
    if albums:
        lines.append("   <immich:albums>")
        lines.append("    <rdf:Bag>")
        for album in albums:
            lines.append(f"     <rdf:li>{_xml_escape(album)}</rdf:li>")
        lines.append("    </rdf:Bag>")
        lines.append("   </immich:albums>")

    # -- GPS → exif:GPSLatitude / exif:GPSLongitude (EXIF DMS) --
    if gps_lat is not None:
        exif_lat, lat_ref = decimal_to_exif_gps(gps_lat, "N", "S")
        if exif_lat is not None:
            lines.append(f"   <exif:GPSLatitude>{exif_lat}</exif:GPSLatitude>")
            lines.append(f"   <exif:GPSLatitudeRef>{lat_ref}</exif:GPSLatitudeRef>")
    if gps_lon is not None:
        exif_lon, lon_ref = decimal_to_exif_gps(gps_lon, "E", "W")
        if exif_lon is not None:
            lines.append(f"   <exif:GPSLongitude>{exif_lon}</exif:GPSLongitude>")
            lines.append(f"   <exif:GPSLongitudeRef>{lon_ref}</exif:GPSLongitudeRef>")

    if city:
        lines.append(f"   <photoshop:City>{_xml_escape(city)}</photoshop:City>")
        lines.append(f"   <iptc-core:Location>{_xml_escape(city)}</iptc-core:Location>")
    if state:
        lines.append(f"   <photoshop:State>{_xml_escape(state)}</photoshop:State>")
    if country:
        lines.append(f"   <photoshop:Country>{_xml_escape(country)}</photoshop:Country>")

    # -- Date → exif:DateTimeOriginal --
    if date_taken:
        lines.append(
            f"   <exif:DateTimeOriginal>{_xml_escape(str(date_taken))}</exif:DateTimeOriginal>"
        )

    # -- Camera / EXIF fields --
    for key, xml in (
        ("camera_make", "exif:Make"),
        ("camera_model", "exif:Model"),
        ("lens_model", "exif:Lens"),
    ):
        if metadata.get(key):
            lines.append(f"   <{xml}>{_xml_escape(metadata[key])}</{xml}>")
    if metadata.get("iso") is not None:
        lines.append(f"   <exif:ISOSpeedRatings>{metadata['iso']}</exif:ISOSpeedRatings>")
    if metadata.get("f_number") is not None:
        lines.append(f"   <exif:FNumber>{metadata['f_number']}</exif:FNumber>")
    if metadata.get("focal_length") is not None:
        lines.append(f"   <exif:FocalLength>{metadata['focal_length']}</exif:FocalLength>")
    if metadata.get("exposure_time"):
        lines.append(
            f"   <exif:ExposureTime>{_xml_escape(str(metadata['exposure_time']))}</exif:ExposureTime>"
        )

    # -- Rating → xmp:Rating --
    if rating is not None:
        lines.append(f"   <xmp:Rating>{rating}</xmp:Rating>")

    # -- Description → dc:description (RDF Alt) --
    if description:
        lines.append("   <dc:description>")
        lines.append("    <rdf:Alt>")
        lines.append(
            f'     <rdf:li xml:lang="x-default">{_xml_escape(str(description))}</rdf:li>'
        )
        lines.append("    </rdf:Alt>")
        lines.append("   </dc:description>")

    # -- People → iptc-core:PersonInImage (RDF Bag) --
    if people_names:
        lines.append("   <iptc-core:PersonInImage>")
        lines.append("    <rdf:Bag>")
        for person in people_names:
            lines.append(f"     <rdf:li>{_xml_escape(person)}</rdf:li>")
        lines.append("    </rdf:Bag>")
        lines.append("   </iptc-core:PersonInImage>")

    # -- Face regions → mwg-rs:Regions --
    if has_regions:
        img_width = metadata.get("width", 0) or face_regions[0].get("image_width", 0)
        img_height = metadata.get("height", 0) or face_regions[0].get("image_height", 0)
        regions_xml = generate_mwg_regions(face_regions, img_width, img_height)
        if regions_xml:
            for rline in regions_xml.splitlines():
                lines.append(f"   {rline}")

    lines.append("  </rdf:Description>")
    lines.append(" </rdf:RDF>")
    lines.append("</x:xmpmeta>")
    lines.append('<?xpacket end="w"?>')

    return "\n".join(lines)
