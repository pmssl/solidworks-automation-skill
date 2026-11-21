"""Real SW2025 regression for advanced native Lofted Surface semantics.

The probe never saves. Failed temporary Parts are closed; after a later case
succeeds, the superseded successful task document is closed and only the newest
successful task document remains open.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _surface_area_mm2(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    return bodies, sum(
        float(get_com_member(face, "GetArea")) * 1e6
        for body in bodies
        for face in tuple(get_com_member(body, "GetFaces") or ())
    )


def _profiles(model):
    plane = sw_part.offset_plane(model, "Front Plane", 0.030)
    plane_name = str(get_com_member(plane, "Name"))
    with sw_part.sketch(model, "Front Plane") as first:
        sw_part.sketch_line(model, -0.010, 0.0, 0.010, 0.0)
    with sw_part.sketch(model, plane_name) as second:
        sw_part.sketch_line(model, -0.015, 0.0, 0.015, 0.0)
    return first, second


def _run_guide(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        first, second = _profiles(model)
        with sw_part.sketch_3d(model) as guide:
            sw_part.sketch_spline_3d(
                model, (
                    (-0.010, 0.0, 0.0),
                    (-0.0125, 0.006, 0.015),
                    (-0.015, 0.0, 0.030),
                ),
            )
        feature = sw_part.loft_surface(
            model, (first, second),
            guide_curves=(guide,),
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.loft_surface_evidence(feature, model)
        bodies, area = _surface_area_mm2(model)
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or len(bodies) != 1 or area <= 750.5
            or evidence["feature_type"] != "BlendRefSurface"
        ):
            raise RuntimeError(
                f"guide lofted surface mismatch: "
                f"rebuild={rebuilt}, bodies={len(bodies)}, area={area}, "
                f"evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "guide_curve",
            "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first, second], "guide": guide,
            "surface_body_count": len(bodies),
            "surface_area_mm2": area, "evidence": evidence,
            "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def _run_centerline(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        first, second = _profiles(model)
        with sw_part.sketch_3d(model) as centerline:
            sw_part.sketch_spline_3d(
                model, (
                    (0.0, 0.0, 0.0),
                    (0.0, 0.006, 0.015),
                    (0.0, 0.0, 0.030),
                ),
            )
        feature = sw_part.loft_surface(
            model, (first, second), centerline=centerline,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.loft_surface_evidence(feature, model)
        bodies, area = _surface_area_mm2(model)
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or len(bodies) != 1 or area <= 750.5
            or evidence["feature_type"] != "BlendRefSurface"
        ):
            raise RuntimeError(
                f"centerline lofted surface mismatch: "
                f"rebuild={rebuilt}, bodies={len(bodies)}, area={area}, "
                f"evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "centerline",
            "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first, second], "centerline": centerline,
            "surface_body_count": len(bodies), "surface_area_mm2": area,
            "evidence": evidence, "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def _run_direction_vectors(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        first, second = _profiles(model)
        with sw_part.sketch_3d(model):
            direction_line = sw_part.sketch_line_3d(
                model, (0.0, 0.0, 0.0), (0.0, 0.030, 0.0),
            )
        axis = sw_part.reference_axis_from_sketch_line(model, direction_line)
        feature = sw_part.loft_surface(
            model, (first, second),
            start_matching_type=2, end_matching_type=2,
            start_tangent_reference=axis, end_tangent_reference=axis,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.loft_surface_evidence(feature, model)
        bodies, area = _surface_area_mm2(model)
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or len(bodies) != 1 or area <= 750.5
            or evidence["feature_type"] != "BlendRefSurface"
        ):
            raise RuntimeError(
                f"direction-vector lofted surface mismatch: "
                f"rebuild={rebuilt}, bodies={len(bodies)}, area={area}, "
                f"evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "start_end_direction_vectors",
            "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "direction_axis": str(get_com_member(axis, "Name")),
            "surface_body_count": len(bodies), "surface_area_mm2": area,
            "evidence": evidence, "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    rows = []
    failures = []
    for case in (_run_guide, _run_centerline, _run_direction_vectors):
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
        raise RuntimeError(f"advanced Lofted Surface regression failures: {failures}")


if __name__ == "__main__":
    main()
