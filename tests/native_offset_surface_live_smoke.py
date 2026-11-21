"""Real SolidWorks regression for native offset-surface direction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def run_case(sw, created, reverse):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle")); created.append(title)
    with sw_part.sketch(model, "Front Plane") as sketch_name:
        sw_part.sketch_rectangle(model, 0, 0, .040, .030)
    sw_part.extrude_boss_midplane(model, sketch_name, .020)
    matches = sw_part.find_planar_faces(model, center=(0, 0, .010), tolerance=1e-8)
    if len(matches) != 1:
        raise RuntimeError(f"top face resolution mismatch: {len(matches)}")
    source = sw_part.planar_face_geometry(matches[0])
    feature = sw_part.offset_surface(model, matches[0], .005, reverse=reverse)
    surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    if len(surface_bodies) != 1:
        raise RuntimeError(f"offset surface body count mismatch: {len(surface_bodies)}")
    faces = tuple(get_com_member(surface_bodies[0], "GetFaces") or ())
    if len(faces) != 1:
        raise RuntimeError(f"offset surface face count mismatch: {len(faces)}")
    result = sw_part.planar_face_geometry(faces[0])
    delta = result["center"][2] - source["center"][2]
    if abs(abs(delta) - .005) > 1e-8:
        raise RuntimeError(f"offset surface distance mismatch: {delta}")
    evidence = {
        "feature": str(get_com_member(feature, "Name")),
        "reverse": reverse,
        "source_center_mm": [value * 1000.0 for value in source["center"]],
        "result_center_mm": [value * 1000.0 for value in result["center"]],
        "delta_z_mm": delta * 1000.0,
        "area_mm2": result["area"] * 1e6,
    }
    sw.QuitDoc(title); created.remove(title)
    return evidence


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        forward = run_case(sw, created, False)
        reverse = run_case(sw, created, True)
        if abs(forward["delta_z_mm"] + reverse["delta_z_mm"]) > 1e-6:
            raise RuntimeError(f"offset reverse directions are not opposite: {forward}, {reverse}")
        print(json.dumps({"status": "ok", "forward": forward, "reverse": reverse}, ensure_ascii=False))
    finally:
        for title in list(created):
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
