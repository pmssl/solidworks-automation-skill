"""Real SolidWorks regression for native linear/circular patterns and mirror."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def engine():
    return NativeParametric(connect=lambda: connect_solidworks(wait_seconds=1), part_ops=lambda: sw_part)


def finished_rectangle(native, title, width, height):
    begun = native.begin(title, "Front Plane")
    native.rectangle(begun["session_id"], width, height)
    native.auto_define(begun["session_id"])
    native.finish(begun["session_id"])
    return begun["sketch"]


def finished_circle(native, title, x_mm, y_mm, radius_mm):
    begun = native.begin(title, "Front Plane")
    native.circle(begun["session_id"], x_mm, y_mm, radius_mm)
    native.auto_define(begun["session_id"])
    native.finish(begun["session_id"])
    return begun["sketch"]


def assert_ok(model, feature):
    if feature is None:
        raise RuntimeError("feature creation returned None")
    error = int(get_com_member(feature, "GetErrorCode"))
    if error != 0:
        raise RuntimeError(f"{feature.Name} error code: {error}")
    if not bool(model.ForceRebuild3(False)):
        raise RuntimeError(f"rebuild failed after {feature.Name}")
    if len(model.GetBodies2(0, False) or ()) != 1:
        raise RuntimeError(f"expected one body after {feature.Name}")


def volume_mm3(model):
    body = (model.GetBodies2(0, False) or ())[0]
    return float(list(body.GetMassProperties(1.0))[3]) * 1e9


def plate_with_hole(sw, created, x_mm=0.0, y_mm=0.0):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created.append(title)
    native = engine()
    base = sw_part.extrude_boss_midplane(model, finished_rectangle(native, title, 80, 60), 0.010)
    assert_ok(model, base)
    hole = sw_part.extrude_cut_midplane(model, finished_circle(native, title, x_mm, y_mm, 3), 0.010)
    assert_ok(model, hole)
    return model, title, hole


def linear_case(sw, created):
    model, title, seed = plate_with_hole(sw, created)
    axes = sw_part.find_solid_edges(
        model, length=0.080, direction=(1, 0, 0), midpoint=(0, -0.030, -0.005), tolerance=1e-7
    )
    if len(axes) != 1:
        raise RuntimeError(f"linear direction edge resolution failed: {len(axes)}")
    feature = sw_part.linear_pattern_feature(model, seed, axes[0], 0.015, 3)
    assert_ok(model, feature)
    definition = get_com_member(feature, "GetDefinition")
    spacing_mm = float(get_com_member(definition, "D1Spacing")) * 1000.0
    count = int(get_com_member(definition, "D1TotalInstances"))
    expected = 80 * 60 * 10 - 3 * math.pi * 3 ** 2 * 10
    actual = volume_mm3(model)
    if count != 3 or abs(spacing_mm - 15.0) > 1e-5 or abs(actual - expected) > 0.5:
        raise RuntimeError(f"linear pattern mismatch: count={count}, spacing={spacing_mm}, volume={actual}")
    result = {"feature": str(feature.Name), "count": count, "spacing_mm": spacing_mm, "volume_mm3": actual}
    sw.QuitDoc(title)
    created.remove(title)
    return result


def circular_axis_edge(model):
    candidates = []
    for edge in sw_part.solid_edges(model):
        curve = get_com_member(edge, "GetCurve")
        if curve is None or not bool(get_com_member(curve, "IsCircle")):
            continue
        params = list(get_com_member(curve, "CircleParams") or ())
        if len(params) >= 7 and abs(float(params[6]) - 0.040) < 1e-7:
            candidates.append(edge)
    if not candidates:
        raise RuntimeError("circular pattern axis edge not found")
    return candidates[0]


def circular_case(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created.append(title)
    native = engine()
    base = sw_part.extrude_boss_midplane(model, finished_circle(native, title, 0, 0, 40), 0.010)
    assert_ok(model, base)
    seed = sw_part.extrude_cut_midplane(model, finished_circle(native, title, 25, 0, 3), 0.010)
    assert_ok(model, seed)
    feature = sw_part.circular_pattern_feature(model, seed, circular_axis_edge(model), math.tau, 5)
    assert_ok(model, feature)
    definition = get_com_member(feature, "GetDefinition")
    count = int(get_com_member(definition, "TotalInstances"))
    spacing_deg = math.degrees(float(get_com_member(definition, "Spacing")))
    expected = math.pi * 40 ** 2 * 10 - 5 * math.pi * 3 ** 2 * 10
    actual = volume_mm3(model)
    if count != 5 or abs(spacing_deg - 360.0) > 1e-5 or abs(actual - expected) > 0.5:
        raise RuntimeError(f"circular pattern mismatch: count={count}, angle={spacing_deg}, volume={actual}")
    result = {"feature": str(feature.Name), "count": count, "angle_deg": spacing_deg, "volume_mm3": actual}
    sw.QuitDoc(title)
    created.remove(title)
    return result


def mirror_case(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created.append(title)
    native = engine()
    base = sw_part.extrude_boss(
        model, finished_rectangle(native, title, 80, 60), 0.010, direction=False
    )
    assert_ok(model, base)
    seed = sw_part.extrude_cut_through_all(
        model, finished_circle(native, title, -20, 0, 3), reverse_direction=True
    )
    assert_ok(model, seed)
    feature = sw_part.mirror_feature_objects(model, seed, "Right Plane")
    assert_ok(model, feature)
    definition = get_com_member(feature, "GetDefinition")
    seed_count = int(get_com_member(definition, "GetPatternFeatureCount"))
    expected = 80 * 60 * 10 - 2 * math.pi * 3 ** 2 * 10
    actual = volume_mm3(model)
    if seed_count != 1 or abs(actual - expected) > 0.5:
        raise RuntimeError(f"mirror mismatch: seed_count={seed_count}, volume={actual}")
    result = {"feature": str(feature.Name), "seed_count": seed_count, "volume_mm3": actual}
    sw.QuitDoc(title)
    created.remove(title)
    return result


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        requested = sys.argv[1:] or ["linear", "circular", "mirror"]
        cases = {"linear": linear_case, "circular": circular_case, "mirror": mirror_case}
        unknown = [name for name in requested if name not in cases]
        if unknown:
            raise ValueError(f"unknown cases: {unknown}")
        results = {name: cases[name](sw, created) for name in requested}
        print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False))
    finally:
        for title in list(created):
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
