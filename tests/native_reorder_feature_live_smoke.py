"""Real SolidWorks regression for independent feature reordering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def top_order(model):
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
    try:
        with sw_part.sketch(model, "Front Plane") as first_sketch:
            sw_part.sketch_rectangle(model, -.020, 0.0, .010, .010)
        first = sw_part.extrude_boss(model, first_sketch, .010, merge=False)
        with sw_part.sketch(model, "Front Plane") as second_sketch:
            sw_part.sketch_rectangle(model, .020, 0.0, .010, .010)
        second = sw_part.extrude_boss(model, second_sketch, .020, merge=False)
        first_name = str(get_com_member(first, "Name")); second_name = str(get_com_member(second, "Name"))
        before = top_order(model)
        volumes_before = sorted(float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9
                                for body in tuple(get_com_member(model, "GetBodies2", 0, False) or ()))
        after = sw_part.reorder_feature_after(model, first_name, second_name)
        get_com_member(model, "ForceRebuild3", False)
        volumes_after = sorted(float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9
                               for body in tuple(get_com_member(model, "GetBodies2", 0, False) or ()))
        if len(volumes_after) != 2 or any(abs(a - b) > 1e-5 for a, b in zip(volumes_before, volumes_after)):
            raise RuntimeError(f"feature reorder changed geometry: {volumes_before} -> {volumes_after}")
        print(json.dumps({"status": "ok", "moved": first_name, "after_target": second_name,
                          "order_before": before, "order_after": list(after),
                          "body_volumes_mm3": volumes_after}, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
