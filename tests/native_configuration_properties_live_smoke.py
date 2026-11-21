"""Live native configuration property and suppress-new-feature regression."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def volume_mm3(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, got {len(bodies)}")
    return float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9


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
        if base is None or int(get_com_member(base, "GetErrorCode")) != 0:
            raise RuntimeError("base extrusion failed")
        default_name = sw_document_data.inspect_configurations(model)["active_configuration"]
        created = sw_document_data.create_configuration(
            model,
            "属性配置",
            activate=False,
            rebuild=True,
            save=False,
        )
        if not created["success"]:
            raise RuntimeError(f"configuration creation failed: {created}")
        updated = sw_document_data.update_configuration_properties(
            model,
            "属性配置",
            comment="批量备注",
            description="轻量配置",
            alternate_name="PN-006",
            use_alternate_name_in_bom=True,
            use_description_in_bom=True,
            suppress_new_features=True,
            rebuild=True,
        )
        if not updated["success"]:
            raise RuntimeError(f"configuration property update failed: {updated}")
        expected_properties = {
            "comment": "批量备注",
            "description": "轻量配置",
            "alternate_name": "PN-006",
            "use_alternate_name_in_bom": True,
            "use_description_in_bom": True,
            "suppress_new_features": True,
        }
        properties = sw_document_data.inspect_configuration_properties(model, "属性配置")
        for key, value in expected_properties.items():
            if properties[key] != value:
                raise RuntimeError(f"property readback mismatch for {key}: {properties}")

        activation = sw_document_data.activate_configuration(
            model, default_name, rebuild=True, save=False,
        )
        if not activation["success"]:
            raise RuntimeError(f"default activation failed: {activation}")
        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
        cut = sw_part.extrude_cut_through_all(model, cut_sketch)
        if cut is None or int(get_com_member(cut, "GetErrorCode")) != 0:
            raise RuntimeError("through-all cut failed")
        cut_name = str(get_com_member(cut, "Name"))
        states = sw_document_data.feature_suppression_states(
            model,
            cut_name,
            configuration_names=(default_name, "属性配置"),
            restore_active=True,
        )
        expected_states = {default_name: False, "属性配置": True}
        if states["states"] != expected_states:
            raise RuntimeError(f"suppress-new-feature behavior mismatch: {states}")

        volumes = {}
        for name in (default_name, "属性配置"):
            active = sw_document_data.activate_configuration(
                model, name, rebuild=True, save=False,
            )
            if not active["success"]:
                raise RuntimeError(f"activation failed: {active}")
            volumes[name] = volume_mm3(model)
        sw_document_data.activate_configuration(model, default_name, rebuild=True, save=False)
        full_volume = 80.0 * 50.0 * 12.0
        cut_volume = full_volume - math.pi * 5.0**2 * 12.0
        if abs(volumes["属性配置"] - full_volume) > 1e-3:
            raise RuntimeError(f"suppressed configuration volume mismatch: {volumes}")
        if abs(volumes[default_name] - cut_volume) > 1e-3:
            raise RuntimeError(f"active configuration cut volume mismatch: {volumes}")

        success = True
        print(json.dumps({
            "status": "ok",
            "document": title,
            "saved": False,
            "properties": {key: properties[key] for key in expected_properties},
            "switched_for_inactive_property": updated["switched_for_inactive_property"],
            "suppression_states": states["states"],
            "volumes_mm3": volumes,
            "expected_full_volume_mm3": full_volume,
            "expected_cut_volume_mm3": cut_volume,
            "active_configuration": sw_document_data.inspect_configurations(model)["active_configuration"],
            "feature_error_codes": {
                str(get_com_member(base, "Name")): int(get_com_member(base, "GetErrorCode")),
                cut_name: int(get_com_member(cut, "GetErrorCode")),
            },
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
