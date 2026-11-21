"""Real SolidWorks regression for native rollback-bar control."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def volume_mm3(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"rollback body count mismatch: {len(bodies)}")
    return float(list(get_com_member(bodies[0], "GetMassProperties", 1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        sw_part.extrude_boss_midplane(model, base_sketch, .020)
        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            sw_part.sketch_circle(model, 0, 0, .004)
        cut = sw_part.extrude_cut_midplane(model, cut_sketch, .020)
        final_volume = volume_mm3(model)
        expected_final = 24000.0 - math.pi * 4.0 * 4.0 * 20.0
        if abs(final_volume - expected_final) > 1e-4:
            raise RuntimeError(f"rollback setup volume mismatch: {final_volume}")

        sw_part.rollback_to_feature(model, cut, before=True)
        rolled_volume = volume_mm3(model)
        rolled_state = bool(get_com_member(cut, "IsRolledBack"))
        if abs(rolled_volume - 24000.0) > 1e-4 or not rolled_state:
            raise RuntimeError(
                f"rollback-before mismatch: volume={rolled_volume}, state={rolled_state}"
            )

        sw_part.rollback_to_end(model)
        restored_volume = volume_mm3(model)
        restored_state = bool(get_com_member(cut, "IsRolledBack"))
        if abs(restored_volume - final_volume) > 1e-4 or restored_state:
            raise RuntimeError(
                f"rollback restore mismatch: volume={restored_volume}, state={restored_state}"
            )
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(cut, "Name")),
            "final_volume_mm3": final_volume,
            "rolled_volume_mm3": rolled_volume,
            "restored_volume_mm3": restored_volume,
            "rolled_state": rolled_state,
            "restored_state": restored_state,
        }, ensure_ascii=False))
    finally:
        try:
            sw_part.rollback_to_end(model)
        except Exception:
            pass
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
