"""Real SolidWorks regression for native sketch-relation lifecycle operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def endpoint_xy_mm(segment):
    start = get_com_member(segment, "GetStartPoint2")
    end = get_com_member(segment, "GetEndPoint2")
    return [
        [float(get_com_member(point, axis)) * 1000.0 for axis in ("X", "Y")]
        for point in (start, end)
    ]


def require_horizontal(segment, label):
    points = endpoint_xy_mm(segment)
    if abs(points[0][1] - points[1][1]) > 1e-6:
        raise RuntimeError(f"{label} is not horizontal: {points}")
    return points


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        sw_part.start_sketch(model, "Front Plane")
        first = sw_part.sketch_line(model, 0.0, 0.0, 0.020, 0.005)
        second = sw_part.sketch_line(model, 0.0, 0.015, 0.020, 0.022)

        added = sw_part.add_sketch_relation_to_entities(
            model, (first,), "sgHORIZONTAL2D"
        )
        if len(added) != 1:
            raise RuntimeError(f"unexpected relation count: {len(added)}")
        relation = added[0]
        summary = sw_part.sketch_relation_summary(relation)
        if summary != {"type": 4, "entity_count": 1, "suppressed": False}:
            raise RuntimeError(f"unexpected relation summary: {summary}")
        first_horizontal = require_horizontal(first, "first line after add")

        sw_part.set_sketch_relation_suppressed(relation, True)
        end = get_com_member(first, "GetEndPoint2")
        moved = sw_part.move_sketch_point(end, 0.020, 0.008)
        if abs(moved[1] - 0.008) > 1e-9:
            raise RuntimeError(f"suppressed relation still constrained endpoint: {moved}")
        sw_part.set_sketch_relation_suppressed(relation, False)
        first_restored = require_horizontal(first, "first line after restore")

        sw_part.replace_sketch_relation_entity(relation, first, second)
        second_rebound = require_horizontal(second, "second line after rebind")
        deletion = sw_part.delete_sketch_relation(
            model, second, 0, "sgHORIZONTAL2D"
        )
        if deletion != {"deleted": 1, "remaining": 0}:
            raise RuntimeError(f"relation deletion mismatch: {deletion}")

        sw_part.end_sketch(model)
        model.ForceRebuild3(False)
        print(json.dumps({
            "status": "ok",
            "relation": summary,
            "first_after_add_mm": first_horizontal,
            "first_after_restore_mm": first_restored,
            "second_after_rebind_mm": second_rebound,
            "deletion": deletion,
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
