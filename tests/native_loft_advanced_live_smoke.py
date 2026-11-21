"""Real SW2025 regressions for advanced native loft modes."""

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


_latest_live_title = None


def new_live_part(sw, prefix):
    """Create an unsaved live Part while retaining only the latest result.

    Live geometry regressions do not need a persisted file.  Avoiding SaveAs here
    removes the modal-save path entirely.  A later case closes the preceding
    task-created document; the final successful case stays open for inspection.
    """
    del prefix  # Used only to make call sites describe the regression case.
    global _latest_live_title
    if _latest_live_title:
        try:
            sw.QuitDoc(_latest_live_title)
        except Exception:
            pass
        _latest_live_title = None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    _latest_live_title = title
    return model, title


def discard_live_part(sw, title):
    global _latest_live_title
    try:
        sw.QuitDoc(title)
    except Exception:
        pass
    if _latest_live_title == title:
        _latest_live_title = None


def live_result_title(title):
    return {
        "live_document_title": title,
        "saved": False,
    }


def body_result(model, feature, expected_volume, tolerance=5.0):
    error = int(get_com_member(feature, "GetErrorCode"))
    rebuilt = bool(model.ForceRebuild3(False))
    if error != 0 or not rebuilt:
        raise RuntimeError(f"advanced loft rebuild failed: error={error}")
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"advanced loft body count mismatch: {len(bodies)}")
    body = bodies[0]
    volume = float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9
    if abs(volume - expected_volume) > tolerance:
        raise RuntimeError(f"advanced loft volume mismatch: {volume} != {expected_volume}")
    box = [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]
    return {
        "body_count": len(bodies),
        "volume_mm3": volume,
        "analytic_delta_mm3": volume - expected_volume,
        "body_box_mm": box,
        "spans_mm": sorted(abs(box[index + 3] - box[index]) for index in range(3)),
        "rebuild": rebuilt,
    }


def volume_mm3(body):
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def centerline_case(sw):
    model, title = new_live_part(sw, "sw_loft_centerline_")
    completed = False
    try:
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, "Front Plane") as first_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.020)
        with sw_part.sketch(model, plane_name) as second_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch_3d(model) as centerline:
            sw_part.sketch_line_3d(
                model, (0.0, 0.0, 0.0), (0.0, 0.0, 0.030),
            )
        feature = sw_part.loft_feature_advanced(
            model, (first_section, second_section), centerline=centerline,
        )
        expected = math.pi * 30.0 / 3.0 * (
            20.0 ** 2 + 20.0 * 10.0 + 10.0 ** 2
        )
        result = body_result(model, feature, expected)
        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, create_empty_dispatch_variant(),
        ))
        if not accessed:
            raise RuntimeError("could not access centerline loft selections")
        try:
            selected_centerline = get_com_member(definition, "Centerline")
            guide_count = int(get_com_member(definition, "GetGuideCurvesCount"))
            profile_count = int(get_com_member(definition, "GetProfileCount"))
            is_boss = bool(get_com_member(definition, "IsBossFeature"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if selected_centerline is None or guide_count != 0 or profile_count != 2 or not is_boss:
            raise RuntimeError(
                "centerline loft semantics mismatch: "
                f"center={selected_centerline}, guides={guide_count}, "
                f"profiles={profile_count}, boss={is_boss}"
            )
        result.update({
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first_section, second_section],
            "centerline": centerline,
            "centerline_readback": True,
            "guide_count": guide_count,
            "profile_count": profile_count,
            "is_boss": is_boss,
        })
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def centerline_cut_case(sw):
    model, title = new_live_part(sw, "sw_loft_centerline_cut_")
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_profile:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.060, 0.060)
        sw_part.extrude_boss_midplane(model, base_profile, 0.080)
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        before_volume = volume_mm3(bodies[0])
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, "Front Plane") as first_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch(model, plane_name) as second_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
        with sw_part.sketch_3d(model) as centerline:
            sw_part.sketch_line_3d(
                model, (0.0, 0.0, 0.0), (0.0, 0.0, 0.030),
            )
        feature = sw_part.loft_feature_advanced(
            model, (first_section, second_section),
            centerline=centerline, cut=True,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"centerline loft cut failed: error={error}, bodies={len(bodies)}"
            )
        after_volume = volume_mm3(bodies[0])
        removed = before_volume - after_volume
        expected_removed = math.pi * 30.0 / 3.0 * (
            10.0 ** 2 + 10.0 * 5.0 + 5.0 ** 2
        )
        if abs(removed - expected_removed) > 5.0:
            raise RuntimeError(
                f"centerline loft cut volume mismatch: {removed} != {expected_removed}"
            )
        definition = get_com_member(feature, "GetDefinition")
        if not bool(get_com_member(
            definition, "AccessSelections", model, create_empty_dispatch_variant(),
        )):
            raise RuntimeError("could not access centerline loft-cut selections")
        try:
            selected_centerline = get_com_member(definition, "Centerline")
            guide_count = int(get_com_member(definition, "GetGuideCurvesCount"))
            is_boss = bool(get_com_member(definition, "IsBossFeature"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if selected_centerline is None or guide_count != 0 or is_boss:
            raise RuntimeError(
                "centerline loft-cut semantics mismatch: "
                f"center={selected_centerline}, guides={guide_count}, boss={is_boss}"
            )
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first_section, second_section],
            "centerline": centerline,
            "centerline_readback": True,
            "guide_count": guide_count,
            "is_boss": is_boss,
            "body_count": len(bodies),
            "before_volume_mm3": before_volume,
            "after_volume_mm3": after_volume,
            "removed_volume_mm3": removed,
            "analytic_delta_mm3": removed - expected_removed,
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def thin_midplane_case(sw):
    model, title = new_live_part(sw, "sw_loft_thin_midplane_")
    completed = False
    try:
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, "Front Plane") as first_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch(model, plane_name) as second_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
        feature = sw_part.loft_feature_advanced(
            model, (first_section, second_section),
            thin_type=2, thickness1=0.002,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"thin loft failed: error={error}, bodies={len(bodies)}"
            )
        definition = get_com_member(feature, "GetDefinition")
        is_thin = bool(get_com_member(definition, "IsThinFeature"))
        wall_type = int(get_com_member(definition, "ThinWallType"))
        forward_thickness = float(get_com_member(
            definition, "GetWallThickness", True,
        ))
        reverse_thickness = float(get_com_member(
            definition, "GetWallThickness", False,
        ))
        if (
            not is_thin
            or wall_type != 2
            or abs(forward_thickness - 0.002) > 1e-9
            or abs(reverse_thickness) > 1e-12
        ):
            raise RuntimeError(
                f"thin loft readback mismatch: thin={is_thin}, "
                f"type={wall_type}, forward={forward_thickness}, "
                f"reverse={reverse_thickness}"
            )
        volume = volume_mm3(bodies[0])
        approximate = 900.0 * math.pi
        if abs(volume - approximate) > 100.0:
            raise RuntimeError(
                f"thin loft volume mismatch: {volume} vs approximate {approximate}"
            )
        box = [float(value) * 1000.0 for value in get_com_member(bodies[0], "GetBodyBox")]
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first_section, second_section],
            "is_thin": is_thin,
            "thin_wall_type": wall_type,
            "body_count": len(bodies),
            "volume_mm3": volume,
            "approximate_delta_mm3": volume - approximate,
            "body_box_mm": box,
            "forward_thickness_mm": forward_thickness * 1000.0,
            "reverse_thickness_mm": reverse_thickness * 1000.0,
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def thin_midplane_cut_case(sw):
    model, title = new_live_part(sw, "sw_loft_thin_midplane_cut_")
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_profile:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.060, 0.060)
        sw_part.extrude_boss_midplane(model, base_profile, 0.080)
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        before_volume = volume_mm3(bodies[0])
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, "Front Plane") as first_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch(model, plane_name) as second_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
        feature = sw_part.loft_feature_advanced(
            model, (first_section, second_section), cut=True,
            thin_type=2, thickness1=0.002,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"thin loft cut failed: error={error}, bodies={len(bodies)}"
            )
        after_volume = volume_mm3(bodies[0])
        removed = before_volume - after_volume
        if abs(removed - 2866.4343118074257) > 5.0:
            raise RuntimeError(f"thin loft-cut removed volume mismatch: {removed}")
        definition = get_com_member(feature, "GetDefinition")
        is_thin = bool(get_com_member(definition, "IsThinFeature"))
        wall_type = int(get_com_member(definition, "ThinWallType"))
        forward_thickness = float(get_com_member(
            definition, "GetWallThickness", True,
        ))
        reverse_thickness = float(get_com_member(
            definition, "GetWallThickness", False,
        ))
        is_boss = bool(get_com_member(definition, "IsBossFeature"))
        if (
            not is_thin or is_boss or wall_type != 2
            or abs(forward_thickness - 0.002) > 1e-9
            or abs(reverse_thickness) > 1e-12
        ):
            raise RuntimeError(
                "thin loft-cut readback mismatch: "
                f"thin={is_thin}, boss={is_boss}, type={wall_type}, "
                f"forward={forward_thickness}, reverse={reverse_thickness}"
            )
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first_section, second_section],
            "is_thin": is_thin,
            "is_boss": is_boss,
            "thin_wall_type": wall_type,
            "forward_thickness_mm": forward_thickness * 1000.0,
            "reverse_thickness_mm": reverse_thickness * 1000.0,
            "body_count": len(bodies),
            "before_volume_mm3": before_volume,
            "after_volume_mm3": after_volume,
            "removed_volume_mm3": removed,
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def closed_boss_case(sw):
    model, title = new_live_part(sw, "sw_loft_closed_boss_")
    completed = False
    try:
        center_radius = 0.020
        profile_radius = 0.003
        profiles = []
        # Four vertical sections follow a closed loop in the model XY plane.
        # Top-plane local X maps to model X; Right-plane local Y maps to model Y.
        profile_specs = (
            ("Top Plane", center_radius, 0.0, (center_radius, 0.0, 0.0)),
            ("Right Plane", 0.0, center_radius, (0.0, center_radius, 0.0)),
            ("Top Plane", -center_radius, 0.0, (-center_radius, 0.0, 0.0)),
            ("Right Plane", 0.0, -center_radius, (0.0, -center_radius, 0.0)),
        )
        for plane_name, center_x, center_y, _world_center in profile_specs:
            with sw_part.sketch(model, plane_name) as profile:
                sw_part.sketch_circle(
                    model, center_x, center_y, profile_radius,
                )
            profiles.append(profile)
        pick_points = tuple(
            (center[0], center[1], profile_radius)
            for _plane_name, _center_x, _center_y, center in profile_specs
        )
        with sw_part.sketch_3d(model) as closed_guide:
            for index, start in enumerate(pick_points):
                sw_part.sketch_line_3d(
                    model, start, pick_points[(index + 1) % len(pick_points)],
                )
        feature = sw_part.loft_feature_advanced(
            model, tuple(profiles), closed=True, keep_tangency=False,
            guide_curves=(closed_guide,), section_pick_points=pick_points,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"closed loft failed: error={error}, bodies={len(bodies)}"
            )
        definition = get_com_member(feature, "GetDefinition")
        closed = bool(get_com_member(definition, "Close"))
        profile_count = int(get_com_member(definition, "GetProfileCount"))
        is_boss = bool(get_com_member(definition, "IsBossFeature"))
        if not closed or profile_count != 4 or not is_boss:
            raise RuntimeError(
                f"closed loft semantics mismatch: closed={closed}, "
                f"profiles={profile_count}, boss={is_boss}"
            )
        volume = volume_mm3(bodies[0])
        box = [float(value) * 1000.0 for value in get_com_member(bodies[0], "GetBodyBox")]
        spans = sorted(abs(box[index + 3] - box[index]) for index in range(3))
        if spans[0] < 5.5 or spans[1] < 39.0 or spans[2] < 39.0:
            raise RuntimeError(f"closed loft bounds mismatch: {box}")
        center_path_length = 4.0 * math.sqrt(2.0) * center_radius * 1000.0
        expected_volume = math.pi * (profile_radius * 1000.0) ** 2 * center_path_length
        if abs(volume - expected_volume) > 500.0:
            raise RuntimeError(
                f"closed loft volume mismatch: {volume} vs {expected_volume}"
            )
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "profiles": profiles,
            "closed_guide": closed_guide,
            "closed": closed,
            "profile_count": profile_count,
            "is_boss": is_boss,
            "body_count": len(bodies),
            "volume_mm3": volume,
            "approximate_delta_mm3": volume - expected_volume,
            "body_box_mm": box,
            "spans_mm": spans,
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def constrained_boss_case(sw, *, vector=False):
    prefix = "sw_loft_vector_constraints_" if vector else "sw_loft_normal_constraints_"
    model, title = new_live_part(sw, prefix)
    completed = False
    try:
        plane = sw_part.offset_plane(model, "Front Plane", 0.030)
        plane_name = str(get_com_member(plane, "Name"))
        with sw_part.sketch(model, "Front Plane") as first_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch(model, plane_name) as second_section:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.006)
        start_reference = None
        end_reference = None
        matching_type = 1
        axis_name = None
        if vector:
            front = get_com_member(model, "FeatureByName", "前视基准面")
            if front is None:
                front = get_com_member(model, "FeatureByName", "Front Plane")
            top = get_com_member(model, "FeatureByName", "上视基准面")
            if top is None:
                top = get_com_member(model, "FeatureByName", "Top Plane")
            axis = sw_part.reference_axis_from_planes(model, front, top)
            axis_name = str(get_com_member(axis, "Name"))
            start_reference = axis
            end_reference = axis
            matching_type = 2
        feature = sw_part.loft_feature_advanced(
            model, (first_section, second_section),
            start_matching_type=matching_type,
            end_matching_type=matching_type,
            start_tangent_length=1.5,
            end_tangent_length=0.75,
            reverse_start_tangent=True,
            start_tangent_reference=start_reference,
            end_tangent_reference=end_reference,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"constrained loft failed: error={error}, bodies={len(bodies)}"
            )
        definition = get_com_member(feature, "GetDefinition")
        start_type = int(get_com_member(definition, "StartTangencyType"))
        end_type = int(get_com_member(definition, "EndTangencyType"))
        start_length = float(get_com_member(definition, "StartTangentLength"))
        end_length = float(get_com_member(definition, "EndTangentLength"))
        reverse_start = bool(get_com_member(
            definition, "ReverseStartTangentDirection",
        ))
        reverse_end = bool(get_com_member(
            definition, "ReverseEndTangentDirection",
        ))
        if (
            start_type != matching_type or end_type != matching_type
            or abs(start_length - 1.5) > 1e-9
            or abs(end_length - 0.75) > 1e-9
            or not reverse_start or reverse_end
        ):
            raise RuntimeError(
                f"constrained loft readback mismatch: start={start_type}/{start_length}, "
                f"end={end_type}/{end_length}, reverse={reverse_start}/{reverse_end}"
            )
        accessed = False
        if vector:
            accessed = bool(get_com_member(
                definition, "AccessSelections", model,
                create_empty_dispatch_variant(),
            ))
            if not accessed:
                raise RuntimeError("could not access direction-vector loft selections")
        try:
            start_vector = get_com_member(definition, "StartDirectionVector")
            end_vector = get_com_member(definition, "EndDirectionVector")
            selection_marks = []
            if accessed:
                count = int(get_com_member(
                    model.SelectionManager, "GetSelectedObjectCount2", -1,
                ))
                selection_marks = [
                    int(get_com_member(
                        model.SelectionManager, "GetSelectedObjectMark", index,
                    ))
                    for index in range(1, count + 1)
                ]
        finally:
            if accessed:
                get_com_member(definition, "ReleaseSelectionAccess")
        body = bodies[0]
        volume = volume_mm3(body)
        if volume <= 0.0:
            raise RuntimeError(
                "constrained loft returned a nominal solid body with zero volume"
            )
        box = [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "profiles": [first_section, second_section],
            "matching_type": matching_type,
            "start_tangent_length": start_length,
            "end_tangent_length": end_length,
            "reverse_start_tangent": reverse_start,
            "reverse_end_tangent": reverse_end,
            "direction_axis": axis_name,
            "direction_vector_properties_readback": bool(
                start_vector is not None and end_vector is not None
            ),
            "selection_marks": selection_marks,
            "body_count": len(bodies),
            "volume_mm3": volume,
            "body_box_mm": box,
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def tangent_to_face_case(sw):
    """Attach a loft to an existing cylindrical boss with type-3 tangency."""
    model, title = new_live_part(sw, "sw_loft_tangent_face_")
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        sw_part.extrude_boss(model, base_profile, 0.010, merge=True)
        base_volume = volume_mm3(tuple(
            get_com_member(model, "GetBodies2", 0, False) or (),
        )[0])
        cap_faces = sw_part.find_planar_faces(
            model, area=math.pi * 0.010 ** 2,
            normal=(0.0, 0.0, 1.0), tolerance=1e-7,
        )
        top_faces = tuple(
            face for face in cap_faces
            if abs(sw_part.planar_face_geometry(face)["center"][2]) > 1e-6
        )
        if len(top_faces) != 1:
            raise RuntimeError(
                f"expected one cylindrical-boss top face, got {len(top_faces)}"
            )
        cap_z = sw_part.planar_face_geometry(top_faces[0])["center"][2]
        end_plane = sw_part.offset_plane(
            model, "Front Plane", 0.040,
            reverse_direction=cap_z < 0.0,
        )
        end_plane_name = str(get_com_member(end_plane, "Name"))
        with sw_part.sketch(model, end_plane_name) as end_profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.006)
        feature = sw_part.loft_feature_advanced(
            model, (top_faces[0], end_profile),
            start_matching_type=3,
            end_matching_type=1,
            start_tangent_length=1.0,
            end_tangent_length=0.75,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if error != 0 or not rebuilt or len(bodies) != 1:
            raise RuntimeError(
                f"tangent-to-face loft failed: error={error}, bodies={len(bodies)}"
            )
        body = bodies[0]
        total_volume = volume_mm3(body)
        if total_volume <= base_volume:
            raise RuntimeError(
                f"tangent loft did not add positive volume: {total_volume}"
            )
        definition = get_com_member(feature, "GetDefinition")
        start_type = int(get_com_member(definition, "StartTangencyType"))
        end_type = int(get_com_member(definition, "EndTangencyType"))
        profile_count = int(get_com_member(definition, "GetProfileCount"))
        if start_type != 3 or end_type != 1 or profile_count != 2:
            raise RuntimeError(
                "tangent-to-face loft definition mismatch: "
                f"start={start_type}, end={end_type}, profiles={profile_count}"
            )
        cylindrical_faces = []
        for face in sw_part.solid_faces(model):
            try:
                cylindrical_faces.append(sw_part.cylindrical_face_geometry(face))
            except (TypeError, ValueError, RuntimeError):
                pass
        if not cylindrical_faces:
            raise RuntimeError("tangent loft lost the existing cylindrical side face")
        box = [float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")]
        result = {
            "feature": str(get_com_member(feature, "Name")),
            "base_profile": base_profile,
            "end_profile": end_profile,
            "start_matching_type": start_type,
            "end_matching_type": end_type,
            "profile_count": profile_count,
            "base_volume_mm3": base_volume,
            "total_volume_mm3": total_volume,
            "added_volume_mm3": total_volume - base_volume,
            "cylindrical_face_count": len(cylindrical_faces),
            "body_box_mm": box,
            "body_count": len(bodies),
            "rebuild": rebuilt,
        }
        result.update(live_result_title(title))
        completed = True
        return result
    finally:
        if not completed:
            discard_live_part(sw, title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    try:
        if "--thin-only" in sys.argv:
            results = {
                "thin_midplane_boss": thin_midplane_case(sw),
                "thin_midplane_cut": thin_midplane_cut_case(sw),
            }
        elif "--centerline-only" in sys.argv:
            results = {
                "centerline_boss": centerline_case(sw),
                "centerline_cut": centerline_cut_case(sw),
            }
        elif "--closed-only" in sys.argv:
            results = {"closed_boss": closed_boss_case(sw)}
        elif "--constraints-only" in sys.argv:
            normal = constrained_boss_case(sw)
            vector = constrained_boss_case(sw, vector=True)
            same_volume = abs(
                normal["volume_mm3"] - vector["volume_mm3"]
            ) <= 1e-6
            same_box = max(
                abs(a - b) for a, b in zip(
                    normal["body_box_mm"], vector["body_box_mm"],
                )
            ) <= 1e-6
            if same_volume and same_box:
                raise RuntimeError(
                    "direction-vector constraint produced no geometric change"
                )
            results = {
                "normal_constraints": normal,
                "vector_constraints": vector,
            }
        elif "--tangent-face-only" in sys.argv:
            results = {"tangent_to_face": tangent_to_face_case(sw)}
        else:
            results = {
                "centerline_boss": centerline_case(sw),
                "centerline_cut": centerline_cut_case(sw),
                "thin_midplane_boss": thin_midplane_case(sw),
                "thin_midplane_cut": thin_midplane_cut_case(sw),
                "normal_constraints": constrained_boss_case(sw),
                "vector_constraints": constrained_boss_case(sw, vector=True),
                "tangent_to_face": tangent_to_face_case(sw),
            }
        print(json.dumps({"status": "ok", **results}, ensure_ascii=False))
    finally:
        target_title = _latest_live_title or original_title
        if target_title:
            try:
                sw.ActivateDoc2(target_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
