"""Real SolidWorks regression for a native bending Flex feature."""

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
    return body, {"body_count": 1, "bounding_box_mm": box, "volume_mm3": volume}


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .010, .010)
        base = sw_part.extrude_boss_midplane(model, sketch_name, .100)
        body, before = _geometry(model)

        flex = sw_part.flex_feature(
            model, body, "bending", math.radians(30.0),
            rotation_axis=(1.0, 0.0, 0.0),
            tangent_axis=(0.0, 1.0, 0.0),
            radius_axis=(0.0, 0.0, 1.0),
            pivot=(0.0, 0.0, 0.0),
            left_trim=.040, right_trim=.040,
            hard_edges=False,
        )
        evidence = sw_part.flex_feature_evidence(flex, model)
        _, after = _geometry(model)

        if evidence["type"] != "Bending" or evidence["error_code"] != 0:
            raise RuntimeError(f"Flex feature state mismatch: {evidence}")
        d0 = next(row for row in evidence["dimensions"] if row["name"] == "D0")
        if not math.isclose(d0["system_value"], math.radians(30), rel_tol=1e-9):
            raise RuntimeError(f"Flex angle readback mismatch: {evidence['dimensions']}")
        if not math.isclose(after["volume_mm3"], before["volume_mm3"], rel_tol=1e-3):
            raise RuntimeError(f"Flex did not preserve volume: before={before}, after={after}")
        if all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(
            after["bounding_box_mm"], before["bounding_box_mm"],
        )):
            raise RuntimeError("Flex feature did not change body geometry")
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("Flex rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (base, flex)):
            raise RuntimeError("Flex feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "mode": "bending", "amount_deg": 30.0,
            "feature": evidence, "before": before, "after": after,
        }, ensure_ascii=False))
    finally:
        if completed:
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
