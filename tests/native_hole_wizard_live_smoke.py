"""Real SolidWorks regression for the native HoleWizard5 simple-hole whitelist."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def volume_mm3(model):
    body = (model.GetBodies2(0, False) or ())[0]
    return float(list(body.GetMassProperties(1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    title = None
    try:
        model = new_document(sw, "part")
        title = str(get_com_member(model, "GetTitle"))
        native = NativeParametric(connect=lambda: connect_solidworks(wait_seconds=1), part_ops=lambda: sw_part)
        begun = native.begin(title, "Front Plane")
        native.rectangle(begun["session_id"], 40, 30)
        native.auto_define(begun["session_id"])
        native.finish(begun["session_id"])
        base = sw_part.extrude_boss_midplane(model, begun["sketch"], .020)
        if base is None or int(get_com_member(base, "GetErrorCode")) != 0:
            raise RuntimeError("base failed")
        faces = sw_part.find_planar_faces(
            model, area=.0012, center=(0, 0, .010), tolerance=1e-8
        )
        if len(faces) != 1:
            raise RuntimeError(f"top face resolution failed: {len(faces)}")
        before = volume_mm3(model)
        feature = None
        chosen_size = None
        for size_name in ("6.0mm", "6mm", "6.00mm", "6.0", "6", ""):
            try:
                feature = sw_part.hole_wizard_simple(
                    model, faces[0], (.007, -.004, .010), .006,
                    through=True, size_name=size_name,
                )
            except RuntimeError:
                continue
            chosen_size = size_name
            break
        if feature is None:
            raise RuntimeError("Hole Wizard rejected all ANSI Metric M6 drill-size candidates")
        error = int(get_com_member(feature, "GetErrorCode"))
        if error != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"Hole Wizard feature/rebuild failed: {error}")
        definition = get_com_member(feature, "GetDefinition")
        diameter_mm = float(get_com_member(definition, "Diameter")) * 1000.0
        end_condition = int(get_com_member(definition, "EndCondition"))
        after = volume_mm3(model)
        expected = 40 * 30 * 20 - math.pi * 3 ** 2 * 20
        if abs(diameter_mm - 6.0) > 1e-5 or end_condition != 1 or abs(after - expected) > 0.5:
            raise RuntimeError(
                f"Hole Wizard mismatch: diameter={diameter_mm}, end={end_condition}, volume={after}"
            )
        circles = []
        for edge in sw_part.solid_edges(model):
            curve = get_com_member(edge, "GetCurve")
            if curve is not None and bool(get_com_member(curve, "IsCircle")):
                params = list(get_com_member(curve, "CircleParams") or ())
                if len(params) >= 7 and abs(float(params[6]) - .003) < 1e-7:
                    circles.append([float(value) * 1000.0 for value in params[:7]])
        if len(circles) < 2:
            raise RuntimeError(f"Hole Wizard circular B-Rep evidence missing: {circles}")
        print(json.dumps({"status": "ok", "feature": str(feature.Name),
                          "diameter_mm": diameter_mm, "end_condition": end_condition,
                          "size_name": chosen_size,
                          "volume_before_mm3": before, "volume_after_mm3": after,
                          "circle_params_mm": circles}, ensure_ascii=False))
    finally:
        if title:
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
