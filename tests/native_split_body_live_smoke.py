"""Real SolidWorks regression for a plane-driven native Split feature."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document, open_document


def volume_mm3(body): return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def main():
    if os.environ.get("SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC") != "1":
        raise RuntimeError(
            "interactive Split diagnostic is disabled; set "
            "SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC=1 only for supervised debugging"
        )
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    with tempfile.TemporaryDirectory(prefix="sw_split_body_") as temp_dir:
        model = new_document(sw, "part")
        title = str(get_com_member(model, "GetTitle"))
        outputs = (
            Path(temp_dir) / "SplitBody1.SLDPRT",
            Path(temp_dir) / "SplitBody2.SLDPRT",
        )
        try:
            with sw_part.sketch(model, "Front Plane") as sketch_name:
                sw_part.sketch_rectangle(model, 0, 0, .040, .030)
            sw_part.extrude_boss_midplane(model, sketch_name, .020)
            plane = get_com_member(model, "FeatureByName", "上视基准面")
            if plane is None: plane = get_com_member(model, "FeatureByName", "Top Plane")
            result = sw_part._split_bodies_experimental(
                model, plane, consume_cut=True,
                save_paths=tuple(str(path) for path in outputs),
                allow_modal=True,
            )
            bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
            volumes = sorted(volume_mm3(body) for body in bodies)
            if any(not path.is_file() or path.stat().st_size == 0 for path in outputs):
                raise RuntimeError("Split did not save both result bodies")
            if any(abs(value - 12000.0) > 1e-4 for value in volumes):
                raise RuntimeError(f"Split retained-body volume mismatch: {volumes}")
            data = get_com_member(result["feature"], "GetDefinition")
            consumed = bool(get_com_member(data, "Consume"))
            saved_volumes = []
            for path in outputs:
                child = open_document(sw, str(path), silent=True, raise_on_error=True)
                child_title = str(get_com_member(child, "GetTitle"))
                child_bodies = tuple(get_com_member(child, "GetBodies2", 0, False) or ())
                if len(child_bodies) != 1:
                    raise RuntimeError(f"saved Split body count mismatch for {path}: {len(child_bodies)}")
                saved_volumes.append(volume_mm3(child_bodies[0]))
                sw.QuitDoc(child_title)
            if any(abs(value - 12000.0) > 1e-4 for value in saved_volumes):
                raise RuntimeError(f"saved Split body volumes mismatch: {saved_volumes}")
            print(json.dumps({"status": "ok", "feature": str(get_com_member(result["feature"], "Name")),
                              "preview_count": len(result["preview_bodies"]),
                              "consume": consumed, "body_count": len(bodies),
                              "volumes_mm3": volumes,
                              "saved_volumes_mm3": saved_volumes,
                              "saved_sizes": [path.stat().st_size for path in outputs]}, ensure_ascii=False))
        finally:
            try: sw.QuitDoc(title)
            except Exception: pass
            if original_title:
                try: sw.ActivateDoc2(original_title, False, 0)
                except Exception: pass


if __name__ == "__main__":
    main()
