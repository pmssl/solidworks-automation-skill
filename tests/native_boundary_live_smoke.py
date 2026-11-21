"""Real SW2025 regressions for native Boundary Boss and Boundary Surface."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks, create_empty_dispatch_variant, get_com_member,
    new_document,
)


_latest_title = None


def new_live_part(sw):
    global _latest_title
    if _latest_title:
        try:
            # QuitDoc has an explicit "without saving changes" contract.
            # Do not use UI-command routes while rotating unnamed live parts.
            sw.QuitDoc(_latest_title)
        except Exception:
            pass
        _latest_title = None
    model = new_document(sw, "part")
    _latest_title = str(get_com_member(model, "GetTitle"))
    return model, _latest_title


def discard(sw, title):
    global _latest_title
    try:
        sw.QuitDoc(title)
    except Exception:
        pass
    if _latest_title == title:
        _latest_title = None


def body_volume_mm3(body):
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def sheet_area_mm2(body):
    """Read IBody2 sheet area from GetMassProperties index 3."""
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e6


def make_surface_network(model):
    """Create four exact 2D segments and return D1/D2 object tuples."""
    with sw_part.sketch(model, "Front Plane"):
        lower = sw_part.sketch_line(model, -0.010, 0.000, 0.010, 0.000)
        upper = sw_part.sketch_line(model, -0.015, 0.030, 0.015, 0.030)
        left = sw_part.sketch_line(model, -0.010, 0.000, -0.015, 0.030)
        right = sw_part.sketch_line(model, 0.010, 0.000, 0.015, 0.030)
    return (lower, upper), (left, right)


def make_surface_edge_pair(model):
    """Create a trapezoid prism and return two adjacent solid B-Rep edges."""
    with sw_part.sketch(model, "Front Plane") as profile:
        sw_part.sketch_line(model, -0.010, 0.000, 0.010, 0.000)
        sw_part.sketch_line(model, 0.010, 0.000, 0.015, 0.030)
        sw_part.sketch_line(model, 0.015, 0.030, -0.015, 0.030)
        sw_part.sketch_line(model, -0.015, 0.030, -0.010, 0.000)
    sw_part.extrude_boss(model, profile, 0.005, direction=False, merge=False)
    solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(solids) != 1:
        raise RuntimeError(f"edge probe expected one solid body, got {len(solids)}")
    cap_faces = []
    for face in sw_part.solid_faces(model):
        try:
            summary = sw_part.planar_face_geometry(face)
        except Exception:
            continue
        if abs(summary["area"] - 0.00075) <= 1e-8:
            cap_faces.append((face, summary))
    if len(cap_faces) != 2:
        raise RuntimeError(f"edge probe expected two trapezoid caps, got {len(cap_faces)}")
    cap, _summary = max(cap_faces, key=lambda item: item[1]["center"][2])
    edges = tuple(get_com_member(cap, "GetEdges") or ())
    summaries = [(edge, sw_part.edge_geometry(edge)) for edge in edges]
    horizontal = sorted(
        (item for item in summaries if abs(item[1]["direction"][0]) > 0.99),
        key=lambda item: item[1]["midpoint"][1],
    )
    slanted = sorted(
        (item for item in summaries if abs(item[1]["direction"][0]) <= 0.99),
        key=lambda item: item[1]["midpoint"][0],
    )
    if len(horizontal) != 2 or len(slanted) != 2:
        raise RuntimeError(f"could not classify trapezoid edges: {summaries}")
    return model, solids[0], horizontal[0][0], slanted[0][0]


def make_parallel_solid_edges(model):
    """Create two separated prisms and return facing parallel cap edges."""
    with sw_part.sketch(model, "Front Plane") as profile:
        sw_part.sketch_corner_rectangle(model, -0.025, -0.005, -0.015, 0.005)
        sw_part.sketch_corner_rectangle(model, 0.015, -0.005, 0.025, 0.005)
    sw_part.extrude_boss(model, profile, 0.005, direction=False, merge=False)
    solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(solids) != 2:
        raise RuntimeError(f"parallel-edge setup expected two solids, got {len(solids)}")
    body_edges = []
    for body in solids:
        box = tuple(float(value) for value in get_com_member(body, "GetBodyBox"))
        center_x = (box[0] + box[3]) / 2.0
        candidates = []
        for edge in tuple(get_com_member(body, "GetEdges") or ()):
            try:
                summary = sw_part.edge_geometry(edge)
            except Exception:
                continue
            if abs(summary["direction"][1]) > 0.99:
                candidates.append((edge, summary))
        if len(candidates) < 4:
            raise RuntimeError(f"parallel-edge setup found too few Y edges: {len(candidates)}")
        body_edges.append((center_x, candidates))
    body_edges.sort(key=lambda item: item[0])
    left_candidates = body_edges[0][1]
    right_candidates = body_edges[1][1]
    left_inner_x = max(item[1]["midpoint"][0] for item in left_candidates)
    right_inner_x = min(item[1]["midpoint"][0] for item in right_candidates)
    left_edge = max(
        (item for item in left_candidates if abs(item[1]["midpoint"][0] - left_inner_x) < 1e-9),
        key=lambda item: item[1]["midpoint"][2],
    )[0]
    right_edge = max(
        (item for item in right_candidates if abs(item[1]["midpoint"][0] - right_inner_x) < 1e-9),
        key=lambda item: item[1]["midpoint"][2],
    )[0]
    return solids, left_edge, right_edge


def make_frame_inner_edges(model):
    """Create a rectangular frame and return its four top inner-hole edges."""
    with sw_part.sketch(model, "Front Plane") as profile:
        sw_part.sketch_corner_rectangle(model, -0.025, -0.015, 0.025, 0.015)
        sw_part.sketch_corner_rectangle(model, -0.015, -0.005, 0.015, 0.005)
    sw_part.extrude_boss(model, profile, 0.005, direction=False, merge=False)
    solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(solids) != 1:
        raise RuntimeError(f"frame setup expected one solid, got {len(solids)}")
    body = solids[0]
    box = tuple(float(value) for value in get_com_member(body, "GetBodyBox"))
    top_z = box[5]
    d1 = []
    d2 = []
    for edge in tuple(get_com_member(body, "GetEdges") or ()):
        try:
            summary = sw_part.edge_geometry(edge)
        except Exception:
            continue
        if abs(summary["midpoint"][2] - top_z) > 1e-8:
            continue
        if abs(summary["length"] - 0.030) < 1e-8 and abs(summary["direction"][0]) > 0.99:
            d1.append((edge, summary))
        if abs(summary["length"] - 0.010) < 1e-8 and abs(summary["direction"][1]) > 0.99:
            d2.append((edge, summary))
    d1.sort(key=lambda item: item[1]["midpoint"][1])
    d2.sort(key=lambda item: item[1]["midpoint"][0])
    if len(d1) != 2 or len(d2) != 2:
        raise RuntimeError(f"frame inner-edge classification failed: {len(d1)}/{len(d2)}")
    return body, tuple(item[0] for item in d1), tuple(item[0] for item in d2)


def boundary_surface_edge_selection_case(sw):
    """Prove the official EDGE category and D1/D2 marks without creation."""
    model, title = new_live_part(sw)
    completed = False
    try:
        _model, _solid, d1_edge, d2_edge = make_surface_edge_pair(model)
        model.ClearSelection2(True)
        for index, (edge, mark) in enumerate(((d1_edge, 1), (d2_edge, 2))):
            if not sw_part._select_boundary_entity(
                model, edge, append=index > 0, mark=mark,
            ):
                raise RuntimeError("Boundary edge probe could not select edge")
        manager = model.SelectionManager
        count = int(get_com_member(manager, "GetSelectedObjectCount2", -1))
        evidence = [
            {
                "type": int(get_com_member(manager, "GetSelectedObjectType3", i, -1)),
                "mark": int(get_com_member(manager, "GetSelectedObjectMark", i)),
            }
            for i in range(1, count + 1)
        ]
        if evidence != [{"type": 1, "mark": 1}, {"type": 1, "mark": 2}]:
            raise RuntimeError(f"Boundary edge evidence mismatch: {evidence}")
        completed = True
        return {
            "selection_count": count,
            "selection_evidence": evidence,
            "live_document_title": title,
            "boundary_creator_called": False,
            "saved": False,
        }
    finally:
        if not completed:
            discard(sw, title)


def boundary_surface_selection_case(sw):
    """Probe only entity types and marks; never call a Boundary creator."""
    model, title = new_live_part(sw)
    completed = False
    try:
        d1, d2 = make_surface_network(model)
        model.ClearSelection2(True)
        for direction, curves in enumerate((d1, d2), start=1):
            for index, curve in enumerate(curves):
                if not sw_part._select_com_object_with_data(
                    model, curve, append=bool(direction > 1 or index), mark=direction,
                ):
                    raise RuntimeError("Boundary selection-only probe could not select curve")
        manager = model.SelectionManager
        count = int(get_com_member(manager, "GetSelectedObjectCount2", -1))
        evidence = [
            {
                "type": int(get_com_member(manager, "GetSelectedObjectType3", i, -1)),
                "mark": int(get_com_member(manager, "GetSelectedObjectMark", i)),
            }
            for i in range(1, count + 1)
        ]
        if [row["mark"] for row in evidence] != [1, 1, 2, 2]:
            raise RuntimeError(f"Boundary selection marks mismatch: {evidence}")
        completed = True
        return {
            "selection_count": count,
            "selection_evidence": evidence,
            "live_document_title": title,
            "boundary_creator_called": False,
            "saved": False,
        }
    finally:
        if not completed:
            discard(sw, title)


def boundary_boss_case(sw):
    model, title = new_live_part(sw)
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as first_profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        sw_part.extrude_boss(
            model, first_profile, 0.010, direction=False, merge=False,
        )
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, plane_name) as second_profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.006)
        sw_part.extrude_boss(
            model, second_profile, 0.010, direction=False, merge=False,
        )
        before = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if len(before) != 2:
            raise RuntimeError(f"boundary setup expected two bodies, got {len(before)}")
        first_faces = sw_part.find_planar_faces(
            model, area=math.pi * 0.010 ** 2,
            center=(0.0, 0.0, 0.010), normal=(0.0, 0.0, 1.0),
            tolerance=1e-7,
        )
        second_faces = sw_part.find_planar_faces(
            model, area=math.pi * 0.006 ** 2,
            center=(0.0, 0.0, 0.030), normal=(0.0, 0.0, 1.0),
            tolerance=1e-7,
        )
        if len(first_faces) != 1 or len(second_faces) != 1:
            raise RuntimeError(
                f"boundary cap resolution failed: {len(first_faces)}/{len(second_faces)}"
            )
        feature = sw_part.boundary_boss(
            model, (first_faces[0], second_faces[0]),
            direction1_data=(
                {"tangency_type": 0}, {"tangency_type": 0},
            ),
            allow_experimental=True,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"boundary boss failed: error={error}, bodies={len(bodies)}"
            )
        volume = body_volume_mm3(bodies[0])
        expected = (
            math.pi * 10.0 ** 2 * 10.0
            + math.pi * 6.0 ** 2 * 10.0
            + math.pi * 20.0 / 3.0 * (10.0 ** 2 + 10.0 * 6.0 + 6.0 ** 2)
        )
        if abs(volume - expected) > 5.0:
            raise RuntimeError(f"boundary boss volume mismatch: {volume} != {expected}")
        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, create_empty_dispatch_variant(),
        ))
        if not accessed:
            raise RuntimeError("could not access Boundary Boss selections")
        try:
            d1_count = int(get_com_member(definition, "GetCurvesCount", 0))
            d2_count = int(get_com_member(definition, "GetCurvesCount", 1))
            tangencies = [
                int(get_com_member(definition, "GetGuideTangencyType", 0, index))
                for index in range(d1_count)
            ]
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if d1_count != 2 or d2_count != 0 or tangencies != [0, 0]:
            raise RuntimeError(
                f"boundary boss definition mismatch: {d1_count}/{d2_count}/{tangencies}"
            )
        box = [float(value) * 1000.0 for value in get_com_member(bodies[0], "GetBodyBox")]
        completed = True
        return {
            "feature": str(get_com_member(feature, "Name")),
            "feature_type": str(get_com_member(feature, "GetTypeName2")),
            "direction1_curve_count": d1_count,
            "direction2_curve_count": d2_count,
            "tangencies": tangencies,
            "body_count": len(bodies),
            "volume_mm3": volume,
            "analytic_delta_mm3": volume - expected,
            "body_box_mm": box,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }
    finally:
        if not completed:
            discard(sw, title)


def boundary_surface_case(sw):
    model, title = new_live_part(sw)
    completed = False
    try:
        # The four true solid EDGEs around a through-hole form a complete D1/D2
        # network, while the 30 x 10 mm opening has no coincident source face.
        _source_solid, d1_edges, d2_edges = make_frame_inner_edges(model)
        one_each = "--one-each" in sys.argv
        selected_d1 = d1_edges[:1] if one_each else d1_edges
        selected_d2 = d2_edges[:1] if one_each else d2_edges
        before_sheets = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        feature = sw_part.boundary_surface(
            model, selected_d1, selected_d2,
            allow_experimental=True, use_legacy="--legacy" in sys.argv,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        sheets = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if error != 0 or not rebuilt or len(solids) != 1 or len(sheets) <= len(before_sheets):
            raise RuntimeError(
                f"boundary surface failed: error={error}, solids={len(solids)}, sheets={len(sheets)}"
            )
        areas = [sheet_area_mm2(body) for body in sheets]
        added_area = sum(areas) - sum(
            sheet_area_mm2(body) for body in before_sheets
        )
        if added_area <= 0.0:
            raise RuntimeError(f"boundary surface added no positive area: {areas}")
        if not one_each and abs(added_area - 300.0) > 1.0:
            raise RuntimeError(f"boundary surface area mismatch: {added_area} != 300")
        definition = get_com_member(feature, "GetDefinition")
        d1_count = int(get_com_member(definition, "GetCurvesCount", 0))
        d2_count = int(get_com_member(definition, "GetCurvesCount", 1))
        expected_counts = (1, 1) if one_each else (2, 2)
        if (d1_count, d2_count) != expected_counts:
            raise RuntimeError(
                f"boundary surface curve counts mismatch: {d1_count}/{d2_count}"
            )
        completed = True
        return {
            "feature": str(get_com_member(feature, "Name")),
            "feature_type": str(get_com_member(feature, "GetTypeName2")),
            "direction1_curve_count": d1_count,
            "direction2_curve_count": d2_count,
            "solid_body_count": len(solids),
            "surface_body_count": len(sheets),
            "surface_areas_mm2": areas,
            "added_surface_area_mm2": added_area,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }
    finally:
        if not completed:
            discard(sw, title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    try:
        if "--edge-selection-only" in sys.argv:
            results = {"boundary_surface_edge_selection": boundary_surface_edge_selection_case(sw)}
        elif "--selection-only" in sys.argv:
            results = {"boundary_surface_selection": boundary_surface_selection_case(sw)}
        elif "--boss-only" in sys.argv:
            results = {"boundary_boss": boundary_boss_case(sw)}
        elif "--surface-only" in sys.argv:
            results = {"boundary_surface": boundary_surface_case(sw)}
        else:
            results = {
                "boundary_boss": boundary_boss_case(sw),
                "boundary_surface": boundary_surface_case(sw),
            }
        print(json.dumps({"status": "ok", **results}, ensure_ascii=False))
    finally:
        target = _latest_title or original_title
        if target:
            try:
                sw.ActivateDoc2(target, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
