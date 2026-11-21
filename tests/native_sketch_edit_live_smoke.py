"""Real SolidWorks regression for editing and deleting existing sketch entities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def point_mm(point):
    return [float(get_com_member(point, axis)) * 1000.0 for axis in ("X", "Y", "Z")]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        sw_part.start_sketch(model, "Front Plane")
        line = sw_part.sketch_line(model, 0, 0, .010, .002)
        circle = sw_part.sketch_circle(model, .020, .010, .003)
        end_point = get_com_member(line, "GetEndPoint2")
        moved = sw_part.move_sketch_point(end_point, .012, .005)
        if [round(value, 9) for value in moved] != [.012, .005, 0.0]:
            raise RuntimeError(f"sketch point move mismatch: {moved}")
        sw_part.set_sketch_construction(line, True)
        if not bool(get_com_member(line, "ConstructionGeometry")):
            raise RuntimeError("construction state did not persist")
        deletion = sw_part.delete_sketch_entities(model, circle)
        if deletion != {"deleted": 1, "remaining": 1}:
            raise RuntimeError(f"sketch deletion mismatch: {deletion}")
        remaining = sw_part._active_sketch_segments(model)
        if len(remaining) != 1 or int(get_com_member(remaining[0], "GetType")) != 0:
            raise RuntimeError("unexpected entity remained after deletion")
        sw_part.end_sketch(model)
        model.ForceRebuild3(False)
        print(json.dumps({
            "status": "ok",
            "moved_endpoint_mm": point_mm(end_point),
            "construction": bool(get_com_member(line, "ConstructionGeometry")),
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
