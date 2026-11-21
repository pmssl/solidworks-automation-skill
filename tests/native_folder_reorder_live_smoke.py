"""Real SolidWorks regression for reordering independent FeatureManager folders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _volumes_mm3(model):
    return sorted(
        float(get_com_member(body, "GetMassProperties", 1.0)[3]) * 1e9
        for body in tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    )


def _top_order(model):
    names = []
    feature = get_com_member(model, "FirstFeature")
    while feature is not None:
        names.append(str(get_com_member(feature, "Name")))
        feature = get_com_member(feature, "GetNextFeature")
    return names


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as first_sketch:
            sw_part.sketch_rectangle(model, -.020, 0.0, .010, .010)
        first = sw_part.extrude_boss(model, first_sketch, .010, merge=False)
        with sw_part.sketch(model, "Front Plane") as second_sketch:
            sw_part.sketch_rectangle(model, .020, 0.0, .010, .010)
        second = sw_part.extrude_boss(model, second_sketch, .020, merge=False)

        first_folder = sw_part.create_feature_folder(model, first, name="First Body")
        second_folder = sw_part.create_feature_folder(model, second, name="Second Body")
        before = _top_order(model)
        volumes_before = _volumes_mm3(model)
        after = sw_part.reorder_feature_after(model, first_folder, second_folder)
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        volumes_after = _volumes_mm3(model)
        first_name = str(get_com_member(first_folder, "Name"))
        second_name = str(get_com_member(second_folder, "Name"))
        if (
            len(volumes_after) != 2
            or any(abs(a - b) > 1e-5 for a, b in zip(volumes_before, volumes_after))
            or list(after).index(first_name) <= list(after).index(second_name)
            or not rebuilt
        ):
            raise RuntimeError(
                f"folder reorder verification failed: before={before}, after={after}, "
                f"volumes={volumes_before}->{volumes_after}, rebuild={rebuilt}"
            )

        print(json.dumps({
            "status": "ok",
            "moved_folder": first_name,
            "after_folder": second_name,
            "order_before": before,
            "order_after": list(after),
            "body_volumes_mm3": volumes_after,
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
