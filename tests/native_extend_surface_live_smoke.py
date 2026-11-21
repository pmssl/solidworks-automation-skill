"""Real SW2025 Same Surface and Linear distance extension regression."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _run_case(sw, linear):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.040, 0.030)
        sw_part.planar_surface_from_sketch(model, sketch_name)
        before_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(before_bodies) != 1:
            raise RuntimeError(f"base surface count mismatch: {len(before_bodies)}")
        edges = []
        for edge in tuple(get_com_member(before_bodies[0], "GetEdges") or ()):
            geometry = sw_part.edge_geometry(edge)
            if math.isclose(geometry["length"], 0.040, abs_tol=1e-9):
                edges.append((geometry, edge))
        edges.sort(key=lambda pair: pair[0]["midpoint"])
        if len(edges) != 2:
            raise RuntimeError(f"expected two 40 mm edges, got {len(edges)}")
        feature = sw_part.extend_surface_distance(
            model, edges[-1][1], 0.010, linear=linear,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.extend_surface_evidence(feature, model)
        bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area = sum(
            float(get_com_member(face, "GetArea")) * 1e6
            for body in bodies
            for face in tuple(get_com_member(body, "GetFaces") or ())
        )
        # SW2025 FeatureData uses 0=Linear and 1=Same Surface.
        expected_type = 0 if linear else 1
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["type"] != expected_type
            or evidence["end_condition"] != 0
            or abs(evidence["distance"] - 0.010) > 1e-12
            or evidence["item_count"] != 1
            or len(bodies) != 1 or abs(area - 1600.0) > 1e-3
        ):
            raise RuntimeError(
                f"surface extension mismatch: linear={linear}, rebuild={rebuilt}, "
                f"bodies={len(bodies)}, area={area}, evidence={evidence}"
            )
        completed = True
        return title, {
            "status": "ok", "case": "linear" if linear else "same_surface",
            "document": title, "saved": False,
            "feature": str(get_com_member(feature, "Name")),
            "surface_body_count": len(bodies), "surface_area_mm2": area,
            "evidence": evidence, "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def _run_to_point(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.040, 0.030)
        sw_part.planar_surface_from_sketch(model, sketch_name)
        bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        edges = []
        for edge in tuple(get_com_member(bodies[0], "GetEdges") or ()):
            geometry = sw_part.edge_geometry(edge)
            if math.isclose(geometry["length"], 0.040, abs_tol=1e-9):
                edges.append((geometry, edge))
        edges.sort(key=lambda pair: pair[0]["midpoint"])
        with sw_part.sketch_3d(model):
            target_point = sw_part.sketch_point_3d(model, 0.0, 0.025, 0.0)
        feature = sw_part.extend_surface(
            model, edges[-1][1], end_condition=1,
            terminal_reference=target_point,
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.extend_surface_evidence(feature, model)
        bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area = sum(float(get_com_member(face, "GetArea")) * 1e6
                   for body in bodies
                   for face in tuple(get_com_member(body, "GetFaces") or ()))
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["end_condition"] != 1 or evidence["item_count"] != 1
            or len(bodies) != 1 or abs(area - 1600.0) > 1e-3
        ):
            raise RuntimeError(
                f"to-point extension mismatch: bodies={len(bodies)}, "
                f"area={area}, evidence={evidence}"
            )
        completed = True
        return title, {"status": "ok", "case": "up_to_point",
                       "document": title, "saved": False,
                       "feature": str(get_com_member(feature, "Name")),
                       "surface_body_count": len(bodies),
                       "surface_area_mm2": area, "evidence": evidence,
                       "rebuild": rebuilt}
    finally:
        if not completed:
            sw.QuitDoc(title)


def _run_to_surface(sw):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as block_profile:
            sw_part.sketch_rectangle(model, 0.0, 0.030, 0.060, 0.010)
        sw_part.extrude_boss_midplane(model, block_profile, 0.010)
        solid_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        target_faces = []
        for face in tuple(get_com_member(solid_bodies[0], "GetFaces") or ()):
            try:
                geometry = sw_part.planar_face_geometry(face)
            except (TypeError, ValueError, RuntimeError):
                continue
            center_mm = tuple(value * 1000.0 for value in geometry["center"])
            if abs(center_mm[1] - 25.0) < 1e-6:
                target_faces.append(face)
        if len(target_faces) != 1:
            raise RuntimeError(f"target solid face count mismatch: {len(target_faces)}")
        with sw_part.sketch(model, "Front Plane") as surface_profile:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.040, 0.030)
        sw_part.planar_surface_from_sketch(model, surface_profile)
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        edges = []
        for edge in tuple(get_com_member(surface_bodies[0], "GetEdges") or ()):
            geometry = sw_part.edge_geometry(edge)
            if math.isclose(geometry["length"], 0.040, abs_tol=1e-9):
                edges.append((geometry, edge))
        edges.sort(key=lambda pair: pair[0]["midpoint"])
        feature = sw_part.extend_surface(
            model, edges[-1][1], end_condition=2,
            terminal_reference=target_faces[0],
        )
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        evidence = sw_part.extend_surface_evidence(feature, model)
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area = sum(float(get_com_member(face, "GetArea")) * 1e6
                   for body in surface_bodies
                   for face in tuple(get_com_member(body, "GetFaces") or ()))
        if (
            not rebuilt or evidence["feature_error_code"] != 0
            or evidence["end_condition"] != 2 or evidence["item_count"] != 1
            or len(surface_bodies) != 1 or abs(area - 1600.0) > 1e-3
        ):
            raise RuntimeError(
                f"to-surface extension mismatch: bodies={len(surface_bodies)}, "
                f"area={area}, evidence={evidence}"
            )
        completed = True
        return title, {"status": "ok", "case": "up_to_solid_face",
                       "document": title, "saved": False,
                       "feature": str(get_com_member(feature, "Name")),
                       "surface_body_count": len(surface_bodies),
                       "surface_area_mm2": area, "evidence": evidence,
                       "rebuild": rebuilt}
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    rows, failures = [], []
    cases = [
        (lambda app: _run_case(app, False)),
        (lambda app: _run_case(app, True)),
        _run_to_point,
        _run_to_surface,
    ]
    for case in cases:
        try:
            title, row = case(sw)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kept_title and kept_title != title:
                sw.QuitDoc(kept_title)
            kept_title = title
            sw.ActivateDoc2(title, False, 0)
        except Exception as exc:
            failures.append({"case": getattr(case, "__name__", "case"), "error": str(exc)})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    if kept_title:
        sw.ActivateDoc2(kept_title, False, 0)
    print(json.dumps({
        "status": "ok" if not failures else "failed",
        "results": rows, "failures": failures,
    }, ensure_ascii=False))
    if failures:
        raise RuntimeError(f"Surface Extend regression failures: {failures}")


if __name__ == "__main__":
    main()
