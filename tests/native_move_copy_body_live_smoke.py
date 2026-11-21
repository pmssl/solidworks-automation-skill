"""Real SolidWorks regression for native Move/Copy Body translation and copy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def new_block(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle")); created.append(title)
    with sw_part.sketch(model, "Front Plane") as sketch_name:
        sw_part.sketch_rectangle(model, 0, 0, .040, .030)
    sw_part.extrude_boss_midplane(model, sketch_name, .020)
    body = tuple(get_com_member(model, "GetBodies2", 0, False) or ())[0]
    return model, title, body


def body_box_mm(body):
    return [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]


def move_case(sw, created):
    model, title, body = new_block(sw, created)
    feature = sw_part.move_copy_bodies(model, body, translation=(.007, -.004, .003))
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    box = body_box_mm(bodies[0])
    center = [(box[index] + box[index + 3]) / 2.0 for index in range(3)]
    if any(abs(a - b) > 1e-5 for a, b in zip(center, (7.0, -4.0, 3.0))):
        raise RuntimeError(f"move body center mismatch: {center}")
    result = {"feature": str(get_com_member(feature, "Name")), "center_mm": center,
              "body_count": len(bodies)}
    sw.QuitDoc(title); created.remove(title)
    return result


def copy_case(sw, created):
    model, title, body = new_block(sw, created)
    feature = sw_part.move_copy_bodies(
        model, body, translation=(.050, 0, 0), copy=True, copies=1
    )
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 2:
        raise RuntimeError(f"copy body count mismatch: {len(bodies)}")
    boxes = sorted((body_box_mm(item) for item in bodies), key=lambda box: box[0])
    centers_x = [(box[0] + box[3]) / 2.0 for box in boxes]
    if any(abs(a - b) > 1e-5 for a, b in zip(centers_x, (0.0, 50.0))):
        raise RuntimeError(f"copy body centers mismatch: {centers_x}")
    result = {"feature": str(get_com_member(feature, "Name")),
              "centers_x_mm": centers_x, "body_count": len(bodies)}
    sw.QuitDoc(title); created.remove(title)
    return result


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        results = {"move": move_case(sw, created), "copy": copy_case(sw, created)}
        print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False))
    finally:
        for title in list(created):
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
