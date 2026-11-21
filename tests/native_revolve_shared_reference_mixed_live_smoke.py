"""Real regression for mixed end conditions to one revolve reference."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from tests.native_revolve_shared_reference_live_smoke import plane_feature


def radial_offset_sector_volume(r1, r2, height, offset):
    def antiderivative(radius):
        return (
            0.5 * radius * radius * math.acos(offset / radius)
            - 0.5 * offset * math.sqrt(radius * radius - offset * offset)
        )
    return height * (antiderivative(r2) - antiderivative(r1))


def main():
    offset_mm = 5.0
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

        feature = sw_part.revolve_feature_two_directions_to_same_reference(
            model, profile_name, target, "up_to_surface",
            direction2_end_condition="offset_from_surface",
            offset_distance2=offset_mm / 1000.0,
            offset_reverse2=True,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"mixed shared-reference revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"mixed shared-reference body count: {len(bodies)}")

        body = bodies[0]
        volume_mm3 = float(list(body.GetMassProperties(1.0))[3]) * 1e9
        quarter = 0.25 * math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        before = radial_offset_sector_volume(10.0, 20.0, 10.0, offset_mm)
        half = 0.5 * math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        candidates = {
            "quarter_plus_before_offset": quarter + before,
            "quarter_plus_beyond_offset": quarter + (half - before),
        }
        resolved_mode, expected = min(
            candidates.items(), key=lambda item: abs(volume_mm3 - item[1]),
        )
        if abs(volume_mm3 - expected) > 0.05:
            raise RuntimeError(
                f"mixed shared-reference volume mismatch: {volume_mm3}, {candidates}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("mixed shared-reference selections not accessible")
        try:
            revolve_type = int(get_com_member(definition, "Type"))
            axis_type = int(get_com_member(definition, "GetAxisType"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "shared_target": str(get_com_member(target, "Name")),
            "direction_end_conditions": ["up_to_surface", "offset_from_surface"],
            "direction2_offset_mm": offset_mm,
            "direction2_offset_reverse": True,
            "resolved_offset_mode": resolved_mode,
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
