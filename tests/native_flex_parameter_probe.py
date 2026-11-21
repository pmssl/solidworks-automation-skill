"""Controlled real-SolidWorks probe for the undocumented Flex axis semantics.

Every case uses a fresh unsaved Part and direct COM only. Failed cases are
discarded with QuitDoc; the first successful case remains open for inspection.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


CASES = (
    {"name": "xyz", "rotation": (1, 0, 0), "tangent": (0, 1, 0),
     "radius": (0, 0, 1), "left": .040, "right": .040, "mark": 1},
    {"name": "xz_minus_y", "rotation": (1, 0, 0), "tangent": (0, 0, 1),
     "radius": (0, -1, 0), "left": .040, "right": .040, "mark": 1},
    {"name": "yx_minus_z", "rotation": (0, 1, 0), "tangent": (1, 0, 0),
     "radius": (0, 0, -1), "left": .040, "right": .040, "mark": 1},
    {"name": "yzx", "rotation": (0, 1, 0), "tangent": (0, 0, 1),
     "radius": (1, 0, 0), "left": .040, "right": .040, "mark": 1},
    {"name": "zxy", "rotation": (0, 0, 1), "tangent": (1, 0, 0),
     "radius": (0, 1, 0), "left": .040, "right": .040, "mark": 1},
    {"name": "zy_minus_x", "rotation": (0, 0, 1), "tangent": (0, 1, 0),
     "radius": (-1, 0, 0), "left": .040, "right": .040, "mark": 1},
)


def _box(body):
    return tuple(float(value) for value in get_com_member(body, "GetBodyBox"))


def _volume(body):
    return float(get_com_member(body, "GetMassProperties", 1.0)[3])


def _dimensions(feature):
    rows = []
    display = get_com_member(feature, "GetFirstDisplayDimension")
    while display:
        dimension = get_com_member(display, "GetDimension2", 0)
        rows.append({
            "name": str(get_com_member(dimension, "Name") or ""),
            "system_value": float(get_com_member(dimension, "SystemValue")),
        })
        display = get_com_member(feature, "GetNextDisplayDimension", display)
    return rows


def _attempt(sw, case):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    keep = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .010, .010)
        sw_part.extrude_boss_midplane(model, sketch_name, .100)
        body = tuple(get_com_member(model, "GetBodies2", 0, False) or ())[0]
        before_box = _box(body)
        before_volume = _volume(body)
        model.ClearSelection2(True)
        data = get_com_member(model.SelectionManager, "CreateSelectData")
        data.Mark = int(case.get("mark", 0))
        selected = bool(body.Select2(False, data))
        manager = sw_part._typed_sldworks_feature_manager(model.FeatureManager)
        feature = manager.InsertFlexFeature(
            *case["rotation"], *case["tangent"], *case["radius"],
            float(case.get("angle", math.radians(30))), 0.0, 0.0, 0.0, 0,
            case["left"], case["right"], bool(case.get("hard_edges", False)),
        )
        after_body = tuple(get_com_member(model, "GetBodies2", 0, False) or ())[0]
        after_box = _box(after_body)
        after_volume = _volume(after_body)
        changed = any(abs(a - b) > 1e-8 for a, b in zip(before_box, after_box))
        volume_ratio = after_volume / before_volume
        keep = feature is not None and changed and 0.99 <= volume_ratio <= 1.01
        return {
            "name": case["name"], "selected": selected,
            "selection_count": int(get_com_member(
                model.SelectionManager, "GetSelectedObjectCount2", -1,
            )),
            "created": keep,
            "feature_type": (
                str(get_com_member(feature, "GetTypeName2")) if feature else None
            ),
            "error_code": (
                int(get_com_member(feature, "GetErrorCode") or 0) if feature else None
            ),
            "dimensions": _dimensions(feature) if feature else [],
            "before_box": before_box, "after_box": after_box,
            "geometry_changed": changed,
            "before_volume": before_volume, "after_volume": after_volume,
            "volume_ratio": volume_ratio,
            "document": title,
        }
    finally:
        model.ClearSelection2(True)
        if not keep:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    results = []
    for case in CASES:
        row = _attempt(sw, case)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if row["created"]:
            if original_title and original_title != row["document"]:
                sw.QuitDoc(original_title)
            sw.ActivateDoc2(row["document"], False, 0)
            break
    if not any(row["created"] for row in results) and original_title:
        sw.ActivateDoc2(original_title, False, 0)
    print(json.dumps({"summary": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
