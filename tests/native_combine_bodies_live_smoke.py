"""Real SolidWorks regression for native multibody Combine operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def volume_mm3(body):
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def make_multibody(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created.append(title)
    with sw_part.sketch(model, "Front Plane") as first_sketch:
        sw_part.sketch_rectangle(model, 0, 0, .040, .030)
    sw_part.extrude_boss_midplane(model, first_sketch, .020)
    with sw_part.sketch(model, "Front Plane") as second_sketch:
        sw_part.sketch_rectangle(model, .015, 0, .020, .020)
    sw_part.extrude_boss_midplane(model, second_sketch, .020, merge=False)
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 2:
        raise RuntimeError(f"expected two pre-combine bodies, got {len(bodies)}")
    return model, title, bodies


def run_case(sw, created, operation, expected_volume):
    model, title, bodies = make_multibody(sw, created)
    before = sorted(volume_mm3(body) for body in bodies)
    main_body = max(bodies, key=volume_mm3) if operation == 15902 else None
    feature = sw_part.combine_bodies(model, operation, bodies, main_body=main_body)
    rebuild = bool(model.ForceRebuild3(False))
    after_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(after_bodies) != 1:
        raise RuntimeError(f"combine body count mismatch: {len(after_bodies)}")
    after = volume_mm3(after_bodies[0])
    if abs(after - expected_volume) > 1e-4:
        raise RuntimeError(f"combine volume mismatch: {after} != {expected_volume}")
    result = {
        "feature": str(get_com_member(feature, "Name")),
        "type": str(get_com_member(feature, "GetTypeName2")),
        "before_volumes_mm3": before,
        "after_volume_mm3": after,
        "body_count": len(after_bodies),
        "rebuild": rebuild,
    }
    sw.QuitDoc(title); created.remove(title)
    return result


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        results = {
            "add": run_case(sw, created, 15903, 26000.0),
            "cut": run_case(sw, created, 15902, 18000.0),
            "intersect": run_case(sw, created, 15901, 6000.0),
        }
        print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False))
    finally:
        for title in list(created):
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
