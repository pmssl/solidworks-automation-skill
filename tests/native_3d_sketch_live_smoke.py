"""Real SolidWorks regression for native 3D sketch line and spline primitives."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def point_xyz(point):
    return tuple(float(get_com_member(point, axis)) for axis in ("X", "Y", "Z"))


def assert_point(point, expected, label):
    actual = point_xyz(point)
    if math.dist(actual, expected) > 1e-9:
        raise RuntimeError(f"{label} mismatch: {actual} != {expected}")
    return [value * 1000.0 for value in actual]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        sw_part.start_3d_sketch(model)
        line_start = (0.001, -0.002, 0.003)
        line_end = (0.011, 0.012, 0.023)
        line = sw_part.sketch_line_3d(model, line_start, line_end)
        spline_points = (
            (0.030, 0.000, 0.000),
            (0.035, -0.004, 0.010),
            (0.042, 0.003, 0.025),
        )
        spline = sw_part.sketch_spline_3d(model, spline_points)
        active = get_com_member(model.SketchManager, "ActiveSketch")
        if not bool(get_com_member(active, "Is3D")):
            raise RuntimeError("active sketch is not 3D")
        segments = sw_part._as_tuple(get_com_member(active, "GetSketchSegments"))
        segment_types = [int(get_com_member(item, "GetType")) for item in segments]
        if segment_types != [0, 3]:
            raise RuntimeError(f"unexpected 3D sketch segment types: {segment_types}")
        line_start_mm = assert_point(get_com_member(line, "GetStartPoint2"), line_start, "line start")
        line_end_mm = assert_point(get_com_member(line, "GetEndPoint2"), line_end, "line end")
        spline_control_points = sw_part._as_tuple(get_com_member(spline, "GetPoints2"))
        if len(spline_control_points) != len(spline_points):
            raise RuntimeError(
                f"unexpected spline control-point count: {len(spline_control_points)}"
            )
        spline_start_mm = assert_point(
            spline_control_points[0], spline_points[0], "spline start"
        )
        spline_end_mm = assert_point(
            spline_control_points[-1], spline_points[-1], "spline end"
        )
        sketch_ref = sw_part.end_3d_sketch(model)
        specific = get_com_member(sketch_ref.feature, "GetSpecificFeature2")
        if not bool(get_com_member(specific, "Is3D")):
            raise RuntimeError("finished sketch feature is not 3D")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("rebuild failed after 3D sketch")
        print(json.dumps({
            "status": "ok",
            "sketch": sketch_ref.name,
            "segment_types": segment_types,
            "line_mm": [line_start_mm, line_end_mm],
            "spline_endpoints_mm": [spline_start_mm, spline_end_mm],
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
