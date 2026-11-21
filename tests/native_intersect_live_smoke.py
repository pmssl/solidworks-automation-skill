"""Real SolidWorks regression for a native Intersect feature."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks,
    create_empty_dispatch_variant,
    get_com_member,
    new_document,
)


def volume(body): return float(list(get_com_member(body, "GetMassProperties", 1.0))[3])


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as first:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        sw_part.extrude_boss_midplane(model, first, .020)
        with sw_part.sketch(model, "Front Plane") as second:
            sw_part.sketch_rectangle(model, .015, 0, .020, .020)
        sw_part.extrude_boss_midplane(model, second, .020, merge=False)
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        overlap_only = "--overlap-only" in sys.argv
        consume = "--consume" in sys.argv
        result = sw_part.intersect_bodies(
            model, bodies,
            target_volume=6.0e-6 if overlap_only else None,
            merge=True,
            consume=consume,
        )
        after = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        after_volume = volume(after[0]) * 1e9 if len(after) == 1 else 0.0
        preview = sorted(volume(body) * 1e9 for body in result["preview_regions"])
        expected_volume = 6000.0 if overlap_only else 26000.0
        if len(after) != 1 or abs(after_volume - expected_volume) > 1e-4:
            raise RuntimeError(f"Intersect result mismatch: count={len(after)}, volume={after_volume}")
        feature = result["feature"]
        error_code = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, create_empty_dispatch_variant(),
        ))
        if not accessed:
            raise RuntimeError("could not access Intersect feature selections")
        try:
            tool_count = int(get_com_member(definition, "GetIntersectionsToolsCount"))
            region_count = int(get_com_member(definition, "GetIntersectionsCount"))
            merge_readback = bool(get_com_member(definition, "Merge"))
            consume_readback = bool(get_com_member(definition, "Consume"))
            cap_readback = bool(get_com_member(definition, "CapPlanar"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if (
            error_code != 0 or not rebuilt or tool_count != 2 or region_count != 3
            or not merge_readback or consume_readback != consume or cap_readback
        ):
            raise RuntimeError(
                "Intersect definition mismatch: "
                f"error={error_code}, rebuild={rebuilt}, tools={tool_count}, "
                f"regions={region_count}, merge={merge_readback}, "
                f"consume={consume_readback}, cap={cap_readback}"
            )
        print(json.dumps({"status": "ok", "feature": str(get_com_member(feature, "Name")),
                          "feature_type": str(get_com_member(feature, "GetTypeName2")),
                          "preview_volumes_mm3": preview,
                          "included_indices": result["included_indices"],
                          "consume": consume,
                          "tool_count": tool_count,
                          "region_count": region_count,
                          "error_code": error_code,
                          "rebuild": rebuilt,
                          "result_volume_mm3": after_volume,
                          "live_document_title": title,
                          "saved": False}, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try: sw.QuitDoc(title)
            except Exception: pass
        if not completed and original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
