"""Real SolidWorks regression for native Delete Face without healing."""

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
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        sw_part.extrude_boss_midplane(model, sketch_name, .020)
        top_faces = sw_part.find_planar_faces(model, center=(0, 0, .010), tolerance=1e-8)
        if len(top_faces) != 1:
            raise RuntimeError(f"top face resolution mismatch: {len(top_faces)}")
        feature = sw_part.delete_faces(model, top_faces[0], heal=False)
        solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if solids or len(surfaces) != 1:
            raise RuntimeError(f"delete-face body mismatch: solids={len(solids)}, surfaces={len(surfaces)}")
        area_mm2 = sum(
            float(get_com_member(face, "GetArea"))
            for face in tuple(get_com_member(surfaces[0], "GetFaces") or ())
        ) * 1e6
        if abs(area_mm2 - 4000.0) > 1e-4:
            raise RuntimeError(f"open shell area mismatch: {area_mm2}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "heal": False,
            "solid_body_count": len(solids),
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
