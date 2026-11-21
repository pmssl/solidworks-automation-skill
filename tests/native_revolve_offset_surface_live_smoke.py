"""Real SolidWorks regression for a revolve offset from a reference plane."""

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


def radial_offset_sector_volume(r1, r2, height, offset):
    """Volume before x=offset for a radial sweep toward the x=0 plane."""
    def antiderivative(radius):
        return (
            0.5 * radius * radius * math.acos(offset / radius)
            - 0.5 * offset * math.sqrt(radius * radius - offset * offset)
        )
    return height * (antiderivative(r2) - antiderivative(r1))


def main(offset_reverse=False):
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

        feature = sw_part.revolve_feature_to_reference(
            model, profile_name, target, "offset_from_surface",
            offset_distance=offset_mm / 1000.0,
            offset_reverse=bool(offset_reverse),
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"offset-from-surface revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"offset-from-surface body count mismatch: {len(bodies)}")
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9

        before_volume = radial_offset_sector_volume(10.0, 20.0, 10.0, offset_mm)
        half_volume = 0.5 * math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        beyond_volume = half_volume - before_volume
        candidates = {"before_surface": before_volume, "beyond_surface": beyond_volume}
        offset_mode, expected_volume = min(
            candidates.items(), key=lambda item: abs(volume_mm3 - item[1]),
        )
        if abs(volume_mm3 - expected_volume) > 0.1:
            raise RuntimeError(
                f"offset-from-surface volume mismatch: {volume_mm3}, candidates={candidates}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("offset-from-surface selections were not accessible")
        try:
            axis_type = int(get_com_member(definition, "GetAxisType"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        box = [float(value) * 1000.0 for value in bodies[0].GetBodyBox()]
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "target_plane": str(get_com_member(target, "Name")),
            "offset_mm": offset_mm,
            "offset_reverse": bool(offset_reverse),
            "resolved_offset_mode": offset_mode,
            "axis_type": axis_type,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
            "analytic_volume_delta_mm3": volume_mm3 - expected_volume,
            "analytic_candidates_mm3": candidates,
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
    main(offset_reverse="--reverse" in sys.argv[1:])
