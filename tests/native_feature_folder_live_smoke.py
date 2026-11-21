"""Real SolidWorks regression for a native containing FeatureManager folder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def finished_profile(native, title, kind):
    begun = native.begin(title, "Front Plane")
    token = begun["session_id"]
    if kind == "rectangle":
        native.rectangle(token, 80, 60)
    else:
        native.circle(token, 0, 0, 3)
    native.auto_define(token)
    native.finish(token)
    return begun["sketch"]


def volume_mm3(model):
    body = tuple(model.GetBodies2(0, False) or ())
    if len(body) != 1:
        raise RuntimeError(f"expected one solid body, got {len(body)}")
    return float(list(body[0].GetMassProperties(1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        native = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )
        base = sw_part.extrude_boss_midplane(
            model, finished_profile(native, title, "rectangle"), 0.010
        )
        cut = sw_part.extrude_cut_midplane(
            model, finished_profile(native, title, "circle"), 0.010
        )
        before = volume_mm3(model)
        folder_feature = sw_part.create_feature_folder(
            model, (base, cut), name="Machining Features"
        )
        if int(get_com_member(folder_feature, "GetErrorCode")) != 0:
            raise RuntimeError("feature folder has a rebuild error")
        folder = get_com_member(folder_feature, "GetSpecificFeature2")
        children = sw_part._as_tuple(get_com_member(folder, "GetFeatures"))
        child_names = [str(get_com_member(item, "Name")) for item in children]
        if len(children) < 2:
            raise RuntimeError(f"folder contains too few features: {child_names}")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("rebuild failed after creating feature folder")
        after = volume_mm3(model)
        if abs(after - before) > 1e-6:
            raise RuntimeError(f"folder changed body volume: {before} -> {after}")
        print(json.dumps({
            "status": "ok",
            "folder": str(get_com_member(folder_feature, "Name")),
            "child_count": len(children),
            "children": child_names,
            "volume_mm3": after,
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
