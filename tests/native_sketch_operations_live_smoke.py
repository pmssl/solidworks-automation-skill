"""Real SolidWorks regression for Convert/Offset and sketch patterns."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def point_xy(point):
    return [float(get_com_member(point, "X")) * 1000.0,
            float(get_com_member(point, "Y")) * 1000.0]


def circle_evidence(segment):
    curve = get_com_member(segment, "GetCurve")
    params = list(get_com_member(curve, "CircleParams") or ())
    return [float(value) * 1000.0 for value in params[:7]]


def new_case(sw, created):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    created.append(title)
    return model, title


def offset_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    line = sw_part.sketch_line(model, -.010, 0, .010, 0)
    added = sw_part.sketch_offset_entities(model, line, .005, add_dimensions=False)
    if len(added) != 1 or int(get_com_member(added[0], "GetType")) != 0:
        raise RuntimeError(f"offset result mismatch: {len(added)}")
    start = point_xy(get_com_member(added[0], "GetStartPoint2"))
    end = point_xy(get_com_member(added[0], "GetEndPoint2"))
    if abs(abs(start[1]) - 5.0) > 1e-5 or abs(abs(end[1]) - 5.0) > 1e-5:
        raise RuntimeError(f"offset distance mismatch: {start}, {end}")
    sw_part.end_sketch(model)
    model.ForceRebuild3(False)
    result = {"added": len(added), "start_mm": start, "end_mm": end}
    sw.QuitDoc(title); created.remove(title)
    return result


def linear_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    circle = sw_part.sketch_circle(model, 0, 0, .002)
    added = sw_part.linear_sketch_pattern(
        model, circle, 3, .010, add_dimensions=False
    )
    segments = sw_part._active_sketch_segments(model)
    circles = [circle_evidence(item) for item in segments if int(get_com_member(item, "GetType")) == 1]
    if len(circles) != 3:
        raise RuntimeError(f"linear sketch pattern circle count mismatch: {circles}")
    sw_part.end_sketch(model)
    result = {"added": len(added), "circles_mm": circles}
    sw.QuitDoc(title); created.remove(title)
    return result


def circular_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    circle = sw_part.sketch_circle(model, -.020, 0, .002)
    added = sw_part.circular_sketch_pattern(
        model, circle, .020, math.tau, 4,
        rotate_instances=False, add_dimensions=False,
    )
    segments = sw_part._active_sketch_segments(model)
    circles = [circle_evidence(item) for item in segments if int(get_com_member(item, "GetType")) == 1]
    if len(circles) != 4:
        raise RuntimeError(f"circular sketch pattern count mismatch: {circles}")
    centers = [(item[0], item[1]) for item in circles]
    expected = {(-20.0, 0.0), (0.0, 20.0), (20.0, 0.0), (0.0, -20.0)}
    rounded = {(round(x, 6), round(y, 6)) for x, y in centers}
    if rounded != expected:
        raise RuntimeError(f"circular sketch pattern geometry mismatch: {centers}")
    sw_part.end_sketch(model)
    result = {"added": len(added), "circles_mm": circles}
    sw.QuitDoc(title); created.remove(title)
    return result


def convert_case(sw, created):
    model, title = new_case(sw, created)
    with sw_part.sketch(model, "Front Plane") as base_sketch:
        sw_part.sketch_rectangle(model, 0, 0, .040, .030)
    feature = sw_part.extrude_boss_midplane(model, base_sketch, .020)
    if feature is None: raise RuntimeError("convert base failed")
    face = sw_part.find_largest_outer_planar_face(model)
    edges = tuple(get_com_member(face, "GetEdges") or ())
    model.ClearSelection2(True)
    if not sw_part._select_com_object(face): raise RuntimeError("convert face selection failed")
    model.SketchManager.InsertSketch(True)
    converted = sw_part.sketch_convert_entities(model, edges[0], chain=False)
    if len(converted) != 1:
        raise RuntimeError(f"convert entities count mismatch: {len(converted)}")
    evidence = int(get_com_member(converted[0], "GetType"))
    sw_part.end_sketch(model)
    result = {"converted": len(converted), "type": evidence}
    sw.QuitDoc(title); created.remove(title)
    return result


def trim_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    horizontal = sw_part.sketch_line(model, -.020, 0, .020, 0)
    vertical = sw_part.sketch_line(model, 0, -.010, 0, .010)
    sw_part.sketch_trim(
        model, 2,
        ((horizontal, (.010, 0, 0)), (vertical, (0, .005, 0))),
    )
    start = point_xy(get_com_member(horizontal, "GetStartPoint2"))
    end = point_xy(get_com_member(horizontal, "GetEndPoint2"))
    xs = sorted((round(start[0], 6), round(end[0], 6)))
    if xs != [-20.0, 0.0]:
        raise RuntimeError(f"trim endpoint mismatch: {start}, {end}")
    sw_part.end_sketch(model)
    result = {"start_mm": start, "end_mm": end}
    sw.QuitDoc(title); created.remove(title)
    return result


def extend_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    horizontal = sw_part.sketch_line(model, -.020, 0, -.005, 0)
    sw_part.sketch_line(model, 0, -.010, 0, .010)
    sw_part.sketch_extend(model, horizontal, pick_point=(-.005, 0, 0))
    start = point_xy(get_com_member(horizontal, "GetStartPoint2"))
    end = point_xy(get_com_member(horizontal, "GetEndPoint2"))
    xs = sorted((round(start[0], 6), round(end[0], 6)))
    if xs != [-20.0, 0.0]:
        raise RuntimeError(f"extend endpoint mismatch: {start}, {end}")
    sw_part.end_sketch(model)
    result = {"start_mm": start, "end_mm": end}
    sw.QuitDoc(title); created.remove(title)
    return result


def mirror_case(sw, created):
    model, title = new_case(sw, created)
    sw_part.start_sketch(model, "Front Plane")
    axis = sw_part.sketch_line(model, 0, -.020, 0, .020)
    axis.ConstructionGeometry = True
    seed = sw_part.sketch_line(model, .005, .005, .015, .010)
    added = sw_part.sketch_mirror_entities(model, seed, axis)
    if len(added) != 1:
        raise RuntimeError(f"sketch mirror count mismatch: {len(added)}")
    start = point_xy(get_com_member(added[0], "GetStartPoint2"))
    end = point_xy(get_com_member(added[0], "GetEndPoint2"))
    points = {(round(x, 6), round(y, 6)) for x, y in (start, end)}
    if points != {(-5.0, 5.0), (-15.0, 10.0)}:
        raise RuntimeError(f"sketch mirror geometry mismatch: {start}, {end}")
    sw_part.end_sketch(model)
    result = {"added": len(added), "start_mm": start, "end_mm": end}
    sw.QuitDoc(title); created.remove(title)
    return result


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    created = []
    try:
        results = {
            "offset": offset_case(sw, created),
            "linear": linear_case(sw, created),
            "circular": circular_case(sw, created),
            "convert": convert_case(sw, created),
            "trim": trim_case(sw, created),
            "extend": extend_case(sw, created),
            "mirror": mirror_case(sw, created),
        }
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
