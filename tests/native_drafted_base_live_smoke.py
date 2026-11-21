"""Live SolidWorks smoke test for the drafted geomagnetic-box base workflow."""

from __future__ import annotations

import json

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def fully_define(engine, token):
    status = engine.status(token)
    if not status["fully_defined"]:
        engine.auto_define(token)
        status = engine.status(token)
    if not status["fully_defined"]:
        raise RuntimeError(f"Sketch remains under-defined: {status}")
    return status


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    temp_title = None
    try:
        model = new_document(sw, "part")
        temp_title = str(get_com_member(model, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )

        base = engine.begin(temp_title, "Top Plane")
        base_token = base["session_id"]
        engine.rectangle(base_token, 45, 45)
        engine.dimension(base_token, "horizontal", 45)
        fully_define(engine, base_token)
        engine.finish(base_token)
        base_feature = engine.extrude(
            base_token, 70, cut=False, draft_angle_deg=45, draft_outward=True
        )

        pocket = engine.begin(temp_title, "Top Plane")
        pocket_token = pocket["session_id"]
        pair = engine.rectangle_pair(pocket_token, 39, 39, 27, 25)
        fully_define(engine, pocket_token)
        segments = get_com_member(model.SketchManager.ActiveSketch, "GetSketchSegments") or ()
        x_values = set()
        y_values = set()
        for segment in segments:
            try:
                start = get_com_member(segment, "GetStartPoint2")
                end = get_com_member(segment, "GetEndPoint2")
            except Exception:
                continue
            if not bool(segment.ConstructionGeometry):
                x_values.update((round(float(start.X) * 1000.0, 6),
                                 round(float(end.X) * 1000.0, 6)))
                y_values.update((round(float(start.Y) * 1000.0, 6),
                                 round(float(end.Y) * 1000.0, 6)))
        actual_profile = {"x_mm": sorted(x_values), "y_mm": sorted(y_values)}
        expected_profile = {
            "x_mm": [-19.5, -13.5, 13.5, 19.5],
            "y_mm": [-19.5, -12.5, 12.5, 19.5],
        }
        if actual_profile != expected_profile:
            raise RuntimeError(
                f"Rectangle-pair profile changed during definition: "
                f"{actual_profile} != {expected_profile}"
            )
        engine.finish(pocket_token)
        cut_feature = engine.extrude(pocket_token, 55, cut=True)
        state = engine.model_state(pocket_token)

        box = list(get_com_member(model, "GetPartBox", True) or ())
        bounds = [round(float(value) * 1000.0, 6) for value in box[:6]] if len(box) >= 6 else None
        envelope = [round((float(box[index + 3]) - float(box[index])) * 1000.0, 6)
                    for index in range(3)] if len(box) >= 6 else None
        expected_bounds = [-92.5, 0.0, -92.5, 92.5, 70.0, 92.5]
        if bounds != expected_bounds:
            raise RuntimeError(f"Coordinate bounds mismatch: {bounds} != {expected_bounds}")
        expected = [185.0, 70.0, 185.0]
        if envelope != expected:
            raise RuntimeError(f"Envelope mismatch: {envelope} != {expected}")
        if state["solid_body_count"] != 1:
            raise RuntimeError(f"Expected one solid body, got {state['solid_body_count']}")

        print(json.dumps({
            "status": "ok",
            "document": temp_title,
            "base_sketch": base["sketch"],
            "base_feature": base_feature,
            "pocket_sketch": pocket["sketch"],
            "rectangle_pair": pair,
            "rectangle_pair_profile": actual_profile,
            "cut_feature": cut_feature,
            "solid_body_count": state["solid_body_count"],
            "bounds_mm": bounds,
            "envelope_mm": envelope,
        }, ensure_ascii=False))
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
