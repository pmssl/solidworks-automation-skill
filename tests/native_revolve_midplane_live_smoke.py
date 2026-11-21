"""Real SolidWorks regression for a symmetric mid-plane revolve."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    total_angle = math.radians(150.0)
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as profile_name:
            axis = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_midplane(
            model, profile_name, total_angle,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"mid-plane revolve failed: error={error}")

        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"mid-plane revolve body count mismatch: {len(bodies)}")
        body = bodies[0]
        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        expected_volume = full_volume * 150.0 / 360.0
        volume_mm3 = float(list(body.GetMassProperties(1.0))[3]) * 1e9
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(
                f"mid-plane revolve volume mismatch: {volume_mm3} != {expected_volume}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("mid-plane revolve selections were not accessible")
        try:
            revolve_type = int(get_com_member(definition, "Type"))
            actual_angle = float(get_com_member(
                definition, "GetRevolutionAngle", True,
            ))
            axis_type = int(get_com_member(definition, "GetAxisType"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if revolve_type != 1:
            raise RuntimeError(
                f"expected swRevolveTypeMidPlane (1), got {revolve_type}"
            )
        if abs(actual_angle - total_angle) > 1e-9:
            raise RuntimeError(
                f"mid-plane total-angle readback mismatch: {actual_angle}"
            )

        body_box = [float(value) * 1000.0 for value in body.GetBodyBox()]
        half_angle = total_angle / 2.0
        expected_box = [
            10.0 * math.cos(half_angle), -5.0,
            -20.0 * math.sin(half_angle),
            20.0, 5.0, 20.0 * math.sin(half_angle),
        ]
        box_delta = [
            actual - expected
            for actual, expected in zip(body_box, expected_box)
        ]
        if max(abs(value) for value in box_delta) > 0.05:
            raise RuntimeError(
                f"mid-plane symmetric body box mismatch: {body_box} != {expected_box}"
            )

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "revolve_type": revolve_type,
            "axis_type": axis_type,
            "total_angle_deg": math.degrees(actual_angle),
            "half_angle_each_side_deg": math.degrees(actual_angle) / 2.0,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected_volume,
            "body_box_mm": body_box,
            "body_box_delta_mm": box_delta,
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
