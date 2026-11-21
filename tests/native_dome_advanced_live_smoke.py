"""Real SolidWorks regression for Dome reverse, constraint, and direction data."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _volume(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    return float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9


def _only_face(model, **criteria):
    faces = sw_part.find_planar_faces(model, **criteria)
    if len(faces) != 1:
        raise RuntimeError(f"expected one semantic planar face, found {len(faces)}: {criteria}")
    return faces[0]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        base = sw_part.extrude_boss_midplane(model, sketch_name, .020)

        sw_part.start_3d_sketch(model)
        constraint_point = sw_part.sketch_point_3d(model, 0.0, 0.0, .018)
        point_xyz = tuple(float(get_com_member(constraint_point, axis)) for axis in ("X", "Y", "Z"))
        sw_part.end_3d_sketch(model)
        if math.dist(point_xyz, (0.0, 0.0, .018)) > 1e-9:
            raise RuntimeError(f"3D constraint point mismatch: {point_xyz}")

        top = _only_face(model, area=.0012, center=(0.0, 0.0, .010), normal=(0.0, 0.0, 1.0))
        top_dome = sw_part.dome_feature(model, (top,), .008)
        direction_edges = sw_part.find_solid_edges(
            model, length=.020, direction=(0.0, 0.0, 1.0),
        )
        if not direction_edges:
            raise RuntimeError("no stable vertical edge found for Dome direction")
        sw_part.update_dome_feature(top_dome, model, direction=direction_edges[0])
        direction_evidence = sw_part.dome_feature_evidence(top_dome, model)
        if not direction_evidence["has_direction"]:
            raise RuntimeError(f"Dome direction was not retained: {direction_evidence}")

        sw_part.update_dome_feature(top_dome, model, constraint=constraint_point)
        constrained_evidence = sw_part.dome_feature_evidence(top_dome, model)
        constrained_volume = _volume(model)
        if not constrained_evidence["has_constraint"]:
            raise RuntimeError(f"Dome references were not retained: {constrained_evidence}")

        bottom = _only_face(model, area=.0012, center=(0.0, 0.0, -.010), normal=(0.0, 0.0, 1.0))
        reverse_dome = sw_part.dome_feature(
            model, (bottom,), .004, reverse_direction=True,
        )
        reverse_evidence = sw_part.dome_feature_evidence(reverse_dome, model)
        reverse_volume = _volume(model)
        if not reverse_evidence["reverse_direction"]:
            raise RuntimeError(f"Dome reverse flag was not retained: {reverse_evidence}")
        if math.isclose(reverse_volume, constrained_volume, abs_tol=1e-6):
            raise RuntimeError("reverse Dome did not change solid volume")
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("advanced Dome rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            base, top_dome, reverse_dome,
        )):
            raise RuntimeError("advanced Dome feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "constraint_point_mm": [value * 1000.0 for value in point_xyz],
            "direction": direction_evidence,
            "constrained": {"feature_data": constrained_evidence, "volume_mm3": constrained_volume},
            "reverse": {"feature_data": reverse_evidence, "volume_mm3": reverse_volume},
        }, ensure_ascii=False))
    finally:
        if completed:
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
