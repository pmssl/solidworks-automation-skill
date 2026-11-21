"""Real SolidWorks regression for native uniform and non-uniform Scale features."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _geometry(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    body = bodies[0]
    box = tuple(float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox"))
    volume = float(get_com_member(body, "GetMassProperties", 1.0)[3]) * 1e9
    return {
        "body_count": 1,
        "bounding_box_mm": box,
        "spans_mm": (box[3] - box[0], box[4] - box[1], box[5] - box[2]),
        "volume_mm3": volume,
    }


def _assert_geometry(actual, spans, volume):
    if any(not math.isclose(value, expected, abs_tol=1e-6)
           for value, expected in zip(actual["spans_mm"], spans)):
        raise RuntimeError(f"Scale spans mismatch: {actual}")
    if not math.isclose(actual["volume_mm3"], volume, abs_tol=1e-3):
        raise RuntimeError(f"Scale volume mismatch: {actual}")


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        base = sw_part.extrude_boss_midplane(model, sketch_name, .020)
        _assert_geometry(_geometry(model), (40.0, 30.0, 20.0), 24000.0)

        nonuniform = sw_part.scale_feature(
            model, 1.5, 0.5, 2.0, about="origin",
        )
        nonuniform_evidence = sw_part.scale_feature_evidence(nonuniform)
        nonuniform_geometry = _geometry(model)
        _assert_geometry(nonuniform_geometry, (60.0, 15.0, 40.0), 36000.0)
        if nonuniform_evidence["about"] != "origin" or nonuniform_evidence["uniform"]:
            raise RuntimeError(f"nonuniform feature data mismatch: {nonuniform_evidence}")
        if any(not math.isclose(value, expected, abs_tol=1e-12) for value, expected in zip(
            nonuniform_evidence["factors"], (1.5, 0.5, 2.0),
        )):
            raise RuntimeError(f"nonuniform factors mismatch: {nonuniform_evidence}")

        uniform = sw_part.scale_feature(model, 0.5, about="centroid")
        uniform_evidence = sw_part.scale_feature_evidence(uniform)
        uniform_geometry = _geometry(model)
        _assert_geometry(uniform_geometry, (30.0, 7.5, 20.0), 4500.0)
        if uniform_evidence["about"] != "centroid" or not uniform_evidence["uniform"]:
            raise RuntimeError(f"uniform feature data mismatch: {uniform_evidence}")
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("Scale rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode")) != 0 for feature in (
            base, nonuniform, uniform,
        )):
            raise RuntimeError("Scale feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "base_feature": str(get_com_member(base, "Name")),
            "nonuniform": {"feature_data": nonuniform_evidence, "geometry": nonuniform_geometry},
            "uniform": {"feature_data": uniform_evidence, "geometry": uniform_geometry},
        }, ensure_ascii=False))
    finally:
        if completed:
            if original_title and original_title != title:
                try: sw.QuitDoc(original_title)
                except Exception: pass
            try: sw.ActivateDoc2(title, False, 0)
            except Exception: pass
        else:
            try: sw.QuitDoc(title)
            except Exception: pass
            if original_title:
                try: sw.ActivateDoc2(original_title, False, 0)
                except Exception: pass


if __name__ == "__main__":
    main()
