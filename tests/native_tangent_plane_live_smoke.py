"""Real SolidWorks regression for a tangent-and-parallel native reference plane."""

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
            sw_part.sketch_circle(model, 0.0, 0.0, .010)
        sw_part.extrude_boss_midplane(model, sketch_name, .030)
        cylinder_faces = sw_part.find_cylindrical_faces(
            model, radius=.010, axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(cylinder_faces) != 1:
            raise RuntimeError(f"tangent-plane cylinder mismatch: {len(cylinder_faces)}")
        top_plane = None
        for name in ("Top Plane", "上视基准面"):
            top_plane = get_com_member(model, "FeatureByName", name)
            if top_plane is not None: break
        if top_plane is None:
            raise RuntimeError("Top Plane was not found")
        ref_plane = sw_part.reference_plane_tangent_parallel(
            model, cylinder_faces[0], top_plane,
        )
        params = list(get_com_member(ref_plane, "GetRefPlaneParams") or ())
        normal = params[6:9]
        origin_distance = math.sqrt(sum(value * value for value in params[:3]))
        if abs(origin_distance - .010) > 1e-8:
            raise RuntimeError(f"tangent plane distance mismatch: {origin_distance}")
        if abs(abs(normal[1]) - 1.0) > 1e-8 or abs(normal[0]) > 1e-8 or abs(normal[2]) > 1e-8:
            raise RuntimeError(f"tangent plane normal mismatch: {normal}")
        feature = sw_part._last_model_feature(model)
        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "distance_mm": origin_distance * 1000.0,
            "normal": normal,
            "rebuild": rebuild,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
