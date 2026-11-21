"""Real SolidWorks regression for a standard sketch-trimmed surface."""

from __future__ import annotations

import json
import math
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
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        sw_part.planar_surface_from_sketch(model, base_sketch)
        with sw_part.sketch(model, "Front Plane") as trim_sketch:
            sw_part.sketch_circle(model, 0, 0, .010)
        target_surface = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(target_surface) != 1:
            raise RuntimeError(f"target surface body count mismatch: {len(target_surface)}")
        tool = get_com_member(model, "FeatureByName", str(trim_sketch))
        if tool is None:
            raise RuntimeError(f"trim tool sketch not found: {trim_sketch}")
        feature = sw_part.trim_surface_standard(
            model, tool, ((.015, 0.0, 0.0),), target_surfaces=target_surface,
        )
        surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area_mm2 = sum(
            float(get_com_member(face, "GetArea"))
            for body in surfaces
            for face in tuple(get_com_member(body, "GetFaces") or ())
        ) * 1e6
        expected = 1200.0 - math.pi * 10.0 ** 2
        if len(surfaces) != 1 or abs(area_mm2 - expected) > 1e-4:
            raise RuntimeError(f"trim result mismatch: bodies={len(surfaces)}, area={area_mm2}, expected={expected}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "trim_tool": str(trim_sketch),
            "surface_body_count": len(surfaces),
            "remaining_area_mm2": area_mm2,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
