"""Real SolidWorks regression for a revolve about another sketch's line."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as axis_sketch_name:
            axis_segment = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis_segment, True)

        with sw_part.sketch(model, "Front Plane") as profile_name:
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_about_sketch_segment(
            model, profile_name, axis_segment, math.tau,
        )
        datum_axis = None
        for candidate in ("Axis1", "基准轴1"):
            datum_axis = get_com_member(model, "FeatureByName", candidate)
            if datum_axis is not None:
                break
        if datum_axis is None:
            raise RuntimeError("public sketch-axis revolve did not retain a datum-axis feature")
        datum_axis_name = str(get_com_member(datum_axis, "Name"))
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"external-sketch-axis revolve failed: error={error}")

        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"external-sketch-axis body count mismatch: {len(bodies)}")
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        expected_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        if abs(volume_mm3 - expected_volume) > 0.05:
            raise RuntimeError(f"external-sketch-axis volume mismatch: {volume_mm3}")

        bounds = [float(value) * 1000.0 for value in bodies[0].GetBodyBox()]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        if any(abs(actual - expected) > 0.1
               for actual, expected in zip(spans, (10.0, 40.0, 40.0))):
            raise RuntimeError(f"external-sketch-axis bounds mismatch: {bounds}")

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("revolve definition selections were not accessible")
        try:
            axis_type = int(get_com_member(definition, "GetAxisType"))
            axis_object = get_com_member(definition, "Axis")
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if axis_type != 5 or axis_object is None:
            raise RuntimeError(f"expected swSelDATUMAXES (5), got {axis_type}")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "axis_sketch": str(axis_sketch_name),
            "datum_axis": datum_axis_name,
            "axis_type": axis_type,
            "solid_body_count": len(bodies),
            "volume_mm3": volume_mm3,
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
