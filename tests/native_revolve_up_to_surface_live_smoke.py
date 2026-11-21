"""Real SolidWorks regression for a revolve terminated by a reference plane."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def plane_feature(model, name):
    for candidate in sw_part._get_plane_name_candidates(name):
        feature = get_com_member(model, "FeatureByName", candidate)
        if feature is not None:
            return feature
    raise RuntimeError(f"reference plane was not found: {name}")


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        target = plane_feature(model, "Right Plane")
        with sw_part.sketch(model, "Front Plane") as profile_name:
            axis = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_to_reference(
            model, profile_name, target, "up_to_surface",
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"up-to-surface revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"up-to-surface body count mismatch: {len(bodies)}")

        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        expected_volume = full_volume / 4.0
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(
                f"up-to-surface volume mismatch: {volume_mm3} != {expected_volume}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("up-to-surface selections were not accessible")
        try:
            revolve_type = int(get_com_member(definition, "Type"))
            axis_type = int(get_com_member(definition, "GetAxisType"))
            angle = float(get_com_member(definition, "GetRevolutionAngle", True))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        box = [float(value) * 1000.0 for value in bodies[0].GetBodyBox()]
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "target_plane": str(get_com_member(target, "Name")),
            "revolve_type": revolve_type,
            "axis_type": axis_type,
            "reported_angle_deg": math.degrees(angle),
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected_volume,
            "body_box_mm": box,
            "rebuild": rebuilt,
        }, ensure_ascii=False))
    finally:
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
