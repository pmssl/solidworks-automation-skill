"""Real SolidWorks regression for nested FeatureManager folders."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _folder_children(folder_feature):
    specific = get_com_member(folder_feature, "GetSpecificFeature2")
    return tuple(get_com_member(specific, "GetFeatures") or ())


def _volume_mm3(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    return float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .080, .060)
        base = sw_part.extrude_boss_midplane(model, base_sketch, .010)
        with sw_part.sketch(model, "Front Plane") as first_cut_sketch:
            sw_part.sketch_circle(model, -.010, 0.0, .003)
        first_cut = sw_part.extrude_cut_midplane(model, first_cut_sketch, .010)
        inner = sw_part.create_feature_folder(
            model, (base, first_cut), name="Machining Inner",
        )

        with sw_part.sketch(model, "Front Plane") as second_cut_sketch:
            sw_part.sketch_circle(model, .010, 0.0, .004)
        second_cut = sw_part.extrude_cut_midplane(model, second_cut_sketch, .010)
        outer = sw_part.create_feature_folder(
            model, (inner, second_cut), name="Machining Outer",
        )

        inner_names = [str(get_com_member(item, "Name")) for item in _folder_children(inner)]
        outer_names = [str(get_com_member(item, "Name")) for item in _folder_children(outer)]
        volume = _volume_mm3(model)
        expected = 80.0 * 60.0 * 10.0 - math.pi * (3.0 ** 2 + 4.0 ** 2) * 10.0
        errors = {
            str(get_com_member(feature, "Name")): int(get_com_member(feature, "GetErrorCode"))
            for feature in (inner, outer)
        }
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        if not {str(get_com_member(base, "Name")), str(get_com_member(first_cut, "Name"))}.issubset(inner_names):
            raise RuntimeError(f"inner folder contents mismatch: {inner_names}")
        if str(get_com_member(inner, "Name")) not in outer_names or str(get_com_member(second_cut, "Name")) not in outer_names:
            raise RuntimeError(f"outer folder contents mismatch: {outer_names}")
        if abs(volume - expected) > 1e-4 or any(errors.values()) or not rebuilt:
            raise RuntimeError(
                f"nested folder verification failed: volume={volume}, expected={expected}, "
                f"errors={errors}, rebuild={rebuilt}"
            )

        print(json.dumps({
            "status": "ok",
            "inner_folder": str(get_com_member(inner, "Name")),
            "inner_children": inner_names,
            "outer_folder": str(get_com_member(outer, "Name")),
            "outer_children": outer_names,
            "volume_mm3": volume,
            "expected_volume_mm3": expected,
            "folder_error_codes": errors,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        if not completed and original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
