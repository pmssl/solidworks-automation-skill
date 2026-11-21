"""Real SolidWorks regression for knitting adjacent planar surface bodies."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def surface_area_mm2(body):
    return sum(float(get_com_member(face, "GetArea"))
               for face in (get_com_member(body, "GetFaces") or ())) * 1e6


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as left_sketch:
            sw_part.sketch_rectangle(model, -.010, 0, .020, .020)
        sw_part.planar_surface_from_sketch(model, left_sketch)
        with sw_part.sketch(model, "Front Plane") as right_sketch:
            sw_part.sketch_rectangle(model, .010, 0, .020, .020)
        sw_part.planar_surface_from_sketch(model, right_sketch)
        before = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(before) != 2:
            raise RuntimeError(f"pre-knit surface count mismatch: {len(before)}")
        before_areas = sorted(surface_area_mm2(body) for body in before)
        if any(abs(area - 400.0) > 1e-5 for area in before_areas):
            raise RuntimeError(f"pre-knit areas mismatch: {before_areas}")

        knit_faces = tuple((get_com_member(body, "GetFaces") or ())[0] for body in before)
        feature = sw_part.knit_surfaces(
            model, knit_faces, merge_entities=False, use_gap_filters=True,
            knit_tolerance=1e-4, max_gap=1e-4,
        )
        after = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(after) != 1:
            raise RuntimeError(f"post-knit surface count mismatch: {len(after)}")
        area = surface_area_mm2(after[0])
        if abs(area - 800.0) > 1e-5:
            raise RuntimeError(f"post-knit area mismatch: {area}")
        data = get_com_member(feature, "GetDefinition")
        tolerance_mm = float(get_com_member(data, "KnitTolerance")) * 1000.0
        if abs(tolerance_mm - .1) > 1e-6:
            raise RuntimeError(f"knit tolerance mismatch: {tolerance_mm}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "before_body_count": len(before),
            "before_areas_mm2": before_areas,
            "after_body_count": len(after),
            "after_area_mm2": area,
            "knit_tolerance_mm": tolerance_mm,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
