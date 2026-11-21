"""Real SolidWorks regression for sketch-normal point projection to a surface."""

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
    success = False
    try:
        with sw_part.sketch(model, "Right Plane") as base_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        base = sw_part.extrude_boss_midplane(model, base_sketch, 0.030)
        with sw_part.sketch(model, "Front Plane"):
            sketch_point = model.SketchManager.CreatePoint(0.0, 0.0, 0.0)
        faces = sw_part.find_cylindrical_faces(
            model, radius=0.010, axis=(1.0, 0.0, 0.0), tolerance=1e-8,
        )
        if base is None or sketch_point is None or len(faces) != 1:
            raise RuntimeError(f"sketch-normal references are incomplete: faces={len(faces)}")
        feature = sw_part.reference_plane_tangent_at_projected_point(
            model, faces[0], sketch_point, projection="sketch_normal",
        )
        geometry = sw_part.reference_plane_geometry(feature)
        origin, normal = geometry["origin"], geometry["normal"]
        radial = (0.0, origin[1], origin[2])
        radius = (radial[1] ** 2 + radial[2] ** 2) ** 0.5
        dot = abs(normal[1] * radial[1] + normal[2] * radial[2]) / radius
        if abs(radius - 0.010) > 1e-8 or abs(dot - 1.0) > 1e-8:
            raise RuntimeError(f"sketch-normal projection is not tangent: {origin}, {normal}")
        if int(get_com_member(feature, "GetErrorCode")) != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("sketch-normal surface plane rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "origin_mm": [value * 1000.0 for value in origin],
            "normal": normal, "radius_mm": radius * 1000.0,
        }, ensure_ascii=False))
    finally:
        if success:
            if original_title and original_title != title:
                try:
                    sw.QuitDoc(original_title)
                except Exception:
                    pass
            try:
                sw.ActivateDoc2(title, False, 0)
            except Exception:
                pass
        else:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
            if original_title:
                try:
                    sw.ActivateDoc2(original_title, False, 0)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
