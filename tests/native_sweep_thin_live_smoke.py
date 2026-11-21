"""Real SolidWorks regression for a native mid-plane thin sweep."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main(thin_type=2, endpoint_profile=False, closed_profile=True):
    thickness = 0.002
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Top Plane") as profile_name:
            if closed_profile:
                sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
            elif endpoint_profile:
                sw_part.sketch_line(model, 0.0, 0.0, 0.010, 0.0)
            else:
                sw_part.sketch_line(model, -0.005, 0.0, 0.005, 0.0)
        with sw_part.sketch(model, "Front Plane") as path_name:
            sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)

        feature = sw_part.sweep_thin_feature(
            model, profile_name, path_name, thickness, thin_type=thin_type,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"thin sweep failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"thin sweep body count mismatch: {len(bodies)}")

        body = bodies[0]
        volume_mm3 = float(list(body.GetMassProperties(1.0))[3]) * 1e9
        if closed_profile:
            volume_candidates = {
                "inside": math.pi * (5.0 ** 2 - 3.0 ** 2) * 40.0,
                "midplane": math.pi * (6.0 ** 2 - 4.0 ** 2) * 40.0,
                "outside": math.pi * (7.0 ** 2 - 5.0 ** 2) * 40.0,
            }
            resolved_profile_mode, expected_volume = min(
                volume_candidates.items(),
                key=lambda item: abs(volume_mm3 - item[1]),
            )
        else:
            volume_candidates = {"open_line": 10.0 * 2.0 * 40.0}
            resolved_profile_mode, expected_volume = next(iter(volume_candidates.items()))
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(
                f"thin sweep volume mismatch: {volume_mm3}, {volume_candidates}"
            )
        definition = get_com_member(feature, "GetDefinition")
        thin_feature = bool(get_com_member(definition, "ThinFeature"))
        actual_thin_type = int(get_com_member(definition, "ThinWallType"))
        actual_thickness = float(get_com_member(
            definition, "GetWallThickness", True,
        ))
        direction = int(get_com_member(definition, "Direction"))
        if not thin_feature or actual_thin_type != int(thin_type):
            raise RuntimeError(
                "thin sweep readback mismatch: "
                f"thin={thin_feature}, type={actual_thin_type}"
            )
        if abs(actual_thickness - thickness) > 1e-12:
            raise RuntimeError(f"thin sweep thickness mismatch: {actual_thickness}")

        box = [float(value) * 1000.0 for value in body.GetBodyBox()]
        spans = sorted(abs(box[index + 3] - box[index]) for index in range(3))
        if not closed_profile:
            expected_spans = [2.0, 10.0, 40.0]
            if max(abs(a - e) for a, e in zip(spans, expected_spans)) > 0.05:
                raise RuntimeError(f"thin sweep spans mismatch: {spans}")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile_name,
            "path": path_name,
            "thin_feature": thin_feature,
            "thin_type": actual_thin_type,
            "total_midplane_thickness_mm": actual_thickness * 1000.0,
            "direction": direction,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected_volume,
            "resolved_profile_mode": resolved_profile_mode,
            "analytic_volume_candidates_mm3": volume_candidates,
            "body_box_mm": box,
            "spans_mm": spans,
            "rebuild": rebuilt,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        target_title = title if completed else original_title
        if target_title:
            try:
                sw.ActivateDoc2(target_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    selected_type = 2
    if "--thin-type" in sys.argv:
        selected_type = int(sys.argv[sys.argv.index("--thin-type") + 1])
    main(
        thin_type=selected_type,
        endpoint_profile="--endpoint-profile" in sys.argv,
        closed_profile="--open-profile" not in sys.argv,
    )
