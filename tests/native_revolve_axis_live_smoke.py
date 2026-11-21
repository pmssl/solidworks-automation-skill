"""Real SolidWorks regression for a solid revolve about an independent axis."""

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
        front = plane_feature(model, "Front Plane")
        right = plane_feature(model, "Right Plane")
        axis = sw_part.reference_axis_from_planes(model, front, right, auto_size=False)
        axis_name = str(get_com_member(axis, "Name"))

        with sw_part.sketch(model, "Front Plane") as profile_name:
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_about_axis(
            model, profile_name, axis, math.tau,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"independent-axis revolve rebuild failed: error={error}")

        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"independent-axis revolve body count mismatch: {len(bodies)}")
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        expected_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(
                f"independent-axis revolve volume mismatch: {volume_mm3} != {expected_volume}"
            )

        bounds = [float(value) * 1000.0 for value in model.GetPartBox(True)]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        expected_spans = (10.0, 40.0, 40.0)
        if any(abs(actual - expected) > 0.1
               for actual, expected in zip(spans, expected_spans)):
            raise RuntimeError(f"independent-axis revolve bounds mismatch: {bounds}")

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("revolve definition selections were not accessible")
        try:
            axis_type = int(get_com_member(definition, "GetAxisType"))
            axis_object = get_com_member(definition, "Axis")
            if axis_object is None:
                raise RuntimeError("revolve definition did not retain its independent axis")
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "axis_feature": axis_name,
            "axis_type": axis_type,
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
