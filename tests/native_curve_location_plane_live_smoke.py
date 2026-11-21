"""Real SolidWorks regression for a point-driven normal plane on a curve."""

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
        edges = sw_part.find_solid_edges(
            model, length=0.040, direction=(1.0, 0.0, 0.0),
            midpoint=(0.0, 0.015, 0.010), tolerance=1e-8,
        )
        if base is None or len(edges) != 1:
            raise RuntimeError(f"semantic reference mismatch: edges={len(edges)}")
        edge = edges[0]
        point_feature, plane_feature = sw_part.reference_plane_normal_at_curve_location(
            model, edge, 25.0, mode="percentage",
        )
        point = sw_part.reference_point_geometry(point_feature)
        plane = sw_part.reference_plane_geometry(plane_feature)
        normal, origin = plane["normal"], plane["origin"]
        if abs(abs(normal[0]) - 1.0) > 1e-8 or abs(normal[1]) > 1e-8 or abs(normal[2]) > 1e-8:
            raise RuntimeError(f"plane is not normal to X-directed edge: {normal}")
        residual = abs(sum(normal[i] * (point[i] - origin[i]) for i in range(3)))
        if residual > 1e-8:
            raise RuntimeError(f"normal plane misses its native reference point: {residual}")
        if abs(abs(point[0]) - 0.010) > 1e-8 or abs(point[1] - 0.015) > 1e-8 or abs(point[2] - 0.010) > 1e-8:
            raise RuntimeError(f"25-percent reference point is unexpected: {point}")
        errors = {
            str(get_com_member(feature, "Name")): int(get_com_member(feature, "GetErrorCode"))
            for feature in (point_feature, plane_feature)
        }
        if any(errors.values()) or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"composite reference geometry rebuild failed: {errors}")
        success = True
        print(json.dumps({
            "status": "ok", "document": title,
            "point_feature": str(get_com_member(point_feature, "Name")),
            "plane_feature": str(get_com_member(plane_feature, "Name")),
            "point_mm": [value * 1000.0 for value in point],
            "normal": normal, "point_plane_residual_mm": residual * 1000.0,
            "feature_errors": errors,
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
