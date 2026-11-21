"""Real SolidWorks regression for native Untrim Surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def surface_area(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
    area = sum(
        float(get_com_member(face, "GetArea"))
        for body in bodies
        for face in tuple(get_com_member(body, "GetFaces") or ())
    )
    return bodies, area


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        points = (
            (-.035002, .035119), (.025668, .036519),
            (.025201, -.016451), (-.068137, -.018551),
            (-.067204, .026718), (-.036169, .026251),
        )
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            for index, start in enumerate(points):
                end = points[(index + 1) % len(points)]
                sw_part.sketch_line(model, start[0], start[1], end[0], end[1])
        sw_part.planar_surface_from_sketch(model, sketch_name)
        before_bodies, before_area = surface_area(model)
        faces = tuple(get_com_member(before_bodies[0], "GetFaces") or ())
        feature = sw_part.untrim_surface(
            model, faces[0], face_untrim_type=0, edge_untrim_type=2,
            distance=0.0, merge=False, trim_opposite_side=True,
        )
        after_bodies, after_area = surface_area(model)
        if len(after_bodies) < 1 or abs(after_area - before_area) < 1e-10:
            raise RuntimeError(
                f"untrim geometry did not change: bodies={len(after_bodies)}, "
                f"before={before_area}, after={after_area}"
            )
        data = get_com_member(feature, "GetDefinition")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "body_count": len(after_bodies),
            "area_before_mm2": before_area * 1e6,
            "area_after_mm2": after_area * 1e6,
            "feature_data_type": str(type(data)),
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
