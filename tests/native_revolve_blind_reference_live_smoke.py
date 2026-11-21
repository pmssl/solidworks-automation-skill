"""Real regression for one blind and one reference-terminated revolve side."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from tests.native_revolve_shared_reference_live_smoke import plane_feature


def main():
    blind_angle = math.radians(45.0)
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

        feature = sw_part.revolve_feature_blind_and_reference(
            model, profile_name, blind_angle, target, "up_to_surface",
            blind_in_direction1=True,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"blind/reference revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"blind/reference body count mismatch: {len(bodies)}")

        body = bodies[0]
        volume_mm3 = float(list(body.GetMassProperties(1.0))[3]) * 1e9
        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        expected = full_volume * 135.0 / 360.0
        if abs(volume_mm3 - expected) > 0.05:
            raise RuntimeError(
                f"blind/reference volume mismatch: {volume_mm3} != {expected}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("blind/reference selections were not accessible")
        try:
            revolve_type = int(get_com_member(definition, "Type"))
            axis_type = int(get_com_member(definition, "GetAxisType"))
            direction1_angle = float(get_com_member(
                definition, "GetRevolutionAngle", True,
            ))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "blind_direction": 1,
            "blind_angle_deg": math.degrees(direction1_angle),
            "reference_direction": 2,
            "reference_target": str(get_com_member(target, "Name")),
            "reference_selection_mark": 64,
            "resolved_total_angle_deg": 135.0,
            "revolve_type_readback": revolve_type,
            "axis_type": axis_type,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected,
            "body_box_mm": [float(v) * 1000.0 for v in body.GetBodyBox()],
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
