"""Diagnostic: promote a verified tangent Fill Surface to curvature continuity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_fill_surface_continuity_live_smoke import (
    _cylinder_boundary,
    _definition_boundaries,
)
from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks,
    create_empty_dispatch_variant,
    get_com_member,
    new_document,
)


def _read_controls(feature, model):
    data = get_com_member(feature, "GetDefinition")
    if not bool(get_com_member(
        data, "AccessSelections", model, create_empty_dispatch_variant(),
    )):
        raise RuntimeError("could not access Fill Surface selections")
    try:
        boundaries = _definition_boundaries(data)
        controls = tuple(
            int(get_com_member(data, "GetCurvatureControl", boundary))
            for boundary in boundaries
        )
    finally:
        get_com_member(data, "ReleaseSelectionAccess")
    return controls


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_circle(model, 0.0, 0.0, .020)
        support = sw_part.extrude_surface(
            model, sketch_name, .025, cap_end=False, knit_result=False,
        )
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(surface_bodies) != 1:
            raise RuntimeError(f"support surface body count mismatch: {len(surface_bodies)}")
        _geometry, direction_face, _boundary_geometry, boundary_edge = (
            _cylinder_boundary(surface_bodies[0])
        )
        feature = sw_part.fill_surface(
            model, boundary_edge, resolution=3,
            contact_types=(1,), direction_faces=(direction_face,),
        )
        before = _read_controls(feature, model)

        data = get_com_member(feature, "GetDefinition")
        if not bool(get_com_member(
            data, "AccessSelections", model, create_empty_dispatch_variant(),
        )):
            raise RuntimeError("could not access Fill Surface selections for edit")
        edit_results = []
        try:
            boundaries = _definition_boundaries(data)
            for boundary in boundaries:
                edit_results.append(bool(get_com_member(
                    data, "SetCurvatureControl", boundary, 2, False,
                )))
            modified = bool(get_com_member(
                # The makepy IFeature wrapper requires a true null Dispatch
                # value here; a VARIANT(VT_DISPATCH, None) cannot be converted
                # by InvokeTypes even though the underlying signature is Object.
                feature, "ModifyDefinition", data, model, None,
            ))
        except Exception:
            try:
                get_com_member(data, "ReleaseSelectionAccess")
            except Exception:
                pass
            raise

        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        after = _read_controls(feature, model)
        error_code = int(get_com_member(feature, "GetErrorCode"))
        result = {
            "status": "ok" if (
                all(edit_results) and modified and rebuilt
                and after == (2,) and error_code == 0
            ) else "unsupported",
            "document": title,
            "support_feature": str(get_com_member(support, "Name")),
            "fill_feature": str(get_com_member(feature, "Name")),
            "before": before,
            "set_results": edit_results,
            "modify_definition": modified,
            "after": after,
            "rebuild": rebuilt,
            "error_code": error_code,
            "saved": False,
        }
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] != "ok":
            raise RuntimeError(f"curvature edit did not round-trip: {result}")
        completed = True
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
