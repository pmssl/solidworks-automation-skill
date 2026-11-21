"""Live SolidWorks smoke test for native sketch primitives."""

from __future__ import annotations

import json

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def assert_close(actual, expected, tolerance=1e-6):
    if len(actual) != len(expected) or any(abs(a - b) > tolerance for a, b in zip(actual, expected)):
        raise RuntimeError(f"Coordinate mismatch: {actual} != {expected}")


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    temp_title = None
    results = {}
    try:
        model = new_document(sw, "part")
        temp_title = str(get_com_member(model, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )

        def run_case(name, create, verify):
            begun = engine.begin(temp_title, "Top Plane")
            token = begun["session_id"]
            created = create(token)
            geometry = engine.geometry(token)
            verify(geometry)
            engine.finish(token, require_fully_defined=False)
            results[name] = {
                "sketch": begun["sketch"],
                "created_entity": created["entity"],
                "segment_count": geometry["segment_count"],
            }

        run_case(
            "line",
            lambda token: engine.line(token, -10, 0, 10, 0),
            lambda geometry: (
                (_ for _ in ()).throw(RuntimeError("Line segment count mismatch"))
                if geometry["segment_count"] != 1 else
                (assert_close(geometry["segments"][0]["start_mm"], [-10, 0]),
                 assert_close(geometry["segments"][0]["end_mm"], [10, 0]))
            ),
        )

        def verify_rectangle(geometry):
            if geometry["segment_count"] != 4:
                raise RuntimeError(f"Rectangle segment count mismatch: {geometry}")
            points = [point for segment in geometry["segments"]
                      for point in (segment.get("start_mm"), segment.get("end_mm")) if point]
            xs = sorted({point[0] for point in points})
            ys = sorted({point[1] for point in points})
            if xs != [-20.0, 20.0] or ys != [-10.0, 10.0]:
                raise RuntimeError(f"Rectangle coordinates changed: {xs}, {ys}")

        run_case(
            "corner_rectangle",
            lambda token: engine.corner_rectangle(token, -20, -10, 20, 10),
            verify_rectangle,
        )

        def verify_circle(geometry):
            if geometry["segment_count"] != 1:
                raise RuntimeError(f"Circle segment count mismatch: {geometry}")
            segment = geometry["segments"][0]
            assert_close(segment["center_mm"], [5, -5])
            if abs(segment["radius_mm"] - 10.0) > 1e-6:
                raise RuntimeError(f"Circle radius mismatch: {segment}")

        run_case("circle", lambda token: engine.circle(token, 5, -5, 10), verify_circle)

        def verify_arc(geometry):
            if geometry["segment_count"] != 1:
                raise RuntimeError(f"Arc segment count mismatch: {geometry}")
            segment = geometry["segments"][0]
            assert_close(segment["center_mm"], [0, 0])
            assert_close(segment["start_mm"], [10, 0])
            assert_close(segment["end_mm"], [0, 10])
            if abs(segment["radius_mm"] - 10.0) > 1e-6:
                raise RuntimeError(f"Arc radius mismatch: {segment}")

        run_case("arc", lambda token: engine.arc(token, 0, 0, 10, 0, 0, 10), verify_arc)

        def verify_polygon(geometry):
            line_count = sum(segment["type"] == "line" for segment in geometry["segments"])
            if line_count != 6:
                raise RuntimeError(f"Polygon line count mismatch: {geometry}")

        run_case("polygon", lambda token: engine.polygon(token, 0, 0, 12, 6), verify_polygon)

        def verify_slot(geometry):
            if geometry["segment_count"] < 4:
                raise RuntimeError(f"Slot segment count mismatch: {geometry}")
            radii = [segment.get("radius_mm") for segment in geometry["segments"]
                     if segment.get("radius_mm") is not None]
            if len(radii) < 2 or any(abs(radius - 3.0) > 1e-6 for radius in radii):
                raise RuntimeError(f"Slot arc radius mismatch: {geometry}")

        run_case(
            "straight_slot",
            lambda token: engine.straight_slot(token, -15, 0, 15, 0, 6),
            verify_slot,
        )

        def verify_spline(geometry):
            if geometry["segment_count"] != 1 or geometry["segments"][0]["type"] != "spline":
                raise RuntimeError(f"Spline geometry mismatch: {geometry}")

        run_case(
            "spline",
            lambda token: engine.spline(token, [(-10, 0), (0, 8), (10, 0)]),
            verify_spline,
        )

        print(json.dumps({"status": "ok", "document": temp_title, "cases": results}, ensure_ascii=False))
    finally:
        if temp_title:
            sw.QuitDoc(temp_title)
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
