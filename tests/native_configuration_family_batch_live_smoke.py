"""Real SolidWorks regression for native configuration-family batch updates."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _volume_mm3(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    return float(get_com_member(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.080, 0.050)
        feature = sw_part.extrude_boss(model, sketch_name, 0.012)
        feature_name = str(get_com_member(feature, "Name"))
        dimension_name = f"D1@{feature_name}"
        default_name = sw_document_data.inspect_configurations(model)["active_configuration"]
        depths = {default_name: 12.0, "薄型": 6.0, "加强型": 20.0}
        result = sw_document_data.apply_configuration_family(model, tuple(
            {
                "name": name,
                "dimensions_mm": {dimension_name: depth},
                "properties": {"ConfigurationClass": name, "NominalDepthMM": depth},
            }
            for name, depth in depths.items()
        ))
        if not result["success"]:
            raise RuntimeError(f"configuration family batch failed: {result}")
        dimension = model.Parameter(dimension_name)
        readback, volumes, properties = {}, {}, {}
        for name, expected in depths.items():
            activation = sw_document_data.activate_configuration(model, name, rebuild=True, save=False)
            if not activation["success"]:
                raise RuntimeError(f"could not activate {name}: {activation}")
            readback[name] = float(dimension.GetSystemValue2(name)) * 1000.0
            volumes[name] = _volume_mm3(model)
            properties[name] = sw_document_data.read_custom_property(
                model, "ConfigurationClass", configuration_name=name,
            )["raw"]
            if abs(readback[name] - expected) > 1e-6:
                raise RuntimeError(f"dimension mismatch for {name}: {readback[name]}")
            if abs(volumes[name] - 80.0 * 50.0 * expected) > 1e-3:
                raise RuntimeError(f"volume mismatch for {name}: {volumes[name]}")
            if properties[name] != name:
                raise RuntimeError(f"property mismatch for {name}: {properties[name]}")
        sw_document_data.activate_configuration(model, default_name, rebuild=True, save=False)
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("configuration family final rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "dimension": dimension_name, "depths_mm": readback,
            "volumes_mm3": volumes, "properties": properties,
            "active_configuration": sw_document_data.inspect_configurations(model)["active_configuration"],
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
