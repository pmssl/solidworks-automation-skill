"""Live SolidWorks smoke test for a native profile-and-path boss sweep."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def main() -> None:
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    temp_title = None
    try:
        model = new_document(sw, "part")
        temp_title = str(get_com_member(model, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )

        profile = engine.begin(temp_title, "Right Plane")
        profile_token = profile["session_id"]
        engine.circle(profile_token, 0, 0, 3)
        engine.auto_define(profile_token)
        engine.finish(profile_token)

        path = engine.begin(temp_title, "Front Plane")
        path_token = path["session_id"]
        engine.line(path_token, 0, 0, 40, 0)
        engine.auto_define(path_token)
        engine.finish(path_token)

        swept = engine.sweep(path_token, profile["sketch"])
        state = engine.model_state(path_token)
        if swept["solid_body_count"] != 1 or swept["cut"]:
            raise RuntimeError(f"Boss sweep topology mismatch: {swept}")
        if swept["profile_segment_count"] != 1 or swept["path_segment_count"] != 1:
            raise RuntimeError(f"Sweep sketch readback mismatch: {swept}")
        bounds = [float(value) * 1000.0 for value in (model.GetPartBox(True) or ())]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        if len(spans) != 3 or any(abs(actual - expected) > 0.05
                                  for actual, expected in zip(spans, [6.0, 6.0, 40.0])):
            raise RuntimeError(f"Unexpected sweep body size: spans={spans}, bounds={bounds}")
        bodies = model.GetBodies2(0, False) or ()
        mass = list(bodies[0].GetMassProperties(1.0))
        volume_mm3 = float(mass[3]) * 1e9
        expected_volume = math.pi * 3.0 ** 2 * 40.0
        if abs(volume_mm3 - expected_volume) > 0.2:
            raise RuntimeError(
                f"Sweep volume mismatch: {volume_mm3} != {expected_volume} mm^3"
            )
        names = [row["name"] for row in state["features"]]
        if profile["sketch"] not in names or path["sketch"] not in names or swept["feature"] not in names:
            raise RuntimeError(f"Sweep feature tree verification failed: {names}")

        cut_profile = engine.begin(temp_title, "Right Plane")
        cut_profile_token = cut_profile["session_id"]
        engine.circle(cut_profile_token, 0, 0, 1)
        engine.auto_define(cut_profile_token)
        engine.finish(cut_profile_token)
        cut_path = engine.begin(temp_title, "Front Plane")
        cut_path_token = cut_path["session_id"]
        engine.line(cut_path_token, 0, 0, 40, 0)
        engine.auto_define(cut_path_token)
        engine.finish(cut_path_token)
        cut = engine.sweep(cut_path_token, cut_profile["sketch"], cut=True)
        if not cut["cut"] or cut["solid_body_count"] != 1:
            raise RuntimeError(f"Cut sweep topology mismatch: {cut}")
        cut_state = engine.model_state(cut_path_token)
        cut_names = [row["name"] for row in cut_state["features"]]
        if cut_profile["sketch"] not in cut_names or cut_path["sketch"] not in cut_names or cut["feature"] not in cut_names:
            raise RuntimeError(f"Cut sweep feature tree verification failed: {cut_names}")
        cut_bodies = model.GetBodies2(0, False) or ()
        cut_mass = list(cut_bodies[0].GetMassProperties(1.0))
        cut_volume_mm3 = float(cut_mass[3]) * 1e9
        expected_cut_volume = math.pi * (3.0 ** 2 - 1.0 ** 2) * 40.0
        if abs(cut_volume_mm3 - expected_cut_volume) > 0.2:
            raise RuntimeError(
                f"Cut sweep volume mismatch: {cut_volume_mm3} != {expected_cut_volume} mm^3"
            )
        print(json.dumps({
            "status": "ok", "document": temp_title,
            "profile_sketch": profile["sketch"], "path_sketch": path["sketch"],
            "feature": swept["feature"], "feature_type": swept["feature_type"],
            "profile_type_code": swept["profile_type_code"],
            "path_type_code": swept["path_type_code"],
            "twist_control_type": swept["twist_control_type"],
            "solid_body_count": swept["solid_body_count"],
            "spans_mm": spans, "volume_mm3": volume_mm3,
            "cut_feature": cut["feature"], "cut_feature_type": cut["feature_type"],
            "cut_volume_mm3": cut_volume_mm3,
        }, ensure_ascii=False))
    finally:
        if temp_title:
            sw.QuitDoc(temp_title)
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
