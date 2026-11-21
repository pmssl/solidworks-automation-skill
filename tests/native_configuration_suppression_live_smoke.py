"""Real SolidWorks regression for configuration-scoped feature suppression."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _volume_mm3(model) -> float:
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    return float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .080, .050)
        base = sw_part.extrude_boss(model, base_sketch, .012)
        if base is None:
            raise RuntimeError("base extrusion failed")
        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, .005)
        cut = sw_part.extrude_cut_through_all(model, cut_sketch)
        if cut is None:
            raise RuntimeError("through-all cut failed")
        cut_name = str(get_com_member(cut, "Name"))

        initial = sw_document_data.inspect_configurations(model)
        default_name = str(initial["active_configuration"])
        for name in ("无孔", "有孔"):
            created = sw_document_data.create_configuration(
                model, name, activate=True, rebuild=True, save=False,
            )
            if not created["success"]:
                raise RuntimeError(f"configuration creation failed: {created}")

        result = sw_document_data.set_feature_suppression(
            model,
            cut_name,
            "suppress",
            configuration_mode="specific",
            configuration_names=("无孔",),
            rebuild=True,
            restore_active=True,
            save=False,
        )
        if not result["success"]:
            raise RuntimeError(f"feature suppression failed: {result}")

        names = (default_name, "无孔", "有孔")
        states = sw_document_data.feature_suppression_states(
            model, cut_name, configuration_names=names, restore_active=True,
        )
        volumes = {}
        for name in names:
            activation = sw_document_data.activate_configuration(
                model, name, rebuild=True, save=False,
            )
            if not activation["success"]:
                raise RuntimeError(f"configuration activation failed: {activation}")
            volumes[name] = _volume_mm3(model)
        sw_document_data.activate_configuration(model, default_name, rebuild=True, save=False)

        full_volume = 80.0 * 50.0 * 12.0
        cut_volume = full_volume - math.pi * 5.0 ** 2 * 12.0
        expected_states = {default_name: False, "无孔": True, "有孔": False}
        if states["states"] != expected_states:
            raise RuntimeError(f"suppression state mismatch: {states['states']}")
        if abs(volumes["无孔"] - full_volume) > 1e-3:
            raise RuntimeError(f"suppressed volume mismatch: {volumes['无孔']}")
        for name in (default_name, "有孔"):
            if abs(volumes[name] - cut_volume) > 1e-3:
                raise RuntimeError(f"unsuppressed volume mismatch for {name}: {volumes[name]}")

        print(json.dumps({
            "status": "ok",
            "base_feature": str(get_com_member(base, "Name")),
            "cut_feature": cut_name,
            "configurations": list(names),
            "suppression_states": states["states"],
            "volumes_mm3": volumes,
            "expected_full_volume_mm3": full_volume,
            "expected_cut_volume_mm3": cut_volume,
            "active_configuration": sw_document_data.inspect_configurations(model)["active_configuration"],
            "rebuild": bool(get_com_member(model, "EditRebuild3")),
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        if not completed and original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
