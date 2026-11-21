"""Real SolidWorks regression for a plane normal to a curve at its endpoint."""

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
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.040, 0.030)
        base = sw_part.extrude_boss_midplane(model, sketch_name, 0.020)
        if base is None:
            raise RuntimeError("failed to create reference block")
        edges = sw_part.find_solid_edges(
            model, length=0.040, direction=(1.0, 0.0, 0.0),
            midpoint=(0.0, 0.015, 0.010), tolerance=1e-8,
        )
        point = (0.020, 0.015, 0.010)
        vertices = sw_part.find_solid_vertices(model, point, tolerance=1e-8)
        if len(edges) != 1 or len(vertices) != 1:
            raise RuntimeError(
                f"semantic reference mismatch: edges={len(edges)}, vertices={len(vertices)}"
            )
        feature = sw_part.reference_plane_normal_to_curve(model, edges[0], vertices[0])
        params = list(get_com_member(feature, "GetRefPlaneParams") or ())
        if len(params) < 9:
            raise RuntimeError(f"missing reference-plane parameters: {params}")
        normal = [float(value) for value in params[6:9]]
        if abs(abs(normal[0]) - 1.0) > 1e-8 or abs(normal[1]) > 1e-8 or abs(normal[2]) > 1e-8:
            raise RuntimeError(f"plane is not normal to X-directed edge: {normal}")
        geometry = sw_part.reference_plane_geometry(feature)
        origin = geometry["origin"]
        transform_data = geometry["transform"]
        if math.dist(normal, geometry["normal"]) > 1e-8:
            raise RuntimeError(
                f"plane normal sources disagree: {normal}, {geometry['normal']}"
            )
        residual = abs(sum(
            normal[index] * (point[index] - origin[index]) for index in range(3)
        ))
        if residual > 1e-8:
            raise RuntimeError(
                f"plane does not pass through endpoint: residual={residual}, "
                f"params={params}, transform={transform_data}"
            )
        if int(get_com_member(feature, "GetErrorCode")) != 0:
            raise RuntimeError("reference plane has a rebuild error")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("rebuild failed after reference plane")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "normal": normal,
            "origin_mm": [value * 1000.0 for value in origin],
            "point_mm": [value * 1000.0 for value in point],
            "point_plane_residual_mm": residual * 1000.0,
        }, ensure_ascii=False))
    finally:
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
