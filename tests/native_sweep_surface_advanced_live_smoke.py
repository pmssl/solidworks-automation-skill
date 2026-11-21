"""Real SW2025 regression for guided and constant-twist swept surfaces.

No document is saved. Failed Parts are closed, and each later success replaces
the preceding successful task document so only the newest success remains open.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _area_evidence(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    area = sum(
        float(get_com_member(face, "GetArea")) * 1e6
        for body in bodies
        for face in tuple(get_com_member(body, "GetFaces") or ())
    )
    boxes = [
        [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]
        for body in bodies
    ]
    return bodies, area, boxes


def _base_sketches(model):
    with sw_part.sketch(model, "Top Plane") as profile:
        sw_part.sketch_line(model, -0.010, 0.0, 0.010, 0.0)
    with sw_part.sketch(model, "Front Plane") as path:
        sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)
    return profile, path


def _run_guided(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        profile, path = _base_sketches(model)
        with sw_part.sketch(model, "Front Plane") as guide:
            sw_part.sketch_line(model, -0.010, 0.0, -0.003, 0.040)
        feature = sw_part.sweep_surface(
            model, profile, path, guide_curves=(guide,), twist_control=2,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.sweep_surface_evidence(feature, model)
        bodies, area, boxes = _area_evidence(model)
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["guide_curve_count"] != 1
            or evidence["twist_control_type"] != 2
            or evidence["is_boss"] or len(bodies) != 1 or area <= 0.0
        ):
            raise RuntimeError(
                f"guided swept surface mismatch: rebuild={rebuilt}, "
                f"bodies={len(bodies)}, area={area}, evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "guide_curve", "document": title,
            "saved": False, "feature": str(get_com_member(feature, "Name")),
            "profile": profile, "path": path, "guide": guide,
            "surface_body_count": len(bodies), "surface_area_mm2": area,
            "body_boxes_mm": boxes, "evidence": evidence,
            "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def _run_constant_twist(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        profile, path = _base_sketches(model)
        angle = math.pi / 2.0
        feature = sw_part.sweep_surface(
            model, profile, path, twist_control=8, twist_angle=angle,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.sweep_surface_evidence(feature, model)
        bodies, area, boxes = _area_evidence(model)
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["guide_curve_count"] != 0
            or evidence["twist_control_type"] != 8
            or abs(abs(evidence["twist_angle"]) - angle) > 1e-9
            or evidence["is_boss"] or len(bodies) != 1 or area <= 800.5
        ):
            raise RuntimeError(
                f"constant-twist swept surface mismatch: rebuild={rebuilt}, "
                f"bodies={len(bodies)}, area={area}, evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "constant_twist_90deg",
            "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile, "path": path,
            "surface_body_count": len(bodies), "surface_area_mm2": area,
            "body_boxes_mm": boxes, "evidence": evidence,
            "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    rows = []
    failures = []
    for case in (_run_guided, _run_constant_twist):
        try:
            title, row = case(sw)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kept_title and kept_title != title:
                sw.QuitDoc(kept_title)
            kept_title = title
            sw.ActivateDoc2(title, False, 0)
        except Exception as exc:
            failures.append({"case": case.__name__, "error": str(exc)})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    if kept_title:
        sw.ActivateDoc2(kept_title, False, 0)
    result = {
        "status": "ok" if not failures else "failed",
        "results": rows, "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False))
    if failures:
        raise RuntimeError(f"advanced Swept Surface regression failures: {failures}")


if __name__ == "__main__":
    main()
