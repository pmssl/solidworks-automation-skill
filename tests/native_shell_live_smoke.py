"""Real SolidWorks regression for semantic face selection and native shell."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def volume_mm3(model):
    body = (model.GetBodies2(0, False) or ())[0]
    return float(list(body.GetMassProperties(1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    title = None
    try:
        model = new_document(sw, "part")
        title = str(get_com_member(model, "GetTitle"))
        native = NativeParametric(connect=lambda: connect_solidworks(wait_seconds=1), part_ops=lambda: sw_part)
        begun = native.begin(title, "Front Plane")
        native.rectangle(begun["session_id"], 40, 30)
        native.auto_define(begun["session_id"])
        native.finish(begun["session_id"])
        base = sw_part.extrude_boss_midplane(model, begun["sketch"], 0.020)
        if base is None or int(get_com_member(base, "GetErrorCode")) != 0:
            raise RuntimeError("base feature failed")
        candidates = sw_part.find_planar_faces(model, area=0.0012, tolerance=1e-8)
        if len(candidates) != 2:
            raise RuntimeError(f"expected two 40x30 faces, got {len(candidates)}")
        face = max(candidates, key=lambda item: sw_part.planar_face_geometry(item)["center"])
        face_evidence = sw_part.planar_face_geometry(face)
        before = volume_mm3(model)
        feature = sw_part.shell(model, 0.002, [face], outward=False)
        if int(get_com_member(feature, "GetErrorCode")) != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("shell feature or rebuild failed")
        definition = get_com_member(feature, "GetDefinition")
        thickness_mm = float(get_com_member(definition, "Thickness")) * 1000.0
        removed_count = int(get_com_member(definition, "FacesRemovedCount"))
        after = volume_mm3(model)
        expected = 40 * 30 * 20 - 36 * 26 * 18
        if abs(thickness_mm - 2.0) > 1e-5 or removed_count != 1 or abs(after - expected) > 0.5:
            raise RuntimeError(
                f"shell mismatch: thickness={thickness_mm}, removed={removed_count}, volume={after}"
            )
        print(json.dumps({"status": "ok", "feature": str(feature.Name),
                          "thickness_mm": thickness_mm, "removed_faces": removed_count,
                          "selected_face": face_evidence, "volume_before_mm3": before,
                          "volume_after_mm3": after}, ensure_ascii=False))
    finally:
        if title:
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
