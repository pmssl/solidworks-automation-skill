"""Real SolidWorks regression for dependency-aware reorder preflight."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _top_order(model):
    names = []
    feature = get_com_member(model, "FirstFeature")
    while feature is not None:
        names.append(str(get_com_member(feature, "Name")))
        feature = get_com_member(feature, "GetNextFeature")
    return names


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.080, 0.050)
        base = sw_part.extrude_boss(model, base_sketch, 0.012)
        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
        cut = sw_part.extrude_cut_through_all(model, cut_sketch)
        circular_edges = sw_part.find_circular_edges(model, radius=0.005, tolerance=1e-8)
        if len(circular_edges) < 1:
            raise RuntimeError("could not resolve circular cut edge")
        fillet = sw_part.fillet(model, 0.001, edges=(circular_edges[0],))
        path = sw_part.feature_dependency_path(model, base, fillet)
        order_before = _top_order(model)
        blocked = ""
        try:
            sw_part.reorder_feature_after_safe(model, base, fillet)
        except ValueError as exc:
            blocked = str(exc)
        order_after = _top_order(model)
        names = [item[0] for item in path]
        if not blocked or names[:1] != [str(get_com_member(base, "Name"))] or names[-1:] != [str(get_com_member(fillet, "Name"))]:
            raise RuntimeError(f"dependency reorder preflight did not block: {blocked}, {names}")
        if order_before != order_after:
            raise RuntimeError("blocked dependency reorder still changed FeatureManager order")
        errors = {
            str(get_com_member(feature, "Name")): int(get_com_member(feature, "GetErrorCode"))
            for feature in (base, cut, fillet)
        }
        if any(errors.values()) or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"dependency chain rebuild failed: {errors}")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "dependency_path": names, "blocked_reason": blocked,
            "feature_order_unchanged": order_before == order_after,
            "feature_errors": errors,
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
