"""Real SolidWorks regressions for revolved, swept, and lofted surfaces."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def surface_evidence(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    area = sum(
        float(get_com_member(face, "GetArea"))
        for body in bodies
        for face in tuple(get_com_member(body, "GetFaces") or ())
    )
    return bodies, area * 1e6


def run_revolve(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle")); created.append(title)
    with sw_part.sketch(model, "Front Plane") as sketch_name:
        axis = sw_part.sketch_line(model, 0.0, -.015, 0.0, .015)
        sw_part.set_sketch_construction(axis, True)
        sw_part.sketch_line(model, .010, -.010, .010, .010)
    feature = sw_part.revolve_surface(model, sketch_name, 1.5 * math.pi)
    bodies, area = surface_evidence(model)
    expected = 1.5 * math.pi * 10.0 * 20.0
    if len(bodies) != 1 or abs(area - expected) > 1e-3:
        raise RuntimeError(f"revolved surface mismatch: bodies={len(bodies)}, area={area}, expected={expected}")
    evidence = {"feature": str(get_com_member(feature, "Name")), "angle_deg": 270.0,
                "body_count": len(bodies), "area_mm2": area}
    sw.QuitDoc(title); created.remove(title)
    return evidence


def run_sweep(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle")); created.append(title)
    with sw_part.sketch(model, "Right Plane") as profile:
        sw_part.sketch_line(model, 0.0, -.005, 0.0, .005)
    with sw_part.sketch(model, "Front Plane") as path:
        sw_part.sketch_line(model, 0.0, 0.0, .040, 0.0)
    feature = sw_part.sweep_surface(model, profile, path)
    bodies, area = surface_evidence(model)
    if len(bodies) != 1 or abs(area - 400.0) > 1e-3:
        raise RuntimeError(f"swept surface mismatch: bodies={len(bodies)}, area={area}")
    evidence = {"feature": str(get_com_member(feature, "Name")), "profile_mm": 10.0,
                "path_mm": 40.0, "body_count": len(bodies), "area_mm2": area}
    sw.QuitDoc(title); created.remove(title)
    return evidence


def run_loft(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle")); created.append(title)
    with sw_part.sketch(model, "Front Plane") as first:
        sw_part.sketch_line(model, -.010, 0.0, .010, 0.0)
    plane = sw_part.offset_plane(model, "Front Plane", .030)
    plane_name = str(get_com_member(plane, "Name"))
    with sw_part.sketch(model, plane_name) as second:
        sw_part.sketch_line(model, -.015, 0.0, .015, 0.0)
    feature = sw_part.loft_surface(model, (first, second))
    bodies, area = surface_evidence(model)
    expected = 30.0 * (20.0 + 30.0) / 2.0
    if len(bodies) != 1 or abs(area - expected) > 1e-3:
        raise RuntimeError(f"lofted surface mismatch: bodies={len(bodies)}, area={area}, expected={expected}")
    evidence = {"feature": str(get_com_member(feature, "Name")), "sections_mm": [20.0, 30.0],
                "separation_mm": 30.0, "body_count": len(bodies), "area_mm2": area}
    sw.QuitDoc(title); created.remove(title)
    return evidence


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        print(json.dumps({"status": "ok", "revolve": run_revolve(sw, created),
                          "sweep": run_sweep(sw, created), "loft": run_loft(sw, created)},
                         ensure_ascii=False))
    finally:
        for title in list(created):
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
