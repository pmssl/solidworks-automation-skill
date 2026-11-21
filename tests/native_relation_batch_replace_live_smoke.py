"""Real SolidWorks regression for transactional relation entity replacement."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _line_geometry(line):
    start = get_com_member(line, "GetStartPoint2")
    end = get_com_member(line, "GetEndPoint2")
    return {
        "start": (float(get_com_member(start, "X")), float(get_com_member(start, "Y"))),
        "end": (float(get_com_member(end, "X")), float(get_com_member(end, "Y"))),
        "length": float(get_com_member(line, "GetLength")),
    }


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            old = model.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.020, 0.005, 0.0)
            other = model.SketchManager.CreateLine(0.030, 0.010, 0.0, 0.055, 0.018, 0.0)
            replacement = model.SketchManager.CreateLine(0.0, 0.030, 0.0, 0.030, 0.040, 0.0)
            horizontal = sw_part.add_sketch_relation_direct(model, old, 4)
            equal = sw_part.add_sketch_relation_direct(model, (old, other), 14)
            before = _line_geometry(replacement)
            relations = sw_part.replace_sketch_relation_entities_batch(
                ((horizontal, old, replacement), (equal, old, replacement)),
            )
            after = _line_geometry(replacement)
            other_after = _line_geometry(other)
            summaries = [sw_part.sketch_relation_summary(relation) for relation in relations]
            attached_names = [len(tuple(get_com_member(relation, "GetEntities") or ())) for relation in relations]
        if sketch_name is None or [item["type"] for item in summaries] != [4, 14]:
            raise RuntimeError(f"relation replacement type mismatch: {summaries}")
        if abs(after["start"][1] - after["end"][1]) > 1e-9:
            raise RuntimeError(f"replacement line did not inherit horizontal relation: {after}")
        if abs(after["length"] - other_after["length"]) > 1e-9:
            raise RuntimeError(f"replacement line did not inherit equal relation: {after}, {other_after}")
        if attached_names != [1, 2] or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"relation replacement readback failed: {attached_names}")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "sketch": sketch_name, "relation_summaries": summaries,
            "replacement_before_mm": {key: ([v * 1000 for v in value] if isinstance(value, tuple) else value * 1000) for key, value in before.items()},
            "replacement_after_mm": {key: ([v * 1000 for v in value] if isinstance(value, tuple) else value * 1000) for key, value in after.items()},
            "other_length_mm": other_after["length"] * 1000,
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
