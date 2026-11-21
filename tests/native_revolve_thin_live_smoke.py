"""Real SolidWorks regression for a mid-plane thin revolve."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    thickness = 0.002
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as profile_name:
            axis = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_line(model, 0.015, -0.005, 0.015, 0.005)

        feature = sw_part.revolve_thin_feature(
            model, profile_name, math.tau, thickness, thin_type=2,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"thin revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"thin revolve body count mismatch: {len(bodies)}")

        expected_volume = math.pi * (16.0 ** 2 - 14.0 ** 2) * 10.0
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(f"thin revolve volume mismatch: {volume_mm3}")
        box = [float(value) * 1000.0 for value in bodies[0].GetBodyBox()]
        spans = sorted(abs(box[index + 3] - box[index]) for index in range(3))
        if any(abs(actual - expected) > 0.1
               for actual, expected in zip(spans, (10.0, 32.0, 32.0))):
            raise RuntimeError(f"thin revolve bounds mismatch: {box}")

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("thin revolve selections were not accessible")
        try:
            is_thin = bool(get_com_member(definition, "IsThinFeature"))
            thin_type = int(get_com_member(definition, "ThinWallType"))
            forward_thickness = float(get_com_member(
                definition, "GetWallThickness", True,
            ))
            reverse_thickness = float(get_com_member(
                definition, "GetWallThickness", False,
            ))
            angle = float(get_com_member(definition, "GetRevolutionAngle", True))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if not is_thin or thin_type != 2:
            raise RuntimeError(f"thin revolve definition mismatch: {is_thin}, {thin_type}")
        if abs(forward_thickness - thickness) > 1e-9:
            raise RuntimeError(
                f"mid-plane thin thickness readback mismatch: {forward_thickness}"
            )

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "is_thin": is_thin,
            "thin_wall_type": thin_type,
            "wall_thickness_mm": [forward_thickness * 1000.0,
                                  reverse_thickness * 1000.0],
            "angle_deg": math.degrees(angle),
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected_volume,
            "spans_mm": spans,
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
