"""Real SW2025 regression for flattening a 270-degree cylindrical surface."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _areas(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    return bodies, [
        sum(float(get_com_member(face, "GetArea"))
            for face in tuple(get_com_member(body, "GetFaces") or ())) * 1e6
        for body in bodies
    ]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            axis = sw_part.sketch_line(model, 0.0, -0.015, 0.0, 0.015)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_line(model, 0.010, -0.010, 0.010, 0.010)
        sw_part.revolve_surface(model, sketch_name, 1.5 * math.pi)
        source_bodies, source_areas = _areas(model)
        if len(source_bodies) != 1:
            raise RuntimeError(f"source surface count mismatch: {len(source_bodies)}")
        faces = tuple(get_com_member(source_bodies[0], "GetFaces") or ())
        vertices = tuple(get_com_member(source_bodies[0], "GetVertices") or ())
        if len(faces) != 1 or not vertices:
            raise RuntimeError(
                f"source topology mismatch: faces={len(faces)}, vertices={len(vertices)}"
            )
        feature = sw_part.flatten_surface(
            model, faces[0], vertices[0], accuracy_factor=3,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.flatten_surface_evidence(feature, model)
        bodies, areas = _areas(model)
        expected = 1.5 * math.pi * 10.0 * 20.0
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["accuracy_factor"] != 3
            or evidence["face_count"] != 1
            or not evidence["has_anchor_vertex"]
            or evidence["should_make_tears"]
            or len(bodies) < 1
            or min(abs(area - expected) for area in areas) > 1.0
        ):
            raise RuntimeError(
                f"flatten surface mismatch: rebuild={rebuilt}, areas={areas}, "
                f"expected={expected}, evidence={evidence}"
            )
        completed = True
        if original_title and original_title != title:
            sw.QuitDoc(original_title)
        sw.ActivateDoc2(title, False, 0)
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "source_area_mm2": source_areas[0],
            "expected_developed_area_mm2": expected,
            "surface_body_count": len(bodies), "body_areas_mm2": areas,
            "evidence": evidence, "rebuild": rebuilt,
        }, ensure_ascii=False))
    finally:
        if not completed:
            sw.QuitDoc(title)
            if original_title:
                sw.ActivateDoc2(original_title, False, 0)


if __name__ == "__main__":
    main()
