"""Controlled probe for a tangent plane at a projected sketch point."""

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
    attempts = []
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        base = sw_part.extrude_boss_midplane(model, base_sketch, 0.030)
        with sw_part.sketch(model, "Front Plane"):
            sketch_point = model.SketchManager.CreatePoint(0.015, 0.0, 0.0)
        faces = sw_part.find_cylindrical_faces(
            model, radius=0.010, axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if base is None or sketch_point is None or len(faces) != 1:
            raise RuntimeError(f"probe references are incomplete: faces={len(faces)}")
        feature = sw_part.reference_plane_tangent_at_projected_point(
            model, faces[0], sketch_point, projection="nearest",
        )
        attempts.append({"variant": "surface_then_point", "created": True})
        geometry = sw_part.reference_plane_geometry(feature)
        normal, origin = geometry["normal"], geometry["origin"]
        radial = (origin[0], origin[1], 0.0)
        radial_length = (radial[0] ** 2 + radial[1] ** 2) ** 0.5
        if abs(radial_length - 0.010) > 1e-8:
            raise RuntimeError(f"plane origin is not on cylinder: {origin}")
        dot = abs(normal[0] * radial[0] + normal[1] * radial[1]) / radial_length
        if abs(dot - 1.0) > 1e-8:
            raise RuntimeError(f"plane is not tangent at projected point: {normal}, {origin}")
        if int(get_com_member(feature, "GetErrorCode")) != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("projected surface plane rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "attempts": attempts, "feature": str(get_com_member(feature, "Name")),
            "origin_mm": [value * 1000.0 for value in origin], "normal": normal,
            "radius_mm": radial_length * 1000.0,
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
