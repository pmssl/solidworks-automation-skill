"""Additive, state-checked native sketch workflow for solidworks-automation-skill.

No COM objects are stored in the sketch session.  Only the active document's title/path,
the sketch's feature name, and a session token are retained.
"""

from __future__ import annotations

import math
import os
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable


FULLY_CONSTRAINED = 3  # swConstrainedStatus_e.swFullyConstrained
CONSTRAINT_STATES = {
    1: "unknown", 2: "under_defined", 3: "fully_defined",
    4: "over_defined", 5: "no_solution", 6: "invalid_solution",
    7: "autosolve_off",
}


@dataclass
class SketchSession:
    token: str
    title: str
    path: str
    sketch_name: str
    open: bool = True
    reverse_boss_direction: bool = False


def _mm(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > 5000:
        raise ValueError("Size must be in (0, 5000] mm")
    return value / 1000.0


def _coord_mm(value: float) -> float:
    if not math.isfinite(value) or abs(value) > 5000:
        raise ValueError("Coordinate must be finite and within +/-5000 mm")
    return value / 1000.0


@contextmanager
def _exact_sketch_creation(sketch_manager: Any):
    """Disable interactive inference while placing exact requested geometry."""
    previous = bool(getattr(sketch_manager, "AddToDB", False))
    try:
        sketch_manager.AddToDB = True
        yield
    finally:
        sketch_manager.AddToDB = previous


def _com_get(obj: Any, member: str) -> Any:
    """Read a no-argument COM member exposed as a method or pseudo-property."""
    value = getattr(obj, member)
    try:
        return value() if callable(value) else value
    except Exception as exc:
        message = str(exc)
        if ("-2147352573" in message or "找不到成员" in message
                or "Member not found" in message):
            # Some pywin32 dispatch properties advertise __call__, but invoking
            # them raises DISP_E_MEMBERNOTFOUND.  The object itself is the value.
            return value
        raise


def _empty_dispatch() -> Any:
    """Return an explicit VT_DISPATCH(None) for strict optional COM parameters."""
    try:
        from .sw_connect import create_empty_dispatch_variant
    except ImportError:
        from sw_connect import create_empty_dispatch_variant
    return create_empty_dispatch_variant()


@contextmanager
def _no_dimension_popup(sw: Any):
    """Guard against the blocking 'Input dimension value' Modify dialog.

    If pywin32 has no generated enum, require explicit operator verification.
    This setting affects the running SolidWorks application's preferences.
    """
    preference = None
    try:
        from win32com.client import constants
        preference = int(constants.swInputDimValOnCreate)
    except (ImportError, AttributeError, TypeError):
        # Verified from the installed SolidWorks 2025 swconst.tlb.
        preference = 10
    if preference is None:
        if os.environ.get("SW_NATIVE_DIM_DIALOG_DISABLED") != "1":
            raise RuntimeError(
                "Turn off Tools > Options > System Options > General > "
                "Input dimension value, then set SW_NATIVE_DIM_DIALOG_DISABLED=1"
            )
        yield
        return
    previous = bool(sw.GetUserPreferenceToggle(preference))
    if previous:
        sw.SetUserPreferenceToggle(preference, False)
    try:
        yield
    finally:
        if previous:
            sw.SetUserPreferenceToggle(preference, True)


def _doc_id(model: Any) -> tuple[str, str]:
    return str(_com_get(model, "GetTitle")), str(_com_get(model, "GetPathName") or "")


def _feature_rows(model: Any, limit: int = 400) -> list[tuple[Any, int]]:
    """Include absorbed sketch subfeatures; never rely on localized names."""
    rows: list[tuple[Any, int]] = []

    def scan(first: Any, level: int, next_method: str) -> None:
        feat = first
        while feat is not None:
            if len(rows) >= limit:
                raise RuntimeError("Feature tree exceeds the bounded inspection limit")
            rows.append((feat, level))
            if level < 12:
                child = _com_get(feat, "GetFirstSubFeature")
                if child is not None:
                    scan(child, level + 1, "GetNextSubFeature")
            feat = _com_get(feat, next_method)

    scan(_com_get(model, "FirstFeature"), 0, "GetNextFeature")
    return rows


def _find_feature(model: Any, name: str) -> Any:
    matches = [feature for feature, _ in _feature_rows(model)
               if str(feature.Name) == name]
    if not matches:
        raise RuntimeError(f"Feature {name!r} not found")
    # The same absorbed sketch can occur both as a feature and a subfeature.
    return matches[0]


def _sketch_name(model: Any, before: set[str]) -> str:
    candidates = [str(feat.Name) for feat, _ in _feature_rows(model)
                  if _com_get(feat, "GetTypeName2") == "ProfileFeature"
                  and str(feat.Name) not in before]
    if len(candidates) == 1:
        return candidates[0]
    active = model.SketchManager.ActiveSketch
    if active is not None:
        name = getattr(active, "Name", None)
        if name and str(name) not in before:
            return str(name)
    raise RuntimeError("Cannot uniquely identify the new native sketch feature")


def _sketch_status(sketch: Any) -> dict[str, Any]:
    code = int(_com_get(sketch, "GetConstrainedStatus"))
    return {
        "constrained_status_code": code,
        "constrained_status": CONSTRAINT_STATES.get(code, "unrecognized"),
        "fully_defined": code == FULLY_CONSTRAINED,
    }


def _segment_by_axis(sketch: Any, axis: str) -> tuple[Any, float, float]:
    """Choose an outer H/V line from a single rectangular profile."""
    candidates: list[tuple[float, float, Any, float, float]] = []
    for seg in _com_get(sketch, "GetSketchSegments") or ():
        try:
            start = _com_get(seg, "GetStartPoint2")
            end = _com_get(seg, "GetEndPoint2")
            dx, dy = float(end.X - start.X), float(end.Y - start.Y)
        except Exception:  # circle/arc/construction entity, not a line
            continue
        if axis == "horizontal" and abs(dy) < 1e-7 and abs(dx) > 1e-7:
            candidates.append((abs(dx), (start.Y + end.Y) / 2, seg,
                               (start.X + end.X) / 2, (start.Y + end.Y) / 2))
        elif axis == "vertical" and abs(dx) < 1e-7 and abs(dy) > 1e-7:
            candidates.append((abs(dy), (start.X + end.X) / 2, seg,
                               (start.X + end.X) / 2, (start.Y + end.Y) / 2))
    if not candidates:
        raise RuntimeError(f"No {axis} sketch line found")
    length = max(row[0] for row in candidates)
    edges = [row for row in candidates if abs(row[0] - length) < 1e-8]
    # Prefer top/right edge so labels do not overlap the origin.
    _, _, seg, x, y = max(edges, key=lambda item: item[1])
    return seg, x, y


def _segment_by_axis_length(sketch: Any, axis: str, length_mm: float) -> tuple[Any, float, float]:
    """Choose an H/V line whose current length matches the requested size."""
    target = _mm(length_mm)
    candidates: list[tuple[float, Any, float, float]] = []
    for seg in _com_get(sketch, "GetSketchSegments") or ():
        try:
            start = _com_get(seg, "GetStartPoint2")
            end = _com_get(seg, "GetEndPoint2")
            dx, dy = float(end.X - start.X), float(end.Y - start.Y)
        except Exception:
            continue
        if axis == "horizontal" and abs(dy) < 1e-7 and abs(abs(dx) - target) < 1e-7:
            candidates.append(((start.Y + end.Y) / 2, seg,
                               (start.X + end.X) / 2, (start.Y + end.Y) / 2))
        elif axis == "vertical" and abs(dx) < 1e-7 and abs(abs(dy) - target) < 1e-7:
            candidates.append(((start.X + end.X) / 2, seg,
                               (start.X + end.X) / 2, (start.Y + end.Y) / 2))
    if not candidates:
        raise RuntimeError(f"No {axis} sketch line of length {length_mm:g} mm found")
    _, seg, x, y = max(candidates, key=lambda item: item[0])
    return seg, x, y


def _point_xy_mm(point: Any) -> list[float]:
    return [round(float(point.X) * 1000.0, 9), round(float(point.Y) * 1000.0, 9)]


def _sketch_geometry(sketch: Any) -> list[dict[str, Any]]:
    """Read actual sketch segments without relying on cached request values."""
    rows: list[dict[str, Any]] = []
    type_names = {0: "line", 1: "arc_or_circle", 2: "ellipse", 3: "spline"}
    for index, segment in enumerate(_com_get(sketch, "GetSketchSegments") or ()):
        try:
            type_code = int(_com_get(segment, "GetType"))
        except Exception:
            type_code = -1
        row: dict[str, Any] = {
            "index": index,
            "type_code": type_code,
            "type": type_names.get(type_code, "other"),
            "construction": bool(getattr(segment, "ConstructionGeometry", False)),
        }
        try:
            row["start_mm"] = _point_xy_mm(_com_get(segment, "GetStartPoint2"))
            row["end_mm"] = _point_xy_mm(_com_get(segment, "GetEndPoint2"))
        except Exception:
            pass
        try:
            row["center_mm"] = _point_xy_mm(_com_get(segment, "GetCenterPoint2"))
        except Exception:
            pass
        try:
            row["radius_mm"] = round(float(_com_get(segment, "GetRadius")) * 1000.0, 9)
        except Exception:
            pass
        rows.append(row)
    return rows


def _add_line_dimension(sw: Any, model: Any, sketch: Any, axis: str,
                        value_mm: float) -> str:
    """Add and verify one driving line-length dimension."""
    seg, x, y = _segment_by_axis_length(sketch, axis, value_mm)
    model.ClearSelection2(True)
    if not seg.Select4(False, _empty_dispatch()):
        raise RuntimeError("Could not select target sketch segment")
    offset = 0.012 if axis == "horizontal" else 0.016
    with _no_dimension_popup(sw):
        display = model.AddDimension2(x + (offset if axis == "vertical" else 0),
                                      y + (offset if axis == "horizontal" else 0), 0.0)
    if display is None:
        raise RuntimeError("AddDimension2 returned no dimension")
    dim = display.GetDimension2(0)
    if dim is None or int(dim.DrivenState) != 2:
        raise RuntimeError("Rectangle-pair dimension is not driving")
    dim.SystemValue = _mm(value_mm)
    actual = float(dim.SystemValue) * 1000.0
    if abs(actual - value_mm) > 1e-3:
        raise RuntimeError(f"Dimension readback mismatch: {actual:.6g} mm")
    model.ClearSelection2(True)
    return str(dim.FullName)


class NativeParametric:
    def __init__(self, connect: Callable[[], tuple[Any, Any]], part_ops: Callable[[], Any]):
        self.connect = connect
        self.part_ops = part_ops
        self.session: SketchSession | None = None

    def _part(self) -> Any:
        _, model = self.connect()
        if model is None or int(_com_get(model, "GetType")) != 1:  # swDocPART
            raise RuntimeError("A native SolidWorks Part must be active")
        return model

    def _bound(self, token: str, *, require_open: bool | None = None) -> Any:
        if self.session is None or token != self.session.token:
            raise RuntimeError("No matching native sketch session. Start a sketch first")
        model = self._part()
        if _doc_id(model) != (self.session.title, self.session.path):
            raise RuntimeError("Active document changed; refusing to edit another part")
        active = model.SketchManager.ActiveSketch
        if require_open is True and (not self.session.open or active is None):
            raise RuntimeError("Session sketch is not currently being edited")
        if require_open is False and active is not None:
            raise RuntimeError("Finish the active sketch before extruding")
        return model

    def begin(self, expected_document_title: str, plane_name: str) -> dict:
        model = self._part()
        title, path = _doc_id(model)
        if expected_document_title != title:
            raise RuntimeError(f"Active Part is {title!r}, not {expected_document_title!r}")
        if model.SketchManager.ActiveSketch is not None:
            raise RuntimeError("A sketch is already active; exit it manually first")
        if self.session is not None and self.session.open:
            raise RuntimeError("Previous sketch session remains open")
        before = {str(feat.Name) for feat, _ in _feature_rows(model)}
        normalized_plane = str(plane_name).strip().lower()
        face_based = normalized_plane in {
            "largest_planar_face", "largest outer planar face", "最大外侧平面", "最大平面"
        }
        if face_based:
            self.part_ops().start_sketch_on_largest_planar_face(model)
        else:
            self.part_ops().start_sketch(model, plane_name)
        if model.SketchManager.ActiveSketch is None:
            raise RuntimeError("SolidWorks did not enter sketch edit mode")
        name = _sketch_name(model, before)
        self.session = SketchSession(
            secrets.token_urlsafe(16), title, path, name,
            reverse_boss_direction=face_based,
        )
        return {"status": "ok", "document": title, "sketch": name,
                "session_id": self.session.token, "editing": True}

    def offset_plane(self, expected_document_title: str, base_plane_name: str,
                     offset_mm: float, reverse_direction: bool = False) -> dict:
        model = self._part()
        title, _ = _doc_id(model)
        if expected_document_title != title:
            raise RuntimeError(f"Active Part is {title!r}, not {expected_document_title!r}")
        if model.SketchManager.ActiveSketch is not None:
            raise RuntimeError("Finish the active sketch before creating a reference plane")
        created = self.part_ops().offset_plane(
            model, base_plane_name, _mm(offset_mm), bool(reverse_direction)
        )
        if created is None:
            raise RuntimeError("Native SolidWorks offset plane returned None")
        error = int(_com_get(created, "GetErrorCode"))
        if error != 0:
            raise RuntimeError(f"Created reference plane has SolidWorks error code {error}")
        rebuilt = bool(model.ForceRebuild3(False))
        if not rebuilt:
            raise RuntimeError("Reference plane created, but model rebuild failed")
        definition = _com_get(created, "GetDefinition")
        if definition is None:
            raise RuntimeError("Cannot read native reference plane definition")
        actual_mm = abs(float(getattr(definition, "Distance"))) * 1000.0
        reverse_actual = bool(getattr(definition, "ReverseDirection"))
        if abs(actual_mm - offset_mm) > 1e-5:
            raise RuntimeError(
                f"Reference plane offset readback mismatch: requested {offset_mm}, got {actual_mm} mm"
            )
        return {
            "status": "ok", "feature": str(created.Name),
            "feature_type": str(_com_get(created, "GetTypeName2")),
            "base_plane": base_plane_name, "offset_mm": actual_mm,
            "reverse_direction": reverse_actual, "rebuild_ok": rebuilt,
        }

    def rectangle(self, token: str, width_mm: float, height_mm: float) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        if _com_get(sketch, "GetSketchSegments"):
            raise RuntimeError("Rectangle tool requires an empty sketch")
        result = model.SketchManager.CreateCenterRectangle(
            0.0, 0.0, 0.0, _mm(width_mm) / 2, _mm(height_mm) / 2, 0.0
        )
        if not result:
            raise RuntimeError("CreateCenterRectangle returned no segments")
        return {"status": "ok", "sketch": self.session.sketch_name,
                "center_mm": [0.0, 0.0], "width_mm": width_mm,
                "height_mm": height_mm, "constraint": _sketch_status(sketch)}

    def rectangle_pair(self, token: str, outer_width_mm: float, outer_height_mm: float,
                       inner_width_mm: float, inner_height_mm: float) -> dict:
        """Create two concentric native rectangles for an annular cut profile."""
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        if _com_get(sketch, "GetSketchSegments"):
            raise RuntimeError("Rectangle-pair tool requires an empty sketch")
        for name, value in (
            ("outer_width_mm", outer_width_mm),
            ("outer_height_mm", outer_height_mm),
            ("inner_width_mm", inner_width_mm),
            ("inner_height_mm", inner_height_mm),
        ):
            _mm(value)
        if inner_width_mm >= outer_width_mm or inner_height_mm >= outer_height_mm:
            raise ValueError("Inner rectangle must be smaller than the outer rectangle")
        sketch_manager = model.SketchManager
        previous_add_to_db = bool(sketch_manager.AddToDB)
        try:
            # Bypass interactive inference while placing exact unequal sizes.
            # Native driving dimensions and relations are added immediately
            # afterwards, so the final sketch remains parametric.
            sketch_manager.AddToDB = True
            def create_lines(width_mm: float, height_mm: float) -> list[Any]:
                half_width = _mm(width_mm) / 2
                half_height = _mm(height_mm) / 2
                corners = [
                    (-half_width, -half_height),
                    (half_width, -half_height),
                    (half_width, half_height),
                    (-half_width, half_height),
                ]
                return [
                    sketch_manager.CreateLine(
                        corners[index][0], corners[index][1], 0.0,
                        corners[(index + 1) % 4][0], corners[(index + 1) % 4][1], 0.0,
                    )
                    for index in range(4)
                ]

            outer = create_lines(outer_width_mm, outer_height_mm)
            inner = create_lines(inner_width_mm, inner_height_mm)
        finally:
            sketch_manager.AddToDB = previous_add_to_db
        if not outer or not inner:
            raise RuntimeError("CreateCenterRectangle returned no segments for the pair")
        sw, _ = self.connect()
        # Protect both profiles from FullyDefineSketch changing their sizes.
        driving_dimensions = [
            _add_line_dimension(sw, model, sketch, "horizontal", outer_width_mm),
            _add_line_dimension(sw, model, sketch, "vertical", outer_height_mm),
            _add_line_dimension(sw, model, sketch, "horizontal", inner_width_mm),
            _add_line_dimension(sw, model, sketch, "vertical", inner_height_mm),
        ]
        return {
            "status": "ok",
            "sketch": self.session.sketch_name,
            "center_mm": [0.0, 0.0],
            "outer_mm": [outer_width_mm, outer_height_mm],
            "inner_mm": [inner_width_mm, inner_height_mm],
            "driving_dimensions": driving_dimensions,
            "constraint": _sketch_status(sketch),
        }

    def line(self, token: str, start_x_mm: float, start_y_mm: float,
             end_x_mm: float, end_y_mm: float, construction: bool = False) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        values = [start_x_mm, start_y_mm, end_x_mm, end_y_mm]
        x1, y1, x2, y2 = (_coord_mm(value) for value in values)
        if math.hypot(x2 - x1, y2 - y1) < 1e-9:
            raise ValueError("Line start and end points must differ")
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = model.SketchManager.CreateLine(x1, y1, 0.0, x2, y2, 0.0)
        if created is None:
            raise RuntimeError("CreateLine returned None")
        created.ConstructionGeometry = bool(construction)
        geometry = _sketch_geometry(sketch)
        created_rows = geometry[before:]
        if not created_rows or created_rows[-1]["construction"] != bool(construction):
            raise RuntimeError("Construction-geometry state did not match the requested value")
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "line", "start_mm": values[:2], "end_mm": values[2:],
                "construction": bool(construction), "created_segments": created_rows,
                "constraint": _sketch_status(sketch)}

    def corner_rectangle(self, token: str, x1_mm: float, y1_mm: float,
                         x2_mm: float, y2_mm: float) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        x1, y1, x2, y2 = (_coord_mm(value) for value in (x1_mm, y1_mm, x2_mm, y2_mm))
        if abs(x2 - x1) < 1e-9 or abs(y2 - y1) < 1e-9:
            raise ValueError("Corner rectangle requires nonzero width and height")
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = model.SketchManager.CreateCornerRectangle(x1, y1, 0.0, x2, y2, 0.0)
        if not created:
            raise RuntimeError("CreateCornerRectangle returned no segments")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "corner_rectangle", "corner1_mm": [x1_mm, y1_mm],
                "corner2_mm": [x2_mm, y2_mm], "created_segments": geometry[before:],
                "constraint": _sketch_status(sketch)}

    def circle(self, token: str, center_x_mm: float, center_y_mm: float,
               radius_mm: float) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        cx, cy, radius = _coord_mm(center_x_mm), _coord_mm(center_y_mm), _mm(radius_mm)
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = model.SketchManager.CreateCircleByRadius(cx, cy, 0.0, radius)
        if created is None:
            raise RuntimeError("CreateCircleByRadius returned None")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "circle", "center_mm": [center_x_mm, center_y_mm],
                "radius_mm": radius_mm, "created_segments": geometry[before:],
                "constraint": _sketch_status(sketch)}

    def arc(self, token: str, center_x_mm: float, center_y_mm: float,
            start_x_mm: float, start_y_mm: float, end_x_mm: float,
            end_y_mm: float, clockwise: bool = False) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        raw = (center_x_mm, center_y_mm, start_x_mm, start_y_mm, end_x_mm, end_y_mm)
        cx, cy, sx, sy, ex, ey = (_coord_mm(value) for value in raw)
        start_radius = math.hypot(sx - cx, sy - cy)
        end_radius = math.hypot(ex - cx, ey - cy)
        if start_radius < 1e-9 or abs(start_radius - end_radius) > 1e-6:
            raise ValueError("Arc start and end must lie on the same nonzero-radius circle")
        if math.hypot(ex - sx, ey - sy) < 1e-9:
            raise ValueError("Arc start and end points must differ")
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = model.SketchManager.CreateArc(
                cx, cy, 0.0, sx, sy, 0.0, ex, ey, 0.0, -1 if clockwise else 1
            )
        if created is None:
            raise RuntimeError("CreateArc returned None")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "arc", "center_mm": [center_x_mm, center_y_mm],
                "start_mm": [start_x_mm, start_y_mm], "end_mm": [end_x_mm, end_y_mm],
                "clockwise": clockwise, "radius_mm": start_radius * 1000.0,
                "created_segments": geometry[before:], "constraint": _sketch_status(sketch)}

    def polygon(self, token: str, center_x_mm: float, center_y_mm: float,
                radius_mm: float, sides: int) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        if sides < 3 or sides > 64:
            raise ValueError("Polygon sides must be in [3, 64]")
        cx, cy, radius = _coord_mm(center_x_mm), _coord_mm(center_y_mm), _mm(radius_mm)
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = model.SketchManager.CreatePolygon(
                cx, cy, 0.0, cx + radius, cy, 0.0, sides, True
            )
        if not created:
            raise RuntimeError("CreatePolygon returned no segments")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "polygon", "center_mm": [center_x_mm, center_y_mm],
                "radius_mm": radius_mm, "sides": sides,
                "created_segments": geometry[before:], "constraint": _sketch_status(sketch)}

    def straight_slot(self, token: str, start_x_mm: float, start_y_mm: float,
                      end_x_mm: float, end_y_mm: float, width_mm: float) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        x1, y1, x2, y2 = (_coord_mm(value) for value in
                           (start_x_mm, start_y_mm, end_x_mm, end_y_mm))
        width = _mm(width_mm)
        if math.hypot(x2 - x1, y2 - y1) < 1e-9:
            raise ValueError("Slot axis start and end points must differ")
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = self.part_ops().sketch_slot(model, x1, y1, x2, y2, width / 2.0)
        if not created:
            raise RuntimeError("CreateSketchSlot returned no segments")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "straight_slot", "axis_start_mm": [start_x_mm, start_y_mm],
                "axis_end_mm": [end_x_mm, end_y_mm], "width_mm": width_mm,
                "end_radius_mm": width_mm / 2.0,
                "created_segments": geometry[before:], "constraint": _sketch_status(sketch)}

    def spline(self, token: str, points_mm: list[tuple[float, float]]) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        if len(points_mm) < 3 or len(points_mm) > 100:
            raise ValueError("Spline requires 3 to 100 points")
        points_m = [(_coord_mm(float(x)), _coord_mm(float(y))) for x, y in points_mm]
        if any(math.hypot(points_m[index][0] - points_m[index - 1][0],
                          points_m[index][1] - points_m[index - 1][1]) < 1e-9
               for index in range(1, len(points_m))):
            raise ValueError("Consecutive spline points must differ")
        before = len(_sketch_geometry(sketch))
        with _exact_sketch_creation(model.SketchManager):
            created = self.part_ops().sketch_spline(model, points_m)
        if created is None:
            raise RuntimeError("CreateSpline2 returned None")
        geometry = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "entity": "spline", "points_mm": [[x, y] for x, y in points_mm],
                "created_segments": geometry[before:], "constraint": _sketch_status(sketch)}

    def geometry(self, token: str) -> dict:
        model = self._bound(token)
        if self.session.open:
            sketch = model.SketchManager.ActiveSketch
        else:
            sketch = _com_get(_find_feature(model, self.session.sketch_name),
                              "GetSpecificFeature2")
        if sketch is None:
            raise RuntimeError("Sketch feature has no native ISketch object")
        segments = _sketch_geometry(sketch)
        return {"status": "ok", "sketch": self.session.sketch_name,
                "editing": self.session.open, "segment_count": len(segments),
                "segments": segments, "constraint": _sketch_status(sketch)}

    def dimension(self, token: str, axis: str, value_mm: float) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        seg, x, y = _segment_by_axis(sketch, axis)
        model.ClearSelection2(True)
        if not seg.Select4(False, _empty_dispatch()):
            raise RuntimeError("Could not select target sketch segment")
        offset = 0.012 if axis == "horizontal" else 0.016
        sw, _ = self.connect()
        with _no_dimension_popup(sw):
            display = model.AddDimension2(x + (offset if axis == "vertical" else 0),
                                          y + (offset if axis == "horizontal" else 0), 0.0)
        if display is None:
            raise RuntimeError("AddDimension2 returned no dimension")
        dim = display.GetDimension2(0)
        if dim is None:
            raise RuntimeError("No model dimension behind display dimension")
        if int(dim.DrivenState) != 2:  # swDimensionDriving
            raise RuntimeError("Dimension is reference/driven, not a driving dimension")
        dim.SystemValue = _mm(value_mm)
        actual = float(dim.SystemValue) * 1000
        if abs(actual - value_mm) > 1e-3:
            raise RuntimeError(f"Dimension readback mismatch: {actual:.6g} mm")
        model.ClearSelection2(True)
        return {"status": "ok", "dimension": str(dim.FullName),
                "axis": axis, "value_mm": actual, "driving": True,
                "constraint": _sketch_status(sketch)}

    def relation(self, token: str, axis: str) -> dict:
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        seg, _, _ = _segment_by_axis(sketch, axis)
        model.ClearSelection2(True)
        if not seg.Select4(False, _empty_dispatch()):
            raise RuntimeError("Could not select sketch line")
        model.SketchAddConstraints("sgHORIZONTAL2D" if axis == "horizontal" else "sgVERTICAL2D")
        model.ClearSelection2(True)
        status = _sketch_status(sketch)
        if status["constrained_status_code"] in (4, 5, 6):
            raise RuntimeError("New relation invalid/over-constrained; inspect sketch before continuing")
        return {"status": "ok", "relation": axis, "constraint": status}

    def auto_define(self, token: str) -> dict:
        """Use relationships + driving baseline dimensions, never sgFIXED."""
        model = self._bound(token, require_open=True)
        sketch = model.SketchManager.ActiveSketch
        before = _sketch_status(sketch)
        if before["fully_defined"]:
            return {"status": "ok", "changed": False, "constraint": before}
        model.ClearSelection2(True)
        # Official VBA example selects the origin as both dimension datums.
        picked = False
        # Prefer the stable English selection path, then localized and
        # coordinate-only fallbacks for Chinese installations.
        for origin_name in ("Point1@Origin", "点1@原点", ""):
            picked = bool(model.Extension.SelectByID2(
                origin_name, "EXTSKETCHPOINT", 0, 0, 0, False, 2 | 4,
                _empty_dispatch(), 0
            ))
            if picked:
                break
        if not picked:
            raise RuntimeError("Cannot select origin as dimension datum; no auto-definition attempted")
        sw, _ = self.connect()
        with _no_dimension_popup(sw):
            model.SketchManager.FullyDefineSketch(
                True, True, 2 | 4 | 512, True, 1, _empty_dispatch(),
                1, _empty_dispatch(), 1, 1
            )
        model.ClearSelection2(True)
        after = _sketch_status(sketch)
        if not after["fully_defined"]:
            raise RuntimeError(f"FullyDefineSketch did not fully define the sketch: {after}")
        return {"status": "ok", "changed": True, "constraint": after,
                "note": "Auto-added relations/dimensions require design-intent review"}

    def status(self, token: str) -> dict:
        model = self._bound(token)
        if self.session.open:
            sketch = model.SketchManager.ActiveSketch
            if sketch is None:
                raise RuntimeError("Session says open but no active sketch found")
        else:
            sketch = _com_get(_find_feature(model, self.session.sketch_name),
                              "GetSpecificFeature2")
        if sketch is None:
            raise RuntimeError("Sketch feature has no native ISketch object")
        return {"status": "ok", "sketch": self.session.sketch_name,
                "editing": self.session.open, **_sketch_status(sketch)}

    def finish(self, token: str, require_fully_defined: bool = True) -> dict:
        model = self._bound(token, require_open=True)
        info = _sketch_status(model.SketchManager.ActiveSketch)
        if require_fully_defined and not info["fully_defined"]:
            raise RuntimeError(f"Sketch not fully defined: {info}")
        self.part_ops().end_sketch(model)
        if model.SketchManager.ActiveSketch is not None:
            raise RuntimeError("SolidWorks did not exit sketch editing")
        self.session.open = False
        return {"status": "ok", "sketch": self.session.sketch_name,
                "editing": False, **info}

    def sketch_plane(self, token: str) -> dict:
        """Read the sketch plane equation in model coordinates."""
        model = self._bound(token)
        sketch = (model.SketchManager.ActiveSketch if self.session.open else
                  _com_get(_find_feature(model, self.session.sketch_name), "GetSpecificFeature2"))
        if sketch is None:
            raise RuntimeError("Session has no native sketch")
        transform = _com_get(_com_get(sketch, "ModelToSketchTransform"), "ArrayData")
        return {"status": "ok", "sketch": self.session.sketch_name,
                "normal_xyz": [float(transform[i]) for i in (2, 5, 8)],
                "offset_mm": -1000.0 * float(transform[11])}

    def extrude(self, token: str, depth_mm: float, cut: bool = False,
                draft_angle_deg: float = 0.0, draft_outward: bool = True,
                *, cut_direction: str | None = None) -> dict:
        """Extrude a sketch. A zero cut depth creates a through-all cut."""
        if cut_direction is not None and (
            not cut or cut_direction not in ("along_normal", "against_normal")
        ):
            raise ValueError("cut_direction requires cut=true and along_normal or against_normal")
        reverse_cut = None
        model = self._bound(token, require_open=False)
        feature = _find_feature(model, self.session.sketch_name)
        sketch = _com_get(feature, "GetSpecificFeature2")
        if sketch is None or not _sketch_status(sketch)["fully_defined"]:
            raise RuntimeError("Refusing extrusion: sketch is not verifiably fully defined")
        # Object-level selection is locale-independent (Sketch1 / 草图1).
        model.ClearSelection2(True)
        if not feature.Select2(False, 0):
            raise RuntimeError("Could not select native sketch feature object")
        ops = self.part_ops()
        if cut:
            if abs(float(draft_angle_deg)) > 1e-12:
                raise ValueError("Draft angle is currently supported for boss extrusions only")
            reverse_cut = (not self.session.reverse_boss_direction if cut_direction is None
                           else cut_direction == "along_normal")
            if depth_mm == 0:
                created = ops.extrude_cut_through_all(
                    model, self.session.sketch_name, reverse_direction=reverse_cut,
                )
            else:
                created = ops.extrude_cut(
                    model, self.session.sketch_name, _mm(depth_mm), reverse_direction=reverse_cut,
                )
        else:
            angle = float(draft_angle_deg)
            if not math.isfinite(angle) or angle < 0.0 or angle >= 89.0:
                raise ValueError("draft_angle_deg must be in [0, 89)")
            created = ops.extrude_boss(
                model, self.session.sketch_name, _mm(depth_mm),
                direction=self.session.reverse_boss_direction,
                draft_angle=math.radians(angle),
                draft_outward=bool(draft_outward),
            )
        if created is None:
            if cut:
                plane = self.sketch_plane(token)
                direction = "along_normal" if reverse_cut else "against_normal"
                raise RuntimeError(
                    f"Cut {direction} returned no feature for {self.session.sketch_name!r} "
                    f"(model normal {plane['normal_xyz']}, offset {plane['offset_mm']:g} mm). "
                    "Check that the selected direction and depth intersect the solid."
                )
            raise RuntimeError("Native SolidWorks extrusion returned None")
        # GetErrorCode2 requires an IsWarning out parameter in SW2025;
        # GetErrorCode returns the same feature error code without by-ref args.
        error = int(_com_get(created, "GetErrorCode"))
        if error != 0:
            raise RuntimeError(f"Created feature has SolidWorks error code {error}")
        rebuilt = bool(model.ForceRebuild3(False))
        if not rebuilt:
            raise RuntimeError("Feature created, but model rebuild failed")
        result = {"status": "ok", "feature": str(created.Name),
                "feature_type": str(_com_get(created, "GetTypeName2")),
                "sketch": self.session.sketch_name, "depth_mm": depth_mm,
                "cut": cut, "draft_angle_deg": float(draft_angle_deg),
                "draft_outward": bool(draft_outward), "rebuild_ok": rebuilt,
                "solid_body_count": self.body_count(model)}
        if cut:
            result["cut_direction"] = "along_normal" if reverse_cut else "against_normal"
            result["through_all"] = depth_mm == 0
        return result

    def revolve(self, token: str, angle_deg: float = 360.0, cut: bool = False,
                reverse_direction: bool = False, merge: bool = True) -> dict:
        model = self._bound(token, require_open=False)
        feature = _find_feature(model, self.session.sketch_name)
        sketch = _com_get(feature, "GetSpecificFeature2")
        if sketch is None or not _sketch_status(sketch)["fully_defined"]:
            raise RuntimeError("Refusing revolve: sketch is not verifiably fully defined")
        angle = float(angle_deg)
        if not math.isfinite(angle) or angle <= 0.0 or angle > 360.0:
            raise ValueError("angle_deg must be in (0, 360]")
        geometry = _sketch_geometry(sketch)
        axes = [row for row in geometry
                if row["type"] == "line" and row["construction"]]
        if len(axes) != 1:
            raise RuntimeError(
                f"Revolve sketch requires exactly one construction-line axis; found {len(axes)}"
            )
        if not any(not row["construction"] for row in geometry):
            raise RuntimeError("Revolve sketch has no non-construction profile geometry")
        model.ClearSelection2(True)
        if not feature.Select2(False, 0):
            raise RuntimeError("Could not select native revolve sketch feature object")
        created = self.part_ops().revolve_feature(
            model, self.session.sketch_name, math.radians(angle),
            cut=bool(cut), reverse_direction=bool(reverse_direction), merge=bool(merge),
        )
        if created is None:
            raise RuntimeError("Native SolidWorks revolve returned None")
        error = int(_com_get(created, "GetErrorCode"))
        if error != 0:
            raise RuntimeError(f"Created revolve has SolidWorks error code {error}")
        rebuilt = bool(model.ForceRebuild3(False))
        if not rebuilt:
            raise RuntimeError("Revolve created, but model rebuild failed")
        definition = _com_get(created, "GetDefinition")
        if definition is None:
            raise RuntimeError("Cannot read native revolve definition")
        forward_angle = math.degrees(float(definition.GetRevolutionAngle(True)))
        reverse_actual = bool(getattr(definition, "ReverseDirection"))
        boss_actual = bool(_com_get(definition, "IsBossFeature"))
        if abs(forward_angle - angle) > 1e-5:
            raise RuntimeError(
                f"Revolve angle readback mismatch: requested {angle:.9g}, got {forward_angle:.9g} deg"
            )
        if boss_actual == bool(cut):
            raise RuntimeError("Revolve boss/cut readback does not match the request")
        return {
            "status": "ok", "feature": str(created.Name),
            "feature_type": str(_com_get(created, "GetTypeName2")),
            "sketch": self.session.sketch_name, "angle_deg": forward_angle,
            "cut": not boss_actual, "reverse_direction": reverse_actual,
            "merge": bool(merge), "axis": axes[0], "rebuild_ok": rebuilt,
            "solid_body_count": self.body_count(model),
        }

    def sweep(self, token: str, profile_sketch_name: str, cut: bool = False,
              merge: bool = True) -> dict:
        model = self._bound(token, require_open=False)
        path_name = self.session.sketch_name
        if profile_sketch_name == path_name:
            raise ValueError("Sweep profile and path must be different sketches")
        profile_feature = _find_feature(model, profile_sketch_name)
        path_feature = _find_feature(model, path_name)
        profile = _com_get(profile_feature, "GetSpecificFeature2")
        path = _com_get(path_feature, "GetSpecificFeature2")
        if profile is None or not _sketch_status(profile)["fully_defined"]:
            raise RuntimeError("Refusing sweep: profile sketch is not verifiably fully defined")
        if path is None or not _sketch_status(path)["fully_defined"]:
            raise RuntimeError("Refusing sweep: path sketch is not verifiably fully defined")
        profile_geometry = _sketch_geometry(profile)
        path_geometry = _sketch_geometry(path)
        if not profile_geometry:
            raise RuntimeError("Sweep profile sketch has no geometry")
        if not any(not row["construction"] for row in path_geometry):
            raise RuntimeError("Sweep path sketch has no non-construction geometry")
        created = self.part_ops().sweep_feature(
            model, profile_sketch_name, path_name,
            cut=bool(cut), merge=bool(merge),
        )
        if created is None:
            raise RuntimeError("Native SolidWorks sweep returned None")
        error = int(_com_get(created, "GetErrorCode"))
        if error != 0:
            raise RuntimeError(f"Created sweep has SolidWorks error code {error}")
        rebuilt = bool(model.ForceRebuild3(False))
        if not rebuilt:
            raise RuntimeError("Sweep created, but model rebuild failed")
        definition = _com_get(created, "GetDefinition")
        if definition is None:
            raise RuntimeError("Cannot read native sweep definition")
        boss_actual = bool(_com_get(definition, "IsBossFeature"))
        if boss_actual == bool(cut):
            raise RuntimeError("Sweep boss/cut readback does not match the request")
        return {
            "status": "ok", "feature": str(created.Name),
            "feature_type": str(_com_get(created, "GetTypeName2")),
            "profile_sketch": profile_sketch_name, "path_sketch": path_name,
            "profile_type_code": int(_com_get(definition, "GetProfileType")),
            "path_type_code": int(_com_get(definition, "GetPathType")),
            "twist_control_type": int(getattr(definition, "TwistControlType")),
            "cut": not boss_actual, "merge": bool(getattr(definition, "Merge", merge)),
            "profile_segment_count": len(profile_geometry),
            "path_segment_count": len(path_geometry),
            "rebuild_ok": rebuilt, "solid_body_count": self.body_count(model),
        }

    def loft(self, token: str, section_sketch_names: list[str],
             cut: bool = False, merge: bool = True) -> dict:
        model = self._bound(token, require_open=False)
        names = [str(name) for name in section_sketch_names]
        if len(names) < 2 or len(names) > 16:
            raise ValueError("Loft requires 2 to 16 section sketches")
        if len(set(names)) != len(names):
            raise ValueError("Loft section sketches must be unique and ordered")
        if self.session.sketch_name not in names:
            raise RuntimeError("Current session sketch must be one of the loft sections")
        segment_counts = []
        for name in names:
            feature = _find_feature(model, name)
            sketch = _com_get(feature, "GetSpecificFeature2")
            if sketch is None or not _sketch_status(sketch)["fully_defined"]:
                raise RuntimeError(f"Refusing loft: section {name!r} is not verifiably fully defined")
            geometry = _sketch_geometry(sketch)
            if not any(not row["construction"] for row in geometry):
                raise RuntimeError(f"Loft section {name!r} has no profile geometry")
            segment_counts.append(len(geometry))
        created = self.part_ops().loft_feature(
            model, names, cut=bool(cut), merge=bool(merge)
        )
        if created is None:
            raise RuntimeError("Native SolidWorks loft returned None")
        error = int(_com_get(created, "GetErrorCode"))
        if error != 0:
            raise RuntimeError(f"Created loft has SolidWorks error code {error}")
        rebuilt = bool(model.ForceRebuild3(False))
        if not rebuilt:
            raise RuntimeError("Loft created, but model rebuild failed")
        definition = _com_get(created, "GetDefinition")
        if definition is None:
            raise RuntimeError("Cannot read native loft definition")
        count_actual = int(_com_get(definition, "GetProfileCount"))
        boss_actual = bool(_com_get(definition, "IsBossFeature"))
        if count_actual != len(names):
            raise RuntimeError(
                f"Loft profile-count readback mismatch: requested {len(names)}, got {count_actual}"
            )
        if boss_actual == bool(cut):
            raise RuntimeError("Loft boss/cut readback does not match the request")
        return {
            "status": "ok", "feature": str(created.Name),
            "feature_type": str(_com_get(created, "GetTypeName2")),
            "section_sketches": names, "section_segment_counts": segment_counts,
            "profile_count": count_actual, "cut": not boss_actual,
            "closed": bool(getattr(definition, "Close")),
            "maintain_tangency": bool(getattr(definition, "MaintainTangency")),
            "merge": bool(getattr(definition, "Merge", merge)),
            "rebuild_ok": rebuilt, "solid_body_count": self.body_count(model),
        }

    @staticmethod
    def body_count(model: Any) -> int:
        bodies = model.GetBodies2(0, False) or ()  # swSolidBody == 0
        return len(bodies)

    def model_state(self, token: str | None = None) -> dict:
        model = self._bound(token) if token else self._part()
        rows = _feature_rows(model)
        feature_list = []
        for feat, level in rows:
            type_name = str(_com_get(feat, "GetTypeName2"))
            try:
                error_code = int(_com_get(feat, "GetErrorCode"))
            except Exception:
                error_code = None
            info = {"name": str(feat.Name), "type": type_name,
                    "level": level, "error_code": error_code}
            if type_name == "ProfileFeature":
                try:
                    sketch = _com_get(feat, "GetSpecificFeature2")
                    info["constraint"] = _sketch_status(sketch)
                except Exception as exc:
                    info["constraint_error"] = str(exc)
            feature_list.append(info)
        return {"status": "ok", "document": _doc_id(model)[0],
                "path": _doc_id(model)[1], "solid_body_count": self.body_count(model),
                "features": feature_list}
