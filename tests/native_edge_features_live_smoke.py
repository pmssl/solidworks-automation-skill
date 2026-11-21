"""Real SolidWorks regression for semantic edge fillet and chamfer features."""

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
    return NativeParametric(
        connect=lambda: connect_solidworks(wait_seconds=1),
        part_ops=lambda: sw_part,
    )


def create_block(model, title):
    native = engine()
    begun = native.begin(title, "Front Plane")
    native.rectangle(begun["session_id"], 40, 30)
    native.auto_define(begun["session_id"])
    native.finish(begun["session_id"])
    feature = sw_part.extrude_boss_midplane(model, begun["sketch"], 0.020)
    assert_feature_ok(model, feature)
    return feature


def assert_feature_ok(model, feature):
    if feature is None:
        raise RuntimeError("SolidWorks feature creation returned None")
    error = int(get_com_member(feature, "GetErrorCode"))
    if error != 0:
        raise RuntimeError(f"Feature {feature.Name} has error code {error}")
    if not bool(model.ForceRebuild3(False)):
        raise RuntimeError(f"Rebuild failed after {feature.Name}")
    bodies = model.GetBodies2(0, False) or ()
    if len(bodies) != 1:
        raise RuntimeError(f"Expected one solid body after {feature.Name}, got {len(bodies)}")


def volume_mm3(model):
    body = (model.GetBodies2(0, False) or ())[0]
    return float(list(body.GetMassProperties(1.0))[3]) * 1e9


def edge_count(model):
    return len(sw_part.solid_edges(model))


def target_edge(model):
    matches = sw_part.find_solid_edges(
        model,
        length=0.020,
        direction=(0, 0, 1),
        midpoint=(-0.020, -0.015, 0.0),
        tolerance=1e-7,
    )
    if len(matches) != 1:
        summaries = [sw_part.edge_geometry(edge) for edge in sw_part.find_solid_edges(
            model, length=0.020, direction=(0, 0, 1), tolerance=1e-7
        )]
        raise RuntimeError(f"Semantic edge did not resolve uniquely: {summaries}")
    return matches[0]


def fillet_case(sw, created_titles):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created_titles.append(title)
    create_block(model, title)
    before_volume = volume_mm3(model)
    before_edges = edge_count(model)
    feature = sw_part.fillet(model, 0.003, edges=[target_edge(model)])
    assert_feature_ok(model, feature)
    definition = get_com_member(feature, "GetDefinition")
    radius_mm = float(get_com_member(definition, "DefaultRadius")) * 1000.0
    if abs(radius_mm - 3.0) > 1e-5:
        raise RuntimeError(f"Fillet radius readback mismatch: {radius_mm} mm")
    after_volume = volume_mm3(model)
    expected = before_volume - (3.0 ** 2 - math.pi * 3.0 ** 2 / 4.0) * 20.0
    if abs(after_volume - expected) > 0.1:
        raise RuntimeError(f"Fillet volume mismatch: expected {expected}, got {after_volume}")
    result = {
        "feature": str(feature.Name),
        "radius_mm": radius_mm,
        "volume_before_mm3": before_volume,
        "volume_after_mm3": after_volume,
        "edges_before": before_edges,
        "edges_after": edge_count(model),
    }
    sw.QuitDoc(title)
    created_titles.remove(title)
    return result


def chamfer_case(sw, created_titles):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created_titles.append(title)
    create_block(model, title)
    before_volume = volume_mm3(model)
    before_edges = edge_count(model)
    feature = sw_part.chamfer(model, 0.002, 37.0, edges=[target_edge(model)])
    assert_feature_ok(model, feature)
    definition = get_com_member(feature, "GetDefinition")
    chamfer_type = int(get_com_member(definition, "Type"))
    angle_deg = math.degrees(float(get_com_member(definition, "EdgeChamferAngle")))
    distances_mm = [
        float(get_com_member(definition, "GetEdgeChamferDistance", side)) * 1000.0
        for side in (0, 1)
    ]
    if min(abs(value - 2.0) for value in distances_mm) > 1e-5:
        raise RuntimeError(f"Chamfer distance readback mismatch: {distances_mm}")
    if min(abs(angle_deg - 37.0), abs(angle_deg - 53.0)) > 1e-5:
        raise RuntimeError(f"Chamfer angle readback mismatch: {angle_deg}")
    after_volume = volume_mm3(model)
    if not 0.0 < after_volume < before_volume:
        raise RuntimeError(f"Chamfer did not remove material: {before_volume} -> {after_volume}")
    result = {
        "feature": str(feature.Name),
        "type": chamfer_type,
        "angle_deg": angle_deg,
        "distances_mm": distances_mm,
        "volume_before_mm3": before_volume,
        "volume_after_mm3": after_volume,
        "edges_before": before_edges,
        "edges_after": edge_count(model),
    }
    sw.QuitDoc(title)
    created_titles.remove(title)
    return result


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created_titles = []
    try:
        results = {
            "fillet": fillet_case(sw, created_titles),
            "chamfer": chamfer_case(sw, created_titles),
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
