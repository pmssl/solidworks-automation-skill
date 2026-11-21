"""Real save-close-reopen regression for SolidWorks persistent references."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks, get_com_member, new_document, open_document, save_document,
)
from scripts.sw_entity_reference import create_persistent_reference, resolve_persistent_reference


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    open_title = None
    with tempfile.TemporaryDirectory(prefix="sw_persist_ref_") as temp_dir:
        path = Path(temp_dir) / "persistent_reference.SLDPRT"
        try:
            model = new_document(sw, "part")
            open_title = str(get_com_member(model, "GetTitle"))
            with sw_part.sketch(model, "Front Plane") as sketch_name:
                sw_part.sketch_rectangle(model, 0, 0, .040, .030)
            sw_part.extrude_boss_midplane(model, sketch_name, .020)
            face = sw_part.find_largest_outer_planar_face(model)
            before = sw_part.planar_face_geometry(face)
            reference = create_persistent_reference(model, face)
            if not save_document(model, str(path)) or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("persistent-reference source part was not saved")
            saved_title = str(get_com_member(model, "GetTitle"))
            sw.QuitDoc(saved_title)
            open_title = None

            reopened = open_document(sw, str(path), silent=True, raise_on_error=True)
            open_title = str(get_com_member(reopened, "GetTitle"))
            resolved = resolve_persistent_reference(reopened, reference)
            after = sw_part.planar_face_geometry(resolved["entity"])
            if abs(after["area"] - before["area"]) > 1e-10:
                raise RuntimeError(f"persistent face area mismatch: {before} != {after}")
            if math.dist(after["center"], before["center"]) > 1e-10:
                raise RuntimeError(f"persistent face center mismatch: {before} != {after}")
            normal_dot = abs(sum(a * b for a, b in zip(after["normal"], before["normal"])))
            if abs(normal_dot - 1.0) > 1e-10:
                raise RuntimeError(f"persistent face normal mismatch: {before} != {after}")
            print(json.dumps({
                "status": "ok",
                "byte_count": reference.byte_count,
                "resolve_error_code": resolved["error_code"],
                "area_mm2": after["area"] * 1e6,
                "center_mm": [value * 1000.0 for value in after["center"]],
                "normal": after["normal"],
                "saved_size": path.stat().st_size,
            }, ensure_ascii=False))
        finally:
            if open_title:
                try:
                    sw.QuitDoc(open_title)
                except Exception:
                    pass
            if original_title:
                try:
                    sw.ActivateDoc2(original_title, False, 0)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
