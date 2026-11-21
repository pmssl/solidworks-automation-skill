"""Real SolidWorks regression for standard and elliptical native Dome features."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _geometry(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    box = tuple(float(value) * 1000.0 for value in get_com_member(bodies[0], "GetBodyBox"))
    volume = float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9
    return {"body_count": 1, "bounding_box_mm": box, "volume_mm3": volume}


def _only_face(model, **criteria):
    faces = sw_part.find_planar_faces(model, **criteria)
    if len(faces) != 1:
        raise RuntimeError(f"expected one semantic planar face, found {len(faces)}: {criteria}")
    return faces[0]


def _assert_close(actual, expected, tolerance=1e-6):
    if not math.isclose(float(actual), float(expected), abs_tol=tolerance):
        raise RuntimeError(f"value mismatch: actual={actual}, expected={expected}")


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
        before = _geometry(model)

        top = _only_face(model, area=.0012, center=(0.0, 0.0, .010), normal=(0.0, 0.0, 1.0))
        standard = sw_part.dome_feature(model, (top,), .008)
        standard_evidence = sw_part.dome_feature_evidence(standard, model)
        after_standard = _geometry(model)

        bottom = _only_face(model, area=.0012, center=(0.0, 0.0, -.010), normal=(0.0, 0.0, 1.0))
        elliptical = sw_part.dome_feature(model, (bottom,), .005, elliptical=True)
        elliptical_evidence = sw_part.dome_feature_evidence(elliptical, model)
        after_elliptical = _geometry(model)

        _assert_close(standard_evidence["height"] * 1000.0, 8.0)
        _assert_close(elliptical_evidence["height"] * 1000.0, 5.0)
        if standard_evidence["elliptical"] or not elliptical_evidence["elliptical"]:
            raise RuntimeError(
                f"Dome elliptical flags mismatch: {standard_evidence}, {elliptical_evidence}"
            )
        if standard_evidence["face_count"] != 1 or elliptical_evidence["face_count"] != 1:
            raise RuntimeError("Dome face counts were not retained")
        # IBody2.GetBodyBox is approximate for curved faces.  Use it only to
        # prove outward growth; exact dome heights come from FeatureData.
        if after_standard["bounding_box_mm"][5] <= 10.0:
            raise RuntimeError(f"standard Dome did not grow above the source face: {after_standard}")
        if after_elliptical["bounding_box_mm"][2] >= -10.0:
            raise RuntimeError(f"elliptical Dome did not grow below the source face: {after_elliptical}")
        if not (before["volume_mm3"] < after_standard["volume_mm3"] < after_elliptical["volume_mm3"]):
            raise RuntimeError(
                f"Dome material growth mismatch: {before}, {after_standard}, {after_elliptical}"
            )
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("Dome rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            base, standard, elliptical,
        )):
            raise RuntimeError("Dome feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "before": before,
            "standard": {"feature_data": standard_evidence, "geometry": after_standard},
            "elliptical": {"feature_data": elliptical_evidence, "geometry": after_elliptical},
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
