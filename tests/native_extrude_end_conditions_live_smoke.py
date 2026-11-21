"""Direct-library SolidWorks smoke tests for extrusion end conditions."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def feature_definition(feature):
    definition = get_com_member(feature, "GetDefinition")
    if definition is None:
        raise RuntimeError("Feature definition is unavailable")
    return definition


def body_volume_mm3(model) -> float:
    bodies = model.GetBodies2(0, False) or ()
    if len(bodies) != 1:
        raise RuntimeError(f"Expected one solid body, got {len(bodies)}")
    return float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9


def bounds_mm(model):
    values = [float(value) * 1000.0 for value in (model.GetPartBox(True) or ())]
    if len(values) != 6:
        raise RuntimeError(f"Part bounds unavailable: {values}")
    return values


def make_engine():
    return NativeParametric(
        connect=lambda: connect_solidworks(wait_seconds=1),
        part_ops=lambda: sw_part,
    )


def finished_rectangle(engine, title, width, height):
    begun = engine.begin(title, "Front Plane")
    engine.rectangle(begun["session_id"], width, height)
    engine.auto_define(begun["session_id"])
    engine.finish(begun["session_id"])
    return begun


def finished_circle(engine, title, radius):
    begun = engine.begin(title, "Front Plane")
    engine.circle(begun["session_id"], 0, 0, radius)
    engine.auto_define(begun["session_id"])
    engine.finish(begun["session_id"])
    return begun


def assert_feature_ok(model, feature):
    if feature is None:
        raise RuntimeError("SolidWorks feature creation returned None")
    if int(get_com_member(feature, "GetErrorCode")) != 0:
        raise RuntimeError(f"Feature error: {feature.Name}")
    if not bool(model.ForceRebuild3(False)):
        raise RuntimeError(f"Rebuild failed after {feature.Name}")


def main() -> None:
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created_titles = []
    results = {}
    try:
        symmetric = new_document(sw, "part")
        symmetric_title = str(get_com_member(symmetric, "GetTitle"))
        created_titles.append(symmetric_title)
        engine = make_engine()
        base = finished_rectangle(engine, symmetric_title, 30, 20)
        boss = sw_part.extrude_boss_midplane(symmetric, base["sketch"], 0.040)
        assert_feature_ok(symmetric, boss)
        boss_def = feature_definition(boss)
        if int(boss_def.GetEndCondition(True)) != 6:
            raise RuntimeError("Boss did not retain the mid-plane end condition")
        if abs(float(boss_def.GetDepth(True)) * 1000.0 - 40.0) > 1e-5:
            raise RuntimeError("Boss mid-plane total depth readback mismatch")
        box = bounds_mm(symmetric)
        spans = sorted(abs(box[index + 3] - box[index]) for index in range(3))
        if any(abs(actual - expected) > 0.05
               for actual, expected in zip(spans, [20.0, 30.0, 40.0])):
            raise RuntimeError(f"Mid-plane boss bounds mismatch: {box}")
        normal_index = max(range(3), key=lambda index: abs(box[index + 3] - box[index]))
        if abs(box[normal_index] + box[normal_index + 3]) > 0.05:
            raise RuntimeError(f"Mid-plane boss is not symmetric about the sketch plane: {box}")
        boss_volume = body_volume_mm3(symmetric)
        if abs(boss_volume - 30.0 * 20.0 * 40.0) > 0.5:
            raise RuntimeError(f"Mid-plane boss volume mismatch: {boss_volume}")

        hole = finished_circle(engine, symmetric_title, 3)
        mid_cut = sw_part.extrude_cut_midplane(symmetric, hole["sketch"], 0.020)
        assert_feature_ok(symmetric, mid_cut)
        cut_def = feature_definition(mid_cut)
        if int(cut_def.GetEndCondition(True)) != 6:
            raise RuntimeError("Cut did not retain the mid-plane end condition")
        if abs(float(cut_def.GetDepth(True)) * 1000.0 - 20.0) > 1e-5:
            raise RuntimeError("Cut mid-plane total depth readback mismatch")
        cut_volume = body_volume_mm3(symmetric)
        expected_cut_volume = 30.0 * 20.0 * 40.0 - math.pi * 3.0 ** 2 * 20.0
        if abs(cut_volume - expected_cut_volume) > 0.5:
            raise RuntimeError(f"Mid-plane cut volume mismatch: {cut_volume}")
        results["midplane"] = {
            "boss": str(boss.Name), "cut": str(mid_cut.Name),
            "bounds_mm": box, "boss_volume_mm3": boss_volume,
            "cut_volume_mm3": cut_volume,
        }
        sw.QuitDoc(symmetric_title)
        created_titles.remove(symmetric_title)

        through = new_document(sw, "part")
        through_title = str(get_com_member(through, "GetTitle"))
        created_titles.append(through_title)
        engine = make_engine()
        through_base = finished_rectangle(engine, through_title, 30, 20)
        blind_boss = sw_part.extrude_boss(
            through, through_base["sketch"], 0.040, direction=False
        )
        assert_feature_ok(through, blind_boss)
        through_hole = finished_circle(engine, through_title, 4)
        through_cut = sw_part.extrude_cut_through_all(
            through, through_hole["sketch"], reverse_direction=True
        )
        assert_feature_ok(through, through_cut)
        through_def = feature_definition(through_cut)
        if int(through_def.GetEndCondition(True)) != 1:
            raise RuntimeError("Cut did not retain the through-all end condition")
        through_volume = body_volume_mm3(through)
        expected_through_volume = 30.0 * 20.0 * 40.0 - math.pi * 4.0 ** 2 * 40.0
        if abs(through_volume - expected_through_volume) > 0.5:
            raise RuntimeError(f"Through-all cut volume mismatch: {through_volume}")
        results["through_all"] = {
            "boss": str(blind_boss.Name), "cut": str(through_cut.Name),
            "volume_mm3": through_volume,
        }
        print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False))
    finally:
        for title in list(created_titles):
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
