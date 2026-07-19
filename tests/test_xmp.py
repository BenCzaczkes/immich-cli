"""Offline unit tests for the XMP sidecar generator (no network)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from immich_cli.models import FaceRegion, Metadata
from immich_cli.xmp import (
    BOM,
    decimal_to_exif_gps,
    generate_mwg_regions,
    generate_xmp_sidecar,
)


def _strip_packet(xmp: str) -> str:
    """Remove the <?xpacket ...?> wrapper so ElementTree can parse the body."""
    inner = xmp
    s = inner.find("<?xpacket ")
    if s != -1:
        e = inner.find("?>", s)
        inner = inner[e + 2 :].strip()
    if inner.endswith("</xpacket>"):
        inner = inner[: -len("</xpacket>")].strip()
    if inner.endswith('<?xpacket end="w"?>'):
        inner = inner[: -len('<?xpacket end="w"?>')].strip()
    return inner


def test_bom_present():
    xmp = generate_xmp_sidecar("IMG.jpg", {"description": "hi"})
    assert xmp.startswith(BOM)


def test_no_xmp_data_yields_bare_rdf():
    xmp = generate_xmp_sidecar("IMG.jpg", {})
    # Even with no fields, the packet is well-formed XML.
    ET.fromstring(_strip_packet(xmp))


def test_description_and_gps_roundtrip():
    meta = Metadata(description="Sunset — café", gps_lat=48.8566, gps_lon=2.3522)
    xmp = generate_xmp_sidecar("IMG.jpg", meta.to_xmp_dict())
    body = _strip_packet(xmp)
    ET.fromstring(body)  # must parse
    assert "48,51,23.76" in xmp  # GPS DMS
    assert "Sunset &#8212; caf&#233;" in xmp or "Sunset — café" in xmp


def test_tags_and_people_and_rating():
    meta = Metadata(
        tags=["Vacation", "Nature/Flowers/Roses"],
        people=["Benjamin"],
        rating=5,
    )
    xmp = generate_xmp_sidecar("IMG.jpg", meta.to_xmp_dict())
    ET.fromstring(_strip_packet(xmp))
    assert "<dc:subject>" in xmp
    assert "<iptc-core:PersonInImage>" in xmp
    assert "<xmp:Rating>5</xmp:Rating>" in xmp


def test_face_region_has_name_and_normalized_area():
    meta = Metadata(
        face_regions=[
            FaceRegion(
                person_name="Benjamin",
                bounding_box={"x1": 48, "y1": 64, "x2": 192, "y2": 320},
                image_width=480,
                image_height=640,
            )
        ],
        width=480,
        height=640,
    )
    xmp = generate_xmp_sidecar("IMG.jpg", meta.to_xmp_dict())
    ET.fromstring(_strip_packet(xmp))
    assert "mwg-rs:Regions" in xmp
    assert "Benjamin" in xmp
    assert "<stArea:unit>normalized</stArea:unit>" in xmp


def test_decimal_to_exif_gps_north_and_south():
    assert decimal_to_exif_gps(48.8566, "N", "S") == ("48,51,23.76", "N")
    assert decimal_to_exif_gps(-33.8688, "N", "S") == ("33,52,7.68", "S")
    assert decimal_to_exif_gps(None, "N", "S") == (None, None)


def test_mwg_regions_empty_for_no_faces():
    assert generate_mwg_regions([], 480, 640) == ""
    assert generate_mwg_regions([{"person_name": "X"}], 0, 0) == ""


def test_metadata_from_dict_nested_and_flat():
    nested = {
        "description": "d",
        "gps": {"latitude": 1.0, "longitude": 2.0},
        "tags": [{"value": "A/B", "name": "A/B"}],
        "people": ["Zoe"],
        "flags": {"is_favorite": True},
        "exif": {"rating": 4},
        "width": 100,
        "height": 200,
    }
    m = Metadata.from_dict(nested)
    assert m.description == "d"
    assert m.gps_lat == 1.0
    assert m.tags == ["A/B"]
    assert m.people == ["Zoe"]
    assert m.is_favorite is True
    assert m.rating == 4
    # round-trips into xmp dict
    d = m.to_xmp_dict()
    assert d["tags"] == ["A/B"]
    assert d["gps_lat"] == 1.0
