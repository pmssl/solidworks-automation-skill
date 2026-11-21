"""Real SolidWorks probe/regression for sketch dimension attachment rebinding."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def segment_length_mm(segment):
    start = get_com_member(segment, "GetStartPoint2")
    end = get_com_member(segment, "GetEndPoint2")
    return math.dist(
        [float(get_com_member(start, axis)) for axis in ("X", "Y", "Z")],
        [float(get_com_member(end, axis)) for axis in ("X", "Y", "Z")],
    ) * 1000.0


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        sw_part.start_sketch(model, "Front Plane")
        first = sw_part.sketch_line(model, 0.0, 0.0, 0.010, 0.0)
        second = sw_part.sketch_line(model, 0.0, 0.020, 0.025, 0.020)
        if not sw_part._select_com_object(first, append=False, mark=0):
            raise RuntimeError("failed to select first line")
        display = model.AddDimension2(0.005, -0.005, 0.0)
        model.ClearSelection2(True)
        if display is None:
            raise RuntimeError("failed to create sketch dimension")
        annotation = get_com_member(display, "GetAnnotation")
        before = sw_part._as_tuple(get_com_member(annotation, "GetAttachedEntities3"))
        attached = sw_part._dispatch_array((second,))
        try:
            changed = bool(annotation.SetAttachedEntities(attached))
        except TypeError:
            changed = bool(
                annotation._oleobj_.InvokeTypes(
                    60, 0, sw_part.pythoncom.DISPATCH_METHOD,
                    (sw_part.pythoncom.VT_BOOL, 0),
                    ((sw_part.pythoncom.VT_VARIANT, 1),),
                    attached,
                )
            )
        after = sw_part._as_tuple(get_com_member(annotation, "GetAttachedEntities3"))
        dimension = get_com_member(display, "GetDimension2", 0)
        dimension.Name = "WidthDrive"
        if not bool(get_com_member(dimension, "SetToleranceType", 2)):
            raise RuntimeError("failed to set bilateral tolerance type")
        if not bool(get_com_member(dimension, "SetToleranceValues", -0.0002, 0.0003)):
            raise RuntimeError("failed to set bilateral tolerance values")
        value_mm = float(get_com_member(dimension, "SystemValue")) * 1000.0
        recreated = None
        recreated_attached = ()
        recreated_value_mm = None
        recreated_name = None
        recreated_tolerance = None
        if not changed:
            rebound = sw_part.rebind_sketch_dimension(
                model, display, (second,), 0.0125, 0.025
            )
            recreated = rebound["display_dimension"]
            recreated_value_mm = rebound["value"] * 1000.0
            recreated_attached = sw_part.display_dimension_attached_entities(recreated)
            recreated_name = rebound["name"]
            recreated_tolerance = rebound["tolerance"]
        second_length_mm = segment_length_mm(second)
        if recreated is not None and abs(second_length_mm - value_mm) > 1e-6:
            raise RuntimeError(
                f"recreated dimension did not drive replacement line: {second_length_mm}"
            )
        if recreated is not None and (
            recreated_name != "WidthDrive"
            or recreated_tolerance["type"] != 2
            or any(abs(actual - expected) > 1e-12 for actual, expected in zip(
                recreated_tolerance["values"], (-0.0002, 0.0003),
            ))
        ):
            raise RuntimeError(
                f"recreated dimension metadata mismatch: {recreated_name}, {recreated_tolerance}"
            )
        sw_part.end_sketch(model)
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("dimension rebind rebuild failed")
        success = changed or recreated is not None
        print(json.dumps({
            "status": "ok" if changed or recreated is not None else "blocked",
            "changed": changed,
            "before_count": len(before),
            "after_count": len(after),
            "value_mm": value_mm,
            "fallback_recreated": recreated is not None,
            "recreated_attached_count": len(recreated_attached),
            "recreated_value_mm": recreated_value_mm,
            "replacement_line_length_mm": second_length_mm,
            "recreated_name": recreated_name,
            "recreated_tolerance": recreated_tolerance,
            "document": title,
            "saved": False,
        }, ensure_ascii=False))
    finally:
        if success:
            if original_title and original_title != title:
                try:
                    sw.QuitDoc(original_title)
                except Exception:
                    pass
            try:
                sw.ActivateDoc2(title, False, 0)
            except Exception:
                pass
        else:
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
