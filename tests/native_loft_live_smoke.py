"""Live SolidWorks smoke test for offset plane and native boss/cut lofts."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def frustum_volume(height_mm: float, radius1_mm: float, radius2_mm: float) -> float:
    return math.pi * height_mm / 3.0 * (
        radius1_mm ** 2 + radius1_mm * radius2_mm + radius2_mm ** 2
    )


def make_circle_section(engine, title, plane_name, radius_mm):
    begun = engine.begin(title, plane_name)
    token = begun["session_id"]
    engine.circle(token, 0, 0, radius_mm)
    engine.auto_define(token)
    engine.finish(token)
    return begun


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

        reverse_plane = engine.offset_plane(temp_title, "Front Plane", 11.0, True)
        if (abs(reverse_plane["offset_mm"] - 11.0) > 1e-6
                or not reverse_plane["reverse_direction"]):
            raise RuntimeError(f"Reverse offset plane readback mismatch: {reverse_plane}")
        plane = engine.offset_plane(temp_title, "Front Plane", 37.0)
        if plane["feature_type"] != "RefPlane" or abs(plane["offset_mm"] - 37.0) > 1e-6:
            raise RuntimeError(f"Offset plane readback mismatch: {plane}")

        base = make_circle_section(engine, temp_title, "Front Plane", 6.0)
        top = make_circle_section(engine, temp_title, plane["feature"], 3.5)
        loft = engine.loft(top["session_id"], [base["sketch"], top["sketch"]])
        if loft["profile_count"] != 2 or loft["cut"] or loft["solid_body_count"] != 1:
            raise RuntimeError(f"Boss loft readback mismatch: {loft}")

        bounds = [float(value) * 1000.0 for value in (model.GetPartBox(True) or ())]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        if len(spans) != 3 or any(abs(actual - expected) > 0.05
                                  for actual, expected in zip(spans, [12.0, 12.0, 37.0])):
            raise RuntimeError(f"Unexpected loft bounds: spans={spans}, bounds={bounds}")
        bodies = model.GetBodies2(0, False) or ()
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        expected_volume = frustum_volume(37.0, 6.0, 3.5)
        if abs(volume_mm3 - expected_volume) > 0.5:
            raise RuntimeError(f"Boss loft volume mismatch: {volume_mm3} != {expected_volume}")

        cut_base = make_circle_section(engine, temp_title, "Front Plane", 2.0)
        cut_top = make_circle_section(engine, temp_title, plane["feature"], 1.0)
        cut = engine.loft(
            cut_top["session_id"], [cut_base["sketch"], cut_top["sketch"]], cut=True
        )
        if not cut["cut"] or cut["profile_count"] != 2 or cut["solid_body_count"] != 1:
            raise RuntimeError(f"Cut loft readback mismatch: {cut}")
        cut_bodies = model.GetBodies2(0, False) or ()
        cut_volume_mm3 = float(list(cut_bodies[0].GetMassProperties(1.0))[3]) * 1e9
        expected_cut_volume = expected_volume - frustum_volume(37.0, 2.0, 1.0)
        if abs(cut_volume_mm3 - expected_cut_volume) > 0.5:
            raise RuntimeError(
                f"Cut loft volume mismatch: {cut_volume_mm3} != {expected_cut_volume}"
            )
        state = engine.model_state(cut_top["session_id"])
        names = [row["name"] for row in state["features"]]
        for required in (
            plane["feature"], base["sketch"], top["sketch"], loft["feature"],
            cut_base["sketch"], cut_top["sketch"], cut["feature"],
        ):
            if required not in names:
                raise RuntimeError(f"Missing feature-tree item {required!r}: {names}")
        print(json.dumps({
            "status": "ok", "document": temp_title,
            "reverse_offset_plane": reverse_plane, "offset_plane": plane,
            "boss_feature": loft["feature"],
            "boss_feature_type": loft["feature_type"], "profile_count": loft["profile_count"],
            "spans_mm": spans, "boss_volume_mm3": volume_mm3,
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
