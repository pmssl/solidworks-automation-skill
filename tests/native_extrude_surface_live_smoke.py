"""Real SolidWorks regression for a native extruded surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_line(model, -.020, 0.0, .020, 0.0)
        feature = sw_part.extrude_surface(model, sketch_name, .025)
        surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area_mm2 = sum(
            float(get_com_member(face, "GetArea"))
            for body in surfaces
            for face in tuple(get_com_member(body, "GetFaces") or ())
        ) * 1e6
        if len(surfaces) != 1 or abs(area_mm2 - 1000.0) > 1e-4:
            raise RuntimeError(f"extruded surface mismatch: bodies={len(surfaces)}, area={area_mm2}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile_length_mm": 40.0,
            "depth_mm": 25.0,
            "surface_body_count": len(surfaces),
            "area_mm2": area_mm2,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
