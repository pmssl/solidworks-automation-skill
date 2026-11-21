"""Probe all five InsertRuledSurfaceFromEdge2 creation modes without saving."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _safe(obj, name, fallback=None):
    try:
        return get_com_member(obj, name)
    except Exception:
        return fallback


def _run_case(sw, creation_type):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        sw_part.planar_surface_from_sketch(model, sketch_name)
        bodies_before = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(bodies_before) != 1:
            raise RuntimeError(f"expected one base surface, found {len(bodies_before)}")
        candidates = []
        direction_candidates = []
        for edge in tuple(get_com_member(bodies_before[0], "GetEdges") or ()):
            try:
                geometry = sw_part.edge_geometry(edge)
            except (TypeError, ValueError, RuntimeError):
                continue
            if math.isclose(geometry["length"], .040, abs_tol=1e-9):
                candidates.append((geometry, edge))
            elif math.isclose(geometry["length"], .030, abs_tol=1e-9):
                direction_candidates.append((geometry, edge))
        candidates.sort(key=lambda item: item[0]["midpoint"])
        direction_candidates.sort(key=lambda item: item[0]["midpoint"])
        if len(candidates) != 2 or len(direction_candidates) != 2:
            raise RuntimeError(
                f"expected two 40/30 mm edge pairs, found {len(candidates)}/{len(direction_candidates)}"
            )
        feature = sw_part.ruled_surface_from_edges(
            model, candidates[-1][1], .010,
            surface_type=creation_type,
            angle_rad=math.radians(20.0) if creation_type == 2 else 0.0,
            direction_vector=(0.0, 0.0, 1.0) if creation_type == 4 else None,
            direction_references=(direction_candidates[-1][1],)
            if creation_type in (2, 3) else (),
        )
        evidence = sw_part.ruled_surface_evidence(feature, model)
        bodies_after = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        areas = [
            sum(float(get_com_member(face, "GetArea"))
                for face in tuple(get_com_member(body, "GetFaces") or ())) * 1e6
            for body in bodies_after
        ]
        boxes = [
            [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]
            for body in bodies_after
        ]
        error_code = int(get_com_member(feature, "GetErrorCode") or 0)
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        if error_code != 0 or not rebuilt or sum(areas) <= 1200.0 + 1.0:
            raise RuntimeError(
                f"ruled surface geometry failed: error={error_code}, rebuild={rebuilt}, areas={areas}"
            )
        completed = True
        return title, {
            "status": "ok", "document": title, "saved": False,
            "creation_type": creation_type,
            "feature_data_type": evidence["type"],
            "feature_data_distance_mm": evidence["distance"] * 1000.0,
            "feature_data_angle_deg": math.degrees(evidence["angle"]),
            "feature_data_use_vector": evidence["use_vector"],
            "direction_reference_count": evidence["direction_reference_count"],
            "surface_body_count": len(bodies_after),
            "areas_mm2": areas, "boxes_mm": boxes,
            "error_code": error_code, "rebuild": rebuilt,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    rows = []
    failures = []
    requested_types = [int(value) for value in sys.argv[1:]] or list(range(5))
    for creation_type in requested_types:
        try:
            title, row = _run_case(sw, creation_type)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kept_title and kept_title != title:
                sw.QuitDoc(kept_title)
            kept_title = title
            sw.ActivateDoc2(title, False, 0)
        except Exception as exc:
            failures.append({"creation_type": creation_type, "error": str(exc)})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    if kept_title:
        sw.ActivateDoc2(kept_title, False, 0)
    status = "ok" if not failures else "failed"
    print(json.dumps({"status": status, "results": rows, "failures": failures}, ensure_ascii=False))
    if failures:
        raise RuntimeError(f"ruled-surface mode regression failures: {failures}")


if __name__ == "__main__":
    main()
