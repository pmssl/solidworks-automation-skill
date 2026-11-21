"""Real SolidWorks regression for two distinct revolve end references."""

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
    requested_plane_angle = math.radians(60.0)
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        front = plane_feature(model, "Front Plane")
        right = plane_feature(model, "Right Plane")
        hinge_axis = sw_part.reference_axis_from_planes(model, front, right)
        angle_plane_ref = sw_part.reference_plane_at_angle(
            model, front, hinge_axis, requested_plane_angle,
        )
        angle_plane_geometry = sw_part.reference_plane_geometry(angle_plane_ref)
        angle_plane_feature = sw_part._last_model_feature(model)
        angle_plane_name = str(get_com_member(angle_plane_feature, "Name"))

        with sw_part.sketch(model, "Front Plane") as profile_name:
            axis = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_two_references(
            model, profile_name, right, angle_plane_feature,
            "up_to_surface", "up_to_surface",
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"two-reference revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"two-reference body count mismatch: {len(bodies)}")

        body = bodies[0]
        volume_mm3 = float(list(body.GetMassProperties(1.0))[3]) * 1e9
        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        candidate_angles = (150.0, 210.0)
        candidates = {
            f"{angle:.0f}_degrees": full_volume * angle / 360.0
            for angle in candidate_angles
        }
        resolved_angle, expected = min(
            candidates.items(), key=lambda item: abs(volume_mm3 - item[1]),
        )
        if abs(volume_mm3 - expected) > 0.05:
            raise RuntimeError(
                f"two-reference volume mismatch: {volume_mm3}, {candidates}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("two-reference selections were not accessible")
        try:
            revolve_type = int(get_com_member(definition, "Type"))
            axis_type = int(get_com_member(definition, "GetAxisType"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "direction1_target": str(get_com_member(right, "Name")),
            "direction2_target": angle_plane_name,
            "angle_plane_normal": angle_plane_geometry["normal"],
            "requested_angle_plane_deg": math.degrees(requested_plane_angle),
            "resolved_total_revolve": resolved_angle,
            "revolve_type_readback": revolve_type,
            "axis_type": axis_type,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected,
            "analytic_candidates_mm3": candidates,
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
