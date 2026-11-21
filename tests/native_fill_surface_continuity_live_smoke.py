"""Real SolidWorks regression for tangent/curvature Fill Surface boundaries."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from win32com.client import gencache

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks,
    create_empty_dispatch_variant,
    get_com_member,
    new_document,
)


def _cylinder_boundary(surface_body):
    faces = tuple(get_com_member(surface_body, "GetFaces") or ())
    cylinders = []
    for face in faces:
        try:
            cylinders.append((sw_part.cylindrical_face_geometry(face), face))
        except (TypeError, ValueError, RuntimeError):
            continue
    if len(cylinders) != 1:
        raise RuntimeError(f"expected one cylindrical face, found {len(cylinders)}")
    cylinder_geometry, cylinder_face = cylinders[0]

    edges = tuple(get_com_member(surface_body, "GetEdges") or ())
    circles = []
    for edge in edges:
        try:
            circles.append((sw_part.circular_edge_geometry(edge), edge))
        except (TypeError, ValueError, RuntimeError):
            continue
    if len(circles) != 2:
        raise RuntimeError(f"expected two circular boundaries, found {len(circles)}")
    circles.sort(key=lambda item: item[0]["center"])
    boundary_geometry, boundary_edge = circles[-1]
    return cylinder_geometry, cylinder_face, boundary_geometry, boundary_edge


def _open_box_boundaries(surface_body, top_z=.010):
    result = []
    for edge in tuple(get_com_member(surface_body, "GetEdges") or ()):
        try:
            geometry = sw_part.edge_geometry(edge)
        except (TypeError, ValueError, RuntimeError):
            continue
        if abs(geometry["midpoint"][2] - top_z) > 1e-8:
            continue
        adjacent = tuple(
            face for face in
            tuple(get_com_member(edge, "GetTwoAdjacentFaces2") or ())
            if face is not None
        )
        if len(adjacent) != 1:
            raise RuntimeError(
                f"open-box boundary should have one adjacent face, found {len(adjacent)}"
            )
        sw_part.planar_face_geometry(adjacent[0])
        result.append((geometry, edge, adjacent[0]))
    result.sort(key=lambda item: item[0]["midpoint"])
    if len(result) != 4:
        raise RuntimeError(f"expected four top opening edges, found {len(result)}")
    return tuple(item[1] for item in result), tuple(item[2] for item in result)


def _definition_boundaries(data):
    """Return boundary proxies owned by the feature definition itself."""
    module = gencache.EnsureModule(
        "{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 33, 0,
    )
    typed = module.IFillSurfaceFeatureData(data._oleobj_)
    result = typed.GetPatchBoundary()
    entities = result[0] if isinstance(result, tuple) and len(result) == 2 else result
    entities = tuple(entities) if isinstance(entities, (tuple, list)) else (entities,)
    if not entities or any(entity is None for entity in entities):
        raise RuntimeError(f"unexpected Fill Surface boundary result: {result!r}")
    return entities


def main():
    contact_type = 2 if "--curvature" in sys.argv else 1
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            if contact_type == 2:
                sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
            else:
                sw_part.sketch_circle(model, 0.0, 0.0, .020)
        if contact_type == 2:
            sw_part.extrude_boss_midplane(model, sketch_name, .020)
            top_faces = sw_part.find_planar_faces(
                model, center=(0.0, 0.0, .010), tolerance=1e-8,
            )
            if len(top_faces) != 1:
                raise RuntimeError(f"top face resolution mismatch: {len(top_faces)}")
            support = sw_part.delete_faces(model, top_faces[0], mode="delete")
        else:
            support = sw_part.extrude_surface(
                model, sketch_name, .025, cap_end=False, knit_result=False,
            )
        before_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(before_bodies) != 1:
            raise RuntimeError(f"support surface body count mismatch: {len(before_bodies)}")
        if contact_type == 2:
            boundary_edges, direction_faces = _open_box_boundaries(before_bodies[0])
            boundaries = tuple(sw_part.edge_geometry(edge) for edge in boundary_edges)
            support_kind = "open_box"
            expected_support_area = 4000.0
        else:
            _support_geometry, direction_face, boundary, boundary_edge = (
                _cylinder_boundary(before_bodies[0])
            )
            boundary_edges = (boundary_edge,)
            direction_faces = (direction_face,)
            boundaries = (boundary,)
            support_kind = "cylinder"
            expected_support_area = 2.0 * math.pi * 20.0 * 25.0
        feature = sw_part.fill_surface(
            model,
            boundary_edges,
            resolution=3,
            contact_types=(contact_type,) * len(boundary_edges),
            direction_faces=direction_faces,
        )

        data = get_com_member(feature, "GetDefinition")
        resolution = int(get_com_member(data, "ResolutionControl"))
        accessed = bool(get_com_member(
            data, "AccessSelections", model, create_empty_dispatch_variant(),
        ))
        if not accessed:
            raise RuntimeError("could not access Fill Surface selections")
        try:
            boundary_count = int(get_com_member(data, "GetPatchBoundaryCount"))
            constraint_count = int(get_com_member(data, "GetConstraintCurvesCount"))
            # The API explicitly requires an entity returned by GetPatchBoundary;
            # a pre-feature Edge proxy can return -1 even for a valid feature.
            definition_boundaries = _definition_boundaries(data)
            actual_contacts = tuple(int(get_com_member(
                data, "GetCurvatureControl", definition_boundary,
            )) for definition_boundary in definition_boundaries)
        finally:
            get_com_member(data, "ReleaseSelectionAccess")

        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        areas_mm2 = [
            sum(float(get_com_member(face, "GetArea"))
                for face in tuple(get_com_member(body, "GetFaces") or ())) * 1e6
            for body in surface_bodies
        ]
        error_code = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if (
            resolution != 3
            or boundary_count != len(boundary_edges)
            or constraint_count != 0
            or actual_contacts != (contact_type,) * len(boundary_edges)
            or error_code != 0
            or not rebuilt
            or len(surface_bodies) < 1
            or sum(areas_mm2) <= expected_support_area + 1.0
        ):
            raise RuntimeError(
                "Fill Surface continuity verification failed: "
                f"resolution={resolution}, boundaries={boundary_count}, "
                f"constraints={constraint_count}, contacts={actual_contacts}, "
                f"bodies={len(surface_bodies)}, areas={areas_mm2}, "
                f"error={error_code}, rebuild={rebuilt}"
            )

        print(json.dumps({
            "status": "ok",
            "support_feature": str(get_com_member(support, "Name")),
            "feature": str(get_com_member(feature, "Name")),
            "contact_type": contact_type,
            "contact_types": actual_contacts,
            "resolution": resolution,
            "boundary_count": boundary_count,
            "constraint_count": constraint_count,
            "surface_body_count": len(surface_bodies),
            "surface_area_mm2": areas_mm2,
            "support_kind": support_kind,
            "support_area_mm2": expected_support_area,
            "boundary_count_expected": len(boundary_edges),
            "boundary_geometry": boundaries,
            "error_code": error_code,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
        if original_title and original_title != title:
            sw.QuitDoc(original_title)
        sw.ActivateDoc2(title, False, 0)
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
