"""Real SolidWorks regression for a native Scale about a coordinate system."""

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
    return bodies[0], {
        "body_count": 1,
        "bounding_box_mm": box,
        "spans_mm": (box[3] - box[0], box[4] - box[1], box[5] - box[2]),
        "center_mm": tuple((box[index] + box[index + 3]) / 2.0 for index in range(3)),
        "volume_mm3": volume,
    }


def _assert_tuple(actual, expected, *, tolerance=1e-6):
    if any(not math.isclose(value, target, abs_tol=tolerance)
           for value, target in zip(actual, expected)):
        raise RuntimeError(f"geometry mismatch: actual={actual}, expected={expected}")


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
        body, before = _geometry(model)
        _assert_tuple(before["spans_mm"], (40.0, 30.0, 20.0))
        _assert_tuple(before["center_mm"], (0.0, 0.0, 0.0))

        coordinate_system = sw_part.coordinate_system_numeric(
            model, location=(.010, 0.0, 0.0),
        )
        coordinate_system_name = str(get_com_member(coordinate_system, "Name") or "")
        scale = sw_part.scale_feature(
            model, 2.0, about="coordinate_system",
            coordinate_system=coordinate_system, bodies=(body,),
        )
        evidence = sw_part.scale_feature_evidence(scale)
        _, after = _geometry(model)

        _assert_tuple(after["bounding_box_mm"], (-50.0, -30.0, -20.0, 30.0, 30.0, 20.0))
        _assert_tuple(after["spans_mm"], (80.0, 60.0, 40.0))
        _assert_tuple(after["center_mm"], (-10.0, 0.0, 0.0))
        if not math.isclose(after["volume_mm3"], 192000.0, abs_tol=1e-3):
            raise RuntimeError(f"Scale volume mismatch: {after}")
        if evidence["about"] != "coordinate_system" or not evidence["uniform"]:
            raise RuntimeError(f"coordinate-system feature data mismatch: {evidence}")
        if evidence["selected_body_count"] != 1:
            raise RuntimeError(f"selected-body scope mismatch: {evidence}")
        if not evidence["coordinate_system"]:
            raise RuntimeError(f"coordinate-system reference was not retained: {evidence}")
        if coordinate_system_name and evidence["coordinate_system"] != coordinate_system_name:
            raise RuntimeError(
                f"coordinate-system name mismatch: feature={coordinate_system_name}, data={evidence}"
            )
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("coordinate-system Scale rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            base, coordinate_system, scale,
        )):
            raise RuntimeError("coordinate-system Scale feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "coordinate_system": coordinate_system_name,
            "feature_data": evidence, "before": before, "after": after,
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
