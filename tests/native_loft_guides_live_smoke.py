"""Real SolidWorks regression for a boss loft driven by a native 3D guide."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def circle_section(engine, title, plane_name, radius_mm):
    begun = engine.begin(title, plane_name)
    token = begun["session_id"]
    engine.circle(token, 0.0, 0.0, radius_mm)
    engine.auto_define(token)
    engine.finish(token)
    return begun["sketch"]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )
        plane = engine.offset_plane(title, "Front Plane", 30.0)
        base_name = circle_section(engine, title, "Front Plane", 20.0)
        top_name = circle_section(engine, title, plane["feature"], 10.0)
        with sw_part.sketch_3d(model) as guide_name:
            sw_part.sketch_line_3d(
                model, (0.020, 0.0, 0.0), (0.010, 0.0, 0.030)
            )
        feature = sw_part.loft_boss_with_guides(
            model, (base_name, top_name), (guide_name,),
            guide_curve_influence=3,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        if error != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"guide loft rebuild failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"guide loft body count mismatch: {len(bodies)}")
        definition = get_com_member(feature, "GetDefinition")
        guide_count = int(get_com_member(definition, "GetGuideCurvesCount"))
        if guide_count != 1:
            raise RuntimeError(f"guide loft count mismatch: {guide_count}")
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        expected = math.pi * 30.0 / 3.0 * (20.0 ** 2 + 20.0 * 10.0 + 10.0 ** 2)
        volume_delta = volume_mm3 - expected
        if abs(volume_delta) > 5.0:
            raise RuntimeError(f"guide loft volume mismatch: {volume_mm3} != {expected}")
        bounds = [float(value) * 1000.0 for value in model.GetPartBox(True)]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        if any(abs(actual - expected_span) > 0.1
               for actual, expected_span in zip(spans, (30.0, 40.0, 40.0))):
            raise RuntimeError(f"guide loft bounds mismatch: {bounds}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [base_name, top_name],
            "guide": guide_name,
            "guide_count": guide_count,
            "volume_mm3": volume_mm3,
            "analytic_frustum_delta_mm3": volume_delta,
            "spans_mm": spans,
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
