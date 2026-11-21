"""Real SolidWorks regression for a plane parallel through a point."""

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
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.040, 0.030)
        base = sw_part.extrude_boss_midplane(model, sketch_name, 0.020)
        point = (0.020, 0.015, -0.010)
        vertices = sw_part.find_solid_vertices(model, point, tolerance=1e-8)
        planar_faces = sw_part.find_planar_faces(
            model, area=0.040 * 0.030, center=(0.0, 0.0, 0.010),
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if base is None or len(vertices) != 1 or len(planar_faces) != 1:
            raise RuntimeError(
                f"semantic reference mismatch: vertices={len(vertices)}, "
                f"faces={len(planar_faces)}"
            )
        feature = sw_part.reference_plane_parallel_through_point(
            model, planar_faces[0], vertices[0],
        )
        params = tuple(float(value) for value in (get_com_member(feature, "GetRefPlaneParams") or ()))
        geometry = sw_part.reference_plane_geometry(feature)
        normal, origin = geometry["normal"], geometry["origin"]
        if abs(normal[0]) > 1e-8 or abs(normal[1]) > 1e-8 or abs(abs(normal[2]) - 1.0) > 1e-8:
            raise RuntimeError(f"plane is not parallel to selected planar face: {normal}")
        residual = abs(sum(normal[i] * (point[i] - origin[i]) for i in range(3)))
        if residual > 1e-8:
            raise RuntimeError(f"plane does not pass through selected point: {residual}")
        if int(get_com_member(feature, "GetErrorCode")) != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("curve-origin reference plane rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title,
            "feature": str(get_com_member(feature, "Name")),
            "normal": normal, "origin_mm": [value * 1000.0 for value in origin],
            "point_mm": [value * 1000.0 for value in point],
            "point_plane_residual_mm": residual * 1000.0,
            "params": params,
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
