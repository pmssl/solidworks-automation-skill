"""Real SolidWorks regression for direct RelationManager constraints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            first = model.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.020, 0.005, 0.0)
            second = model.SketchManager.CreateLine(0.030, 0.010, 0.0, 0.050, 0.020, 0.0)
            horizontal_first, horizontal_second, equal = (
                sw_part.add_sketch_relations_direct_batch(
                    model,
                    (((first,), 4), ((second,), 4), ((first, second), 14)),
                )
            )
            summaries = [
                sw_part.sketch_relation_summary(relation)
                for relation in (horizontal_first, horizontal_second, equal)
            ]
            lengths = [float(get_com_member(segment, "GetLength")) for segment in (first, second)]
            endpoints = [
                (
                    float(get_com_member(get_com_member(segment, "GetStartPoint2"), "Y")),
                    float(get_com_member(get_com_member(segment, "GetEndPoint2"), "Y")),
                )
                for segment in (first, second)
            ]
        if sketch_name is None or [item["type"] for item in summaries] != [4, 4, 14]:
            raise RuntimeError(f"direct relation readback mismatch: {summaries}")
        if any(abs(start - end) > 1e-9 for start, end in endpoints):
            raise RuntimeError(f"horizontal relations did not resolve geometry: {endpoints}")
        if abs(lengths[0] - lengths[1]) > 1e-9:
            raise RuntimeError(f"equal relation did not resolve lengths: {lengths}")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("direct relation sketch rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "sketch": sketch_name,
            "relation_summaries": summaries,
            "lengths_mm": [value * 1000.0 for value in lengths],
            "endpoint_y_mm": [[value * 1000.0 for value in pair] for pair in endpoints],
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
