"""
SolidWorks 零件建模工具
提供草图绘制和特征创建的常用函数
"""
from dataclasses import dataclass
from contextlib import contextmanager
import math
import os
import time

try:
    from .sw_connect import get_com_member
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member
    from sw_preflight import import_com_dependencies

pythoncom, _win32com, VARIANT = import_com_dependencies()

PLANE_NAME_ALIASES = {
    "Front Plane": ["Front Plane", "前视基准面"],
    "Top Plane": ["Top Plane", "上视基准面"],
    "Right Plane": ["Right Plane", "右视基准面"],
    "前视基准面": ["前视基准面", "Front Plane"],
    "上视基准面": ["上视基准面", "Top Plane"],
    "右视基准面": ["右视基准面", "Right Plane"],
}

SKETCH_NAME_PREFIX_ALIASES = {
    "Sketch": "草图",
    "草图": "Sketch",
}


@dataclass
class SketchSelectionRef:
    """
    记录草图对象引用，避免后续只能靠 SelectByID2("SKETCH") 按名称反查。

    SolidWorks 2024 中文版中，按名称选择 SKETCH 可能持续返回 False。创建草图时
    保存对象引用，后续特征创建可直接 Select2 草图、草图特征或轮廓。
    """

    name: str
    sketch: object = None
    feature: object = None
    contours: tuple = ()
    regions: tuple = ()
    segments: tuple = ()
    source: str = ""

    def __str__(self):
        """保持与旧代码中普通草图名称字符串相近的表现。"""
        return self.name


_SKETCH_SELECTION_CACHE = {}


# ============================================================
# 草图操作
# ============================================================

def _empty_callout():
    """创建兼容 SelectByID2 的空 Callout 参数。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _select_by_id(extension, entity_name, entity_type, append=False, mark=0):
    """
    统一封装 SelectByID2，避免 None 在部分 SolidWorks 版本中触发类型不匹配。

    参数:
        extension: ModelDocExtension 对象
        entity_name: 实体名称
        entity_type: 实体类型字符串
        append: 是否追加选择
        mark: 选择标记

    返回:
        bool
    """
    return extension.SelectByID2(
        entity_name, entity_type, 0, 0, 0, append, mark, _empty_callout(), 0
    )


def _get_plane_name_candidates(plane_name):
    """
    获取基准面的候选名称列表

    参数:
        plane_name: 用户提供的基准面名称

    返回:
        list[str]
    """
    return PLANE_NAME_ALIASES.get(plane_name, [plane_name])


def _get_sketch_name_candidates(sketch_name):
    """
    获取草图名称候选列表，自动兼容中英文前缀。

    参数:
        sketch_name: 草图名称

    返回:
        list[str]
    """
    sketch_name = str(sketch_name)
    candidates = [sketch_name]
    for prefix, alias in SKETCH_NAME_PREFIX_ALIASES.items():
        if sketch_name.startswith(prefix):
            alias_name = alias + sketch_name[len(prefix):]
            if alias_name not in candidates:
                candidates.append(alias_name)
    return candidates


def _as_tuple(value):
    """把 COM 返回的单对象、SAFEARRAY 或 None 统一成 tuple。"""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(item for item in value if item is not None)
    if isinstance(value, list):
        return tuple(item for item in value if item is not None)
    return (value,)


def _safe_com_member(obj, attr_name, *args, default=None):
    """读取 COM 成员，失败时返回默认值，避免排障路径再次抛 COM 异常。"""
    if obj is None:
        return default
    try:
        value = get_com_member(obj, attr_name, *args)
        return default if value is None else value
    except Exception:
        return default


def _model_cache_key(model):
    """生成仅用于当前 Python 进程的模型缓存键。"""
    ole_object = getattr(model, "_oleobj_", None)
    if ole_object is not None:
        return id(ole_object)
    return id(model)


def _cache_name_variants(sketch_name):
    """生成草图缓存名称，兼容中英文默认草图名前缀。"""
    variants = []
    for candidate in _get_sketch_name_candidates(sketch_name):
        if candidate not in variants:
            variants.append(candidate)
    return variants


def _cache_sketch_ref(model, sketch_ref):
    """缓存草图对象引用，后续可跳过 SelectByID2("SKETCH")。"""
    if not sketch_ref or not sketch_ref.name:
        return sketch_ref
    model_cache = _SKETCH_SELECTION_CACHE.setdefault(_model_cache_key(model), {})
    for candidate in _cache_name_variants(sketch_ref.name):
        model_cache[candidate] = sketch_ref
    return sketch_ref


def _find_cached_sketch_ref(model, sketch_name):
    """从当前进程缓存中查找草图对象引用。"""
    if isinstance(sketch_name, SketchSelectionRef):
        return sketch_name

    model_cache = _SKETCH_SELECTION_CACHE.get(_model_cache_key(model), {})
    for candidate in _cache_name_variants(sketch_name):
        cached = model_cache.get(candidate)
        if cached:
            return cached
    return None


def _capture_sketch_ref(model, sketch_obj=None, fallback="Sketch1", source=""):
    """从活动草图或给定草图对象中提取可复用的选择引用。"""
    if sketch_obj is None:
        sketch_obj = _safe_com_member(model.SketchManager, "ActiveSketch")
    if sketch_obj is None:
        return None

    sketch_name = _safe_com_member(sketch_obj, "Name", default=fallback) or fallback
    sketch_ref = SketchSelectionRef(
        name=sketch_name,
        sketch=sketch_obj,
        feature=_safe_com_member(sketch_obj, "GetFeature"),
        contours=_as_tuple(_safe_com_member(sketch_obj, "GetSketchContours")),
        regions=_as_tuple(_safe_com_member(sketch_obj, "GetSketchRegions")),
        segments=_as_tuple(_safe_com_member(sketch_obj, "GetSketchSegments")),
        source=source,
    )
    return _cache_sketch_ref(model, sketch_ref)


def _refresh_sketch_ref(sketch_ref):
    """退出草图后再次刷新 Feature/Contour 引用。"""
    if not sketch_ref or sketch_ref.sketch is None:
        return sketch_ref
    feature = _safe_com_member(sketch_ref.sketch, "GetFeature")
    contours = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchContours"))
    regions = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchRegions"))
    segments = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchSegments"))
    if feature is not None:
        sketch_ref.feature = feature
    if contours:
        sketch_ref.contours = contours
    if regions:
        sketch_ref.regions = regions
    if segments:
        sketch_ref.segments = segments
    return sketch_ref


def _select_first_candidate(extension, candidate_names, entity_type, append=False, mark=0):
    """
    按候选名称列表依次尝试选择实体。

    参数:
        extension: ModelDocExtension 对象
        candidate_names: 候选名称列表
        entity_type: 实体类型字符串
        append: 是否追加选择
        mark: 选择标记

    返回:
        str | None
    """
    for candidate_name in candidate_names:
        if _select_by_id(extension, candidate_name, entity_type, append=append, mark=mark):
            return candidate_name
    return None


def _get_selection_count(model):
    """
    获取当前选择集中的对象数量。

    参数:
        model: IModelDoc2 对象

    返回:
        int
    """
    selection_manager = model.SelectionManager
    count_member = getattr(selection_manager, "GetSelectedObjectCount2")
    return count_member(-1) if callable(count_member) else int(count_member)


def _select_com_object(obj, append=False, mark=0):
    """使用对象自身 Select2/Select4 选择，优先避开 SelectByID2 名称解析。"""
    if obj is None:
        return False
    for method_name in ("Select2", "Select", "Select4"):
        method = getattr(obj, method_name, None)
        if not method:
            continue
        try:
            if method_name == "Select2":
                if bool(method(append, mark)):
                    return True
            elif method_name == "Select":
                if bool(method(append, mark)):
                    return True
            elif bool(method(append, _empty_callout())):
                return True
        except Exception:
            continue
    return False


def select_com_object_at(model, obj, point, append=False, mark=0):
    """Select an entity at an explicit model-space point using ISelectData."""
    coordinates = tuple(float(value) for value in point)
    if len(coordinates) != 3 or not all(math.isfinite(value) for value in coordinates):
        raise ValueError("point must contain three finite model-space coordinates")
    select_data = get_com_member(model.SelectionManager, "CreateSelectData")
    select_data.X, select_data.Y, select_data.Z = coordinates
    select_data.Mark = int(mark)
    method = getattr(obj, "Select4", None)
    if method is None or not bool(method(bool(append), select_data)):
        raise RuntimeError("failed to select entity at the requested model-space point")
    return True


def _select_com_object_with_data(
    model, obj, append=False, mark=0, *, select2_with_data=False,
):
    """Select an entity with an explicit ``ISelectData`` role mark.

    Sketch segments and topological entities do not consistently expose a
    mark-aware ``Select2``.  Passing an empty Callout object to ``Select4``
    silently loses the mark, so axis/profile roles must use SelectData. Body2
    is the notable inverse contract: it exposes ``Select2(Append, SelectData)``
    but no Select4, so callers that have established Body2 semantics must opt
    into that typed path with ``select2_with_data=True``.
    """
    if obj is None:
        return False
    select_data = get_com_member(model.SelectionManager, "CreateSelectData")
    select_data.Mark = int(mark)
    method = getattr(obj, "Select4", None)
    if method is not None:
        try:
            if bool(method(bool(append), select_data)):
                return True
        except Exception:
            pass
    method = getattr(obj, "Select2", None)
    if select2_with_data and method is not None:
        try:
            if bool(method(bool(append), select_data)):
                return True
        except Exception:
            pass
    return _select_com_object(obj, append=append, mark=mark)


def _select_any_object(objects, append=False, mark=0):
    """从一组 COM 对象里尽量选择全部对象，至少选中一个即视为成功。"""
    selected_count = 0
    for obj in _as_tuple(objects):
        if _select_com_object(obj, append=(append or selected_count > 0), mark=mark):
            selected_count += 1
    return selected_count > 0


def solid_edges(model):
    """Return all topological edges from every solid body in the active part."""
    edges = []
    for body in _as_tuple(get_com_member(model, "GetBodies2", 0, False)):
        edges.extend(_as_tuple(get_com_member(body, "GetEdges")))
    return tuple(edges)


def edge_geometry(edge):
    """Return a selection-safe geometric summary for a straight, open edge.

    Coordinates and lengths use SolidWorks API units (metres). The direction is
    canonicalized so an edge has the same signature regardless of vertex order.
    """
    start_vertex = get_com_member(edge, "GetStartVertex")
    end_vertex = get_com_member(edge, "GetEndVertex")
    if start_vertex is None or end_vertex is None:
        raise ValueError("edge_geometry only supports open edges with two vertices")
    start = tuple(float(value) for value in get_com_member(start_vertex, "GetPoint")[:3])
    end = tuple(float(value) for value in get_com_member(end_vertex, "GetPoint")[:3])
    delta = tuple(end[index] - start[index] for index in range(3))
    chord = math.dist(start, end)
    if chord <= 0.0:
        raise ValueError("edge has coincident vertices")
    direction = tuple(value / chord for value in delta)
    for value in direction:
        if abs(value) > 1e-12:
            if value < 0.0:
                direction = tuple(-item for item in direction)
            break
    length = _safe_com_member(edge, "GetLength", default=chord)
    return {
        "start": start,
        "end": end,
        "midpoint": tuple((start[index] + end[index]) / 2.0 for index in range(3)),
        "direction": direction,
        "length": float(length),
    }


def _select_boundary_entity(model, entity, *, append=False, mark=0):
    """Select Boundary inputs through the entity-category contract SW expects.

    Direct ``IEdge.Select4`` is reported as ``swSelREFEDGES`` (51), while the
    Boundary API examples require ``SelectByID2(..., "EDGE", ...)`` and
    ``swSelEDGES`` (1).  Resolve true B-Rep edges by semantic midpoint and use
    the documented selection route; non-edge entities retain mark-aware
    object selection and are validated before the dangerous feature call.
    """
    try:
        midpoint = edge_geometry(entity)["midpoint"]
    except Exception:
        return _select_com_object_with_data(
            model, entity, append=append, mark=mark,
        )
    return bool(model.Extension.SelectByID2(
        "", "EDGE", *midpoint, bool(append), int(mark), _empty_callout(), 0,
    ))


def find_solid_edges(model, *, length=None, direction=None, midpoint=None, tolerance=1e-6):
    """Resolve straight solid edges by geometry instead of topology order.

    Any supplied criterion participates in the match. ``direction`` is treated
    as unoriented, so opposite vectors select the same edge set.
    """
    expected_direction = None
    if direction is not None:
        values = tuple(float(value) for value in direction)
        if len(values) != 3:
            raise ValueError("direction must be a non-zero three-component vector")
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude <= 0.0:
            raise ValueError("direction must be a non-zero three-component vector")
        expected_direction = tuple(value / magnitude for value in values)
    expected_midpoint = tuple(float(value) for value in midpoint) if midpoint is not None else None
    if expected_midpoint is not None and len(expected_midpoint) != 3:
        raise ValueError("midpoint must contain three coordinates")

    matches = []
    for edge in solid_edges(model):
        try:
            geometry = edge_geometry(edge)
        except (TypeError, ValueError, RuntimeError):
            continue
        if length is not None and abs(geometry["length"] - float(length)) > tolerance:
            continue
        if expected_midpoint is not None and math.dist(geometry["midpoint"], expected_midpoint) > tolerance:
            continue
        if expected_direction is not None:
            dot = abs(sum(a * b for a, b in zip(geometry["direction"], expected_direction)))
            if abs(1.0 - dot) > tolerance:
                continue
        matches.append((geometry, edge))
    matches.sort(key=lambda item: (item[0]["midpoint"], item[0]["length"], item[0]["direction"]))
    return tuple(edge for _geometry, edge in matches)


def circular_edge_geometry(edge):
    """Return center, unit axis and radius for a circular solid edge."""
    curve = get_com_member(edge, "GetCurve")
    if curve is None or not bool(get_com_member(curve, "IsCircle")):
        raise ValueError("edge is not circular")
    params = tuple(float(value) for value in get_com_member(curve, "CircleParams")[:7])
    if len(params) != 7 or params[6] <= 0.0:
        raise ValueError("circular edge returned invalid parameters")
    axis = params[3:6]
    magnitude = math.sqrt(sum(value * value for value in axis))
    if magnitude <= 0.0:
        raise ValueError("circular edge returned a zero axis")
    return {
        "center": params[:3],
        "axis": tuple(value / magnitude for value in axis),
        "radius": params[6],
    }


def find_circular_edges(model, *, center=None, radius=None, axis=None, tolerance=1e-6):
    """Resolve circular solid edges by center, radius and unoriented axis."""
    expected_center = tuple(float(value) for value in center) if center is not None else None
    expected_axis = None
    if axis is not None:
        values = tuple(float(value) for value in axis)
        magnitude = math.sqrt(sum(value * value for value in values)) if len(values) == 3 else 0.0
        if magnitude <= 0.0:
            raise ValueError("axis must be a non-zero three-component vector")
        expected_axis = tuple(value / magnitude for value in values)
    matches = []
    for edge in solid_edges(model):
        try:
            geometry = circular_edge_geometry(edge)
        except (TypeError, ValueError, RuntimeError):
            continue
        if expected_center is not None and math.dist(geometry["center"], expected_center) > tolerance:
            continue
        if radius is not None and abs(geometry["radius"] - float(radius)) > tolerance:
            continue
        if expected_axis is not None:
            dot = abs(sum(a * b for a, b in zip(geometry["axis"], expected_axis)))
            if abs(1.0 - dot) > tolerance:
                continue
        matches.append((geometry, edge))
    matches.sort(key=lambda item: (item[0]["center"], item[0]["radius"]))
    return tuple(edge for _geometry, edge in matches)


def _select_feature_edges(model, edges):
    """Select an explicit, non-empty edge sequence and verify the selection."""
    edge_objects = _as_tuple(edges)
    if not edge_objects:
        raise ValueError("at least one explicit edge is required")
    model.ClearSelection2(True)
    for index, edge in enumerate(edge_objects):
        if not _select_com_object(edge, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select edge at index {index}")
    selected_count = _get_selection_count(model)
    if selected_count < len(edge_objects):
        model.ClearSelection2(True)
        raise RuntimeError(
            f"edge selection count mismatch: expected {len(edge_objects)}, got {selected_count}"
        )
    return edge_objects


def _positive_finite(name, value):
    """Validate a positive finite numeric feature parameter."""
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a positive finite value")
    return number


def _feature_object(model, feature_or_name):
    """Resolve a feature object while allowing stable feature names at API edges."""
    if not isinstance(feature_or_name, str):
        if feature_or_name is None:
            raise ValueError("feature reference cannot be None")
        return feature_or_name
    candidates = PLANE_NAME_ALIASES.get(feature_or_name, [feature_or_name])
    for candidate in candidates:
        feature = _safe_com_member(model, "FeatureByName", candidate)
        if feature is not None:
            return feature
    cached = _find_cached_sketch_ref(model, feature_or_name)
    if cached is not None and cached.feature is not None:
        return cached.feature
    raise ValueError(f"feature not found: {feature_or_name}")


def _dispatch_array(objects):
    """Build the explicit SAFEARRAY(IDispatch) required by feature-data arrays."""
    values = _as_tuple(objects)
    if not values:
        raise ValueError("at least one feature object is required")
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, values)


def _typed_sldworks_feature_manager(manager):
    """Wrap a real FeatureManager with the SW2025 makepy InvokeTypes class."""
    ole_object = getattr(manager, "_oleobj_", None)
    if ole_object is None:
        return manager
    try:
        from win32com.client import gencache
        module = gencache.EnsureModule(
            "{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 33, 0,
        )
        return module.FeatureManager(ole_object)
    except Exception as exc:
        raise RuntimeError(
            "SW2025 typed FeatureManager dispatch is required for advanced features"
        ) from exc


def _typed_sldworks_interface(obj, interface_name):
    """Wrap a real SW2025 COM proxy with a named makepy interface class."""
    ole_object = getattr(obj, "_oleobj_", None)
    if ole_object is None:
        return obj
    try:
        from win32com.client import gencache
        module = gencache.EnsureModule(
            "{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 33, 0,
        )
        wrapper = getattr(module, str(interface_name))
        return wrapper(ole_object)
    except Exception as exc:
        raise RuntimeError(
            f"SW2025 typed {interface_name} dispatch is required"
        ) from exc


def _last_model_feature(model):
    """Return the last feature in tree order for legacy boolean-returning APIs."""
    feature = _safe_com_member(model, "FirstFeature")
    last = None
    while feature is not None:
        last = feature
        feature = _safe_com_member(feature, "GetNextFeature")
    return last


def _feature_key(feature):
    """Return a stable comparison key across repeated pywin32 COM proxies."""
    if feature is None:
        return None
    return (
        str(_safe_com_member(feature, "Name", default="")),
        str(_safe_com_member(feature, "GetTypeName2", default="")),
    )


def _select_pattern_inputs(model, reference, seed_features):
    """Select a direction/plane with mark 1 and seed features with mark 4."""
    seeds = tuple(_feature_object(model, item) for item in _as_tuple(seed_features))
    if not seeds:
        raise ValueError("at least one seed feature is required")
    model.ClearSelection2(True)
    if not _select_com_object(reference, append=False, mark=1):
        raise RuntimeError("failed to select the pattern reference")
    for index, seed in enumerate(seeds):
        if not _select_com_object(seed, append=True, mark=4):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select seed feature at index {index}")
    return seeds


def linear_pattern_feature(
    model,
    seed_features,
    direction_reference,
    spacing,
    count,
    *,
    reverse=False,
    geometry_pattern=False,
):
    """Create a one-direction native linear feature pattern from object references."""
    spacing = _positive_finite("spacing", spacing)
    count = int(count)
    if count < 2:
        raise ValueError("count must be at least 2")
    if direction_reference is None:
        raise ValueError("direction_reference cannot be None")
    _select_pattern_inputs(model, direction_reference, seed_features)
    try:
        feature = model.FeatureManager.FeatureLinearPattern3(
            count, spacing, 1, 0.0,
            bool(reverse), False,
            "", "", bool(geometry_pattern), False,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the linear pattern feature")
    return feature


def circular_pattern_feature(
    model,
    seed_features,
    axis_reference,
    angle_rad,
    count,
    *,
    equal_spacing=True,
    reverse=False,
    geometry_pattern=False,
):
    """Create a native circular feature pattern from object references."""
    angle_rad = _positive_finite("angle_rad", angle_rad)
    if angle_rad > math.tau + 1e-12:
        raise ValueError("angle_rad cannot exceed one full revolution")
    count = int(count)
    if count < 2:
        raise ValueError("count must be at least 2")
    if axis_reference is None:
        raise ValueError("axis_reference cannot be None")
    _select_pattern_inputs(model, axis_reference, seed_features)
    try:
        feature = model.FeatureManager.FeatureCircularPattern4(
            count, angle_rad, bool(reverse), "",
            bool(geometry_pattern), bool(equal_spacing), False,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the circular pattern feature")
    return feature


def mirror_feature_objects(model, seed_features, mirror_plane, *, geometry_pattern=False):
    """Mirror native features about an explicit reference-plane object."""
    plane = _feature_object(model, mirror_plane)
    seeds = tuple(_feature_object(model, item) for item in _as_tuple(seed_features))
    if not seeds:
        raise ValueError("at least one seed feature is required")
    feature = None
    for seed_mark, plane_mark, plane_first in (
        # SW2025 API Help: seed features use mark 1; mirror plane uses mark 2.
        (1, 2, False), (1, 2, True),
        (4, 1, False), (2, 1, False), (4, 1, True), (2, 1, True), (0, 0, False),
    ):
        model.ClearSelection2(True)
        plane_selected = False
        if plane_first and isinstance(mirror_plane, str):
            for candidate in PLANE_NAME_ALIASES.get(mirror_plane, [mirror_plane]):
                if _select_by_id(model.Extension, candidate, "PLANE", append=False, mark=plane_mark):
                    plane_selected = True
                    break
        elif plane_first:
            plane_selected = _select_com_object(plane, append=False, mark=plane_mark)
        selected = not plane_first or plane_selected
        for index, seed in enumerate(seeds):
            seed_name = _safe_com_member(seed, "Name")
            by_name = bool(seed_name) and _select_by_id(
                model.Extension, str(seed_name), "BODYFEATURE",
                append=(plane_first or index > 0), mark=seed_mark,
            )
            if not by_name and not _select_com_object(
                seed, append=(plane_first or index > 0), mark=seed_mark
            ):
                selected = False
                break
        if selected and not plane_first and isinstance(mirror_plane, str):
            for candidate in PLANE_NAME_ALIASES.get(mirror_plane, [mirror_plane]):
                if _select_by_id(model.Extension, candidate, "PLANE", append=True, mark=plane_mark):
                    plane_selected = True
                    break
        elif selected and not plane_first:
            plane_selected = _select_com_object(plane, append=True, mark=plane_mark)
        if selected and plane_selected:
            feature = model.FeatureManager.InsertMirrorFeature2(
                False, bool(geometry_pattern), False, False, 0
            )
            if feature is None:
                feature = model.FeatureManager.InsertMirrorFeature(
                    False, bool(geometry_pattern), False, False
                )
        if feature is not None:
            break
    if feature is None:
        model.ClearSelection2(True)
        for index, seed in enumerate(seeds):
            _select_com_object(seed, append=index > 0, mark=4)
        _select_com_object(plane, append=True, mark=1)
        inserted = _safe_com_member(model, "InsertMirrorFeature", bool(geometry_pattern))
        if inserted:
            feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
            if feature is None:
                feature = _safe_com_member(model, "FeatureByPositionReverse", 0)
            if feature is None:
                feature = _last_model_feature(model)
    model.ClearSelection2(True)
    if feature is None:
        specific_plane = _safe_com_member(plane, "GetSpecificFeature2", default=plane)
        for plane_ref in (plane, specific_plane):
            for feature_array in (seeds, list(seeds), _dispatch_array(seeds)):
                definition = model.FeatureManager.CreateDefinition(7)  # swFmMirrorPattern
                if definition is None:
                    continue
                try:
                    definition.Plane = plane_ref
                    definition.PatternFeatureArray = feature_array
                    definition.GeometryPattern = bool(geometry_pattern)
                    feature = model.FeatureManager.CreateFeature(definition)
                except Exception:
                    feature = None
                if feature is not None:
                    break
            if feature is not None:
                break
    if feature is None:
        raise RuntimeError("SolidWorks did not create the mirror feature")
    return feature


def _select_sketch_ref(model, sketch_ref, mark=0):
    """
    按稳定优先级选择草图引用。

    轮廓/区域更接近 FeatureExtrusion3 需要的预选对象；不可用时再回退草图
    Feature 或 Sketch 对象。
    """
    if not sketch_ref:
        return False
    model.ClearSelection2(True)
    _refresh_sketch_ref(sketch_ref)
    for objects in (
        sketch_ref.feature,
        sketch_ref.sketch,
        sketch_ref.contours,
        sketch_ref.regions,
        sketch_ref.segments,
    ):
        if _select_any_object(objects, append=False, mark=mark):
            return True
        model.ClearSelection2(True)
    return False


def _select_sketch_feature_by_name(model, sketch_name, mark=0):
    """通过 FeatureByName 找到草图特征后对象级选择。"""
    for candidate in _get_sketch_name_candidates(sketch_name):
        feature = _safe_com_member(model, "FeatureByName", candidate)
        if feature and _select_com_object(feature, append=False, mark=mark):
            return candidate
    return None


def _ensure_sketch_selected(model, sketch_name):
    """
    确保拉伸/切除前已有可用的草图选择。

    参数:
        model: IModelDoc2 对象
        sketch_name: 草图名称

    返回:
        str
    """
    if str(sketch_name) == "__current_selection__" and _get_selection_count(model) > 0:
        return "__current_selection__"

    active_ref = _capture_sketch_ref(model, fallback=str(sketch_name), source="active")
    if active_ref and _select_sketch_ref(model, active_ref):
        return active_ref.name

    cached_ref = _find_cached_sketch_ref(model, sketch_name)
    if cached_ref and _select_sketch_ref(model, cached_ref):
        return cached_ref.name

    selected_feature = _select_sketch_feature_by_name(model, sketch_name)
    if selected_feature:
        return selected_feature

    selected_sketch = _select_first_candidate(
        model.Extension, _get_sketch_name_candidates(sketch_name), "SKETCH"
    )
    if not selected_sketch:
        model.ClearSelection2(True)
        raise ValueError(
            f"无法选择草图: {sketch_name}。已尝试活动草图对象、缓存草图对象、"
            "FeatureByName 和 SelectByID2('SKETCH')。"
        )
    return selected_sketch


def start_sketch(model, plane_name="Front Plane"):
    """
    在指定基准面上开始草图

    参数:
        model: IModelDoc2
        plane_name: 基准面名称
            英文: "Front Plane", "Top Plane", "Right Plane"
            中文: "前视基准面", "上视基准面", "右视基准面"
    """
    model.ClearSelection2(True)

    selected_plane = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(plane_name), "PLANE"
    )
    if selected_plane:
        model.SketchManager.InsertSketch(True)
        return selected_plane

    raise ValueError(f"无法选择基准面: {plane_name}")


def start_3d_sketch(model):
    """Enter a new native 3D sketch and return its active sketch object."""
    manager = model.SketchManager
    if _safe_com_member(manager, "ActiveSketch") is not None:
        raise RuntimeError("a sketch is already active")
    manager.Insert3DSketch(True)
    active = _safe_com_member(manager, "ActiveSketch")
    if active is None or not bool(_safe_com_member(active, "Is3D", default=False)):
        raise RuntimeError("SolidWorks did not enter a native 3D sketch")
    return active


def find_largest_outer_planar_face(model):
    """Return the largest planar face, preferring the outer member of ties."""
    candidates = []
    for body in get_com_member(model, "GetBodies2", 0, False) or ():
        for face in get_com_member(body, "GetFaces") or ():
            try:
                surface = get_com_member(face, "GetSurface")
                if surface is None or not bool(get_com_member(surface, "IsPlane")):
                    continue
                area = float(get_com_member(face, "GetArea"))
                box = list(get_com_member(face, "GetBox") or ())
                if len(box) >= 6:
                    center = [(float(box[index]) + float(box[index + 3])) / 2.0
                              for index in range(3)]
                    distance_sq = sum(value * value for value in center)
                else:
                    distance_sq = 0.0
                candidates.append((area, distance_sq, face))
            except Exception:
                continue
    if not candidates:
        raise RuntimeError("当前零件没有可用的平面实体面")
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def solid_faces(model):
    """Return all faces from all solid bodies in the active part."""
    faces = []
    for body in _as_tuple(get_com_member(model, "GetBodies2", 0, False)):
        faces.extend(_as_tuple(get_com_member(body, "GetFaces")))
    return tuple(faces)


def solid_vertices(model):
    """Return unique solid-body vertices, de-duplicated by model coordinates."""
    unique = {}
    for body in _as_tuple(get_com_member(model, "GetBodies2", 0, False)):
        for vertex in _as_tuple(get_com_member(body, "GetVertices")):
            point = tuple(float(value) for value in get_com_member(vertex, "GetPoint")[:3])
            unique.setdefault(tuple(round(value, 12) for value in point), vertex)
    return tuple(unique[key] for key in sorted(unique))


def vertex_geometry(vertex):
    """Return a solid vertex's model-space point."""
    point = tuple(float(value) for value in get_com_member(vertex, "GetPoint")[:3])
    if len(point) != 3:
        raise ValueError("vertex did not return three coordinates")
    return {"point": point}


def find_solid_vertices(model, point, tolerance=1e-6):
    """Resolve solid vertices by model-space point rather than topology order."""
    expected = tuple(float(value) for value in point)
    if len(expected) != 3:
        raise ValueError("point must contain three coordinates")
    return tuple(
        vertex for vertex in solid_vertices(model)
        if math.dist(vertex_geometry(vertex)["point"], expected) <= float(tolerance)
    )


def planar_face_geometry(face):
    """Return area, box center and unit normal for a planar face."""
    surface = get_com_member(face, "GetSurface")
    if surface is None or not bool(get_com_member(surface, "IsPlane")):
        raise ValueError("face is not planar")
    box = tuple(float(value) for value in get_com_member(face, "GetBox")[:6])
    face_normal = _safe_com_member(face, "Normal")
    if face_normal is not None:
        normal = tuple(float(value) for value in face_normal[:3])
    else:
        params = tuple(float(value) for value in get_com_member(surface, "PlaneParams")[:6])
        normal = params[:3]
    magnitude = math.sqrt(sum(value * value for value in normal))
    if magnitude <= 0.0:
        raise ValueError("planar face returned a zero normal")
    normal = tuple(value / magnitude for value in normal)
    return {
        "area": float(get_com_member(face, "GetArea")),
        "center": tuple((box[index] + box[index + 3]) / 2.0 for index in range(3)),
        "normal": normal,
        "box": box,
    }


def find_planar_faces(model, *, area=None, center=None, normal=None, tolerance=1e-6):
    """Resolve planar faces by geometric evidence instead of topology order."""
    expected_center = tuple(float(value) for value in center) if center is not None else None
    expected_normal = tuple(float(value) for value in normal) if normal is not None else None
    matches = []
    for face in solid_faces(model):
        try:
            geometry = planar_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        if area is not None and abs(geometry["area"] - float(area)) > tolerance:
            continue
        if expected_center is not None and math.dist(geometry["center"], expected_center) > tolerance:
            continue
        if expected_normal is not None:
            dot = abs(sum(a * b for a, b in zip(geometry["normal"], expected_normal)))
            if abs(1.0 - dot) > tolerance:
                continue
        matches.append((geometry, face))
    matches.sort(key=lambda item: (item[0]["center"], item[0]["area"]))
    return tuple(face for _geometry, face in matches)


def cylindrical_face_geometry(face):
    """Return origin, unit axis, radius and area for a cylindrical face."""
    surface = get_com_member(face, "GetSurface")
    if surface is None or not bool(get_com_member(surface, "IsCylinder")):
        raise ValueError("face is not cylindrical")
    params = tuple(float(value) for value in get_com_member(surface, "CylinderParams")[:7])
    if len(params) != 7 or params[6] <= 0.0:
        raise ValueError("cylindrical face returned invalid parameters")
    axis = params[3:6]
    magnitude = math.sqrt(sum(value * value for value in axis))
    if magnitude <= 0.0:
        raise ValueError("cylindrical face returned a zero axis")
    return {
        "origin": params[:3],
        "axis": tuple(value / magnitude for value in axis),
        "radius": params[6],
        "area": float(get_com_member(face, "GetArea")),
    }


def find_cylindrical_faces(model, *, radius=None, axis=None, tolerance=1e-6):
    """Resolve cylindrical faces by radius and unoriented axis direction."""
    expected_axis = None
    if axis is not None:
        values = tuple(float(value) for value in axis)
        if len(values) != 3:
            raise ValueError("axis must contain three values")
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude <= 0.0:
            raise ValueError("axis must be non-zero")
        expected_axis = tuple(value / magnitude for value in values)
    matches = []
    for face in solid_faces(model):
        try:
            geometry = cylindrical_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        if radius is not None and abs(geometry["radius"] - float(radius)) > tolerance:
            continue
        if expected_axis is not None:
            dot = abs(sum(a * b for a, b in zip(geometry["axis"], expected_axis)))
            if abs(1.0 - dot) > tolerance:
                continue
        matches.append((geometry, face))
    matches.sort(key=lambda item: (item[0]["radius"], item[0]["origin"], item[0]["area"]))
    return tuple(face for _geometry, face in matches)


def conical_face_geometry(face):
    """Return SW2025 ConeParams2 geometry for a conical face."""
    surface = get_com_member(face, "GetSurface")
    if surface is None or not bool(get_com_member(surface, "IsCone")):
        raise ValueError("face is not conical")
    params = tuple(float(value) for value in get_com_member(surface, "ConeParams2")[:11])
    if len(params) != 11 or params[6] < 0.0 or not 0.0 < abs(params[7]) < math.pi / 2.0:
        raise ValueError("conical face returned invalid parameters")
    axis = params[3:6]
    magnitude = math.sqrt(sum(value * value for value in axis))
    if magnitude <= 0.0:
        raise ValueError("conical face returned a zero axis")
    return {
        "origin": params[:3],
        "axis": tuple(value / magnitude for value in axis),
        "radius": params[6],
        "half_angle": params[7],
        "reference_direction": params[8:11],
        "area": float(get_com_member(face, "GetArea")),
    }


def find_conical_faces(model, *, axis=None, half_angle=None, tolerance=1e-6):
    """Resolve conical faces by unoriented axis and half angle."""
    expected_axis = None
    if axis is not None:
        values = tuple(float(value) for value in axis)
        if len(values) != 3:
            raise ValueError("axis must contain three values")
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude <= 0.0:
            raise ValueError("axis must be non-zero")
        expected_axis = tuple(value / magnitude for value in values)
    matches = []
    for face in solid_faces(model):
        try:
            geometry = conical_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        if half_angle is not None and abs(abs(geometry["half_angle"]) - abs(float(half_angle))) > tolerance:
            continue
        if expected_axis is not None:
            dot = abs(sum(a * b for a, b in zip(geometry["axis"], expected_axis)))
            if abs(1.0 - dot) > tolerance:
                continue
        matches.append((geometry, face))
    matches.sort(key=lambda item: (abs(item[0]["half_angle"]), item[0]["origin"], item[0]["area"]))
    return tuple(face for _geometry, face in matches)


def start_sketch_on_largest_planar_face(model):
    """Select the largest outer planar face and enter native sketch editing."""
    model.ClearSelection2(True)
    face = find_largest_outer_planar_face(model)
    if not _select_com_object(face, append=False, mark=0):
        raise RuntimeError("无法选择最大外侧平面")
    model.SketchManager.InsertSketch(True)
    if model.SketchManager.ActiveSketch is None:
        raise RuntimeError("SolidWorks 未在所选实体面进入草图编辑")
    return face


def end_sketch(model):
    """
    退出当前草图，并返回可复用的草图选择引用。

    返回值兼容旧调用：调用者可以忽略它；需要稳定选择时可传给
    `extrude_boss()` / `extrude_cut()` 等特征函数。
    """
    sketch_ref = _capture_sketch_ref(model, source="end_sketch")
    model.SketchManager.InsertSketch(True)
    return _cache_sketch_ref(model, _refresh_sketch_ref(sketch_ref))


def end_3d_sketch(model):
    """Exit the active native 3D sketch and return a reusable sketch reference."""
    active = _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None or not bool(_safe_com_member(active, "Is3D", default=False)):
        raise RuntimeError("no active 3D sketch")
    sketch_ref = _capture_sketch_ref(model, source="end_3d_sketch")
    model.SketchManager.Insert3DSketch(True)
    sketch_ref = _refresh_sketch_ref(sketch_ref)
    if sketch_ref is not None and sketch_ref.feature is None:
        feature = _safe_com_member(model, "FeatureByName", sketch_ref.name)
        if feature is None:
            candidate = _last_model_feature(model)
            candidate_type = str(_safe_com_member(candidate, "GetTypeName2", default=""))
            if candidate_type in {"3DProfileFeature", "ProfileFeature"}:
                feature = candidate
        if feature is None:
            raise RuntimeError("SolidWorks finished the 3D sketch but exposed no feature object")
        sketch_ref.feature = feature
    return _cache_sketch_ref(model, sketch_ref)


@contextmanager
def sketch(model, plane_name="Front Plane"):
    """
    草图上下文管理器。

    示例:
        with sketch(model, "Front Plane") as sketch_name:
            sketch_circle(model, 0, 0, mm(25))
        extrude_boss(model, sketch_name, mm(50))
    """
    start_sketch(model, plane_name)
    sketch_ref = None
    try:
        sketch_ref = _capture_sketch_ref(model, source="context")
        yield sketch_ref.name if sketch_ref else current_sketch_name(model)
    finally:
        finished_ref = end_sketch(model)
        if sketch_ref and finished_ref:
            sketch_ref.feature = finished_ref.feature
            sketch_ref.contours = finished_ref.contours
            sketch_ref.regions = finished_ref.regions
            sketch_ref.segments = finished_ref.segments
            _cache_sketch_ref(model, sketch_ref)


@contextmanager
def sketch_3d(model):
    """Context manager for one native 3D sketch."""
    start_3d_sketch(model)
    sketch_ref = None
    try:
        sketch_ref = _capture_sketch_ref(model, source="3d_context")
        yield sketch_ref.name if sketch_ref else current_sketch_name(model)
    finally:
        finished_ref = end_3d_sketch(model)
        if sketch_ref and finished_ref:
            sketch_ref.feature = finished_ref.feature
            sketch_ref.contours = finished_ref.contours
            sketch_ref.regions = finished_ref.regions
            sketch_ref.segments = finished_ref.segments
            _cache_sketch_ref(model, sketch_ref)


def current_sketch_name(model, fallback="Sketch1"):
    """
    获取当前草图名称。

    参数:
        model: IModelDoc2
        fallback: 无法读取当前草图时返回的默认名称
    """
    active_sketch = model.SketchManager.ActiveSketch
    if active_sketch:
        return active_sketch.Name
    return fallback


def sketch_point(model, x, y):
    """Create a native point in the active 2D sketch (metres)."""
    coordinates = (float(x), float(y))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("sketch point coordinates must be finite")
    manager = model.SketchManager
    previous_add_to_db = bool(getattr(manager, "AddToDB", False))
    try:
        manager.AddToDB = True
        point = manager.CreatePoint(coordinates[0], coordinates[1], 0.0)
    finally:
        manager.AddToDB = previous_add_to_db
    if point is None:
        raise RuntimeError("SolidWorks did not create the sketch point")
    return point


def sketch_point_3d(model, x, y, z):
    """Create a native point in the active 3D sketch (metres)."""
    coordinates = tuple(float(value) for value in (x, y, z))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("3D sketch point coordinates must be finite")
    active = _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None or not bool(_safe_com_member(active, "Is3D", default=False)):
        raise RuntimeError("a native 3D sketch must be active")
    manager = model.SketchManager
    previous_add_to_db = bool(getattr(manager, "AddToDB", False))
    try:
        manager.AddToDB = True
        point = manager.CreatePoint(*coordinates)
    finally:
        manager.AddToDB = previous_add_to_db
    if point is None:
        raise RuntimeError("SolidWorks did not create the 3D sketch point")
    return point


def sketch_line(model, x1, y1, x2, y2):
    """画直线（单位: 米）"""
    manager = model.SketchManager
    active_sketch = _safe_com_member(manager, "ActiveSketch")
    before = _as_tuple(_safe_com_member(active_sketch, "GetSketchSegments"))
    previous_add_to_db = bool(getattr(manager, "AddToDB", False))
    try:
        manager.AddToDB = True
        line = manager.CreateLine(x1, y1, 0, x2, y2, 0)
    finally:
        manager.AddToDB = previous_add_to_db
    if line is not None:
        return line
    after = _as_tuple(_safe_com_member(active_sketch, "GetSketchSegments"))
    if len(after) > len(before):
        return after[-1]
    raise RuntimeError("SolidWorks did not create the sketch line")


def sketch_line_3d(model, start, end):
    """Create one exact native 3D-sketch line from two XYZ points (metres)."""
    start = tuple(float(value) for value in start)
    end = tuple(float(value) for value in end)
    if len(start) != 3 or len(end) != 3 or not all(
        math.isfinite(value) for value in start + end
    ):
        raise ValueError("3D line endpoints must contain three finite coordinates")
    if math.dist(start, end) <= 1e-12:
        raise ValueError("3D line endpoints must be distinct")
    manager = model.SketchManager
    active = _safe_com_member(manager, "ActiveSketch")
    if active is None or not bool(_safe_com_member(active, "Is3D", default=False)):
        raise RuntimeError("no active 3D sketch")
    before = _as_tuple(_safe_com_member(active, "GetSketchSegments"))
    previous_add_to_db = bool(getattr(manager, "AddToDB", False))
    try:
        manager.AddToDB = True
        line = manager.CreateLine(*(start + end))
    finally:
        manager.AddToDB = previous_add_to_db
    if line is not None:
        return line
    after = _as_tuple(_safe_com_member(active, "GetSketchSegments"))
    if len(after) > len(before):
        return after[-1]
    raise RuntimeError("SolidWorks did not create the 3D sketch line")


def sketch_rectangle(model, cx, cy, w, h):
    """以中心点画矩形（单位: 米）"""
    return model.SketchManager.CreateCenterRectangle(
        cx, cy, 0, cx + w / 2, cy + h / 2, 0
    )


def sketch_corner_rectangle(model, x1, y1, x2, y2):
    """以对角线画矩形（单位: 米）"""
    return model.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0)


def sketch_circle(model, cx, cy, radius):
    """画圆（单位: 米）"""
    manager = model.SketchManager
    active_sketch = _safe_com_member(manager, "ActiveSketch")
    before = _as_tuple(_safe_com_member(active_sketch, "GetSketchSegments"))
    previous_add_to_db = bool(getattr(manager, "AddToDB", False))
    try:
        manager.AddToDB = True
        circle = manager.CreateCircleByRadius(cx, cy, 0, radius)
    finally:
        manager.AddToDB = previous_add_to_db
    if circle is not None:
        return circle
    after = _as_tuple(_safe_com_member(active_sketch, "GetSketchSegments"))
    if len(after) > len(before):
        return after[-1]
    raise RuntimeError("SolidWorks did not create the sketch circle")


def sketch_arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    """
    画圆弧

    参数:
        cx, cy: 圆心坐标（米）
        x1, y1: 起点坐标
        x2, y2: 终点坐标
        direction: 1=逆时针, -1=顺时针
    """
    return model.SketchManager.CreateArc(cx, cy, 0, x1, y1, 0, x2, y2, 0, direction)


def sketch_polygon(model, cx, cy, radius, sides=6):
    """画正多边形（内切圆方式）"""
    return model.SketchManager.CreatePolygon(cx, cy, 0, cx + radius, cy, 0, sides, True)


def sketch_slot(model, x1, y1, x2, y2, radius):
    """画直槽；radius 为两端圆弧半径。"""
    return model.SketchManager.CreateSketchSlot(
        0,  # swSketchSlotCreationType_e: 0=Straight
        radius * 2.0, radius * 2.0,  # SolidWorks API 接收总宽度
        x1, y1, 0,
        x2, y2, 0,
        0, 0, 0,
        1, False
    )


def sketch_spline(model, points):
    """
    画样条曲线

    参数:
        points: [(x1,y1), (x2,y2), ...] 控制点列表（单位: 米）
    """
    import pythoncom
    from win32com.client import VARIANT

    point_array = []
    for x, y in points:
        point_array.extend([x, y, 0.0])
    point_data = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, point_array)
    return model.SketchManager.CreateSpline2(point_data, False)


def sketch_spline_3d(model, points):
    """Create a native 3D-sketch spline through ordered XYZ points."""
    values = tuple(tuple(float(value) for value in point) for point in points)
    if len(values) < 3 or any(len(point) != 3 for point in values):
        raise ValueError("3D spline requires at least three XYZ points")
    flattened = tuple(value for point in values for value in point)
    if not all(math.isfinite(value) for value in flattened):
        raise ValueError("3D spline coordinates must be finite")
    active = _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None or not bool(_safe_com_member(active, "Is3D", default=False)):
        raise RuntimeError("no active 3D sketch")
    point_data = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flattened)
    spline = model.SketchManager.CreateSpline2(point_data, False)
    if spline is None:
        raise RuntimeError("SolidWorks did not create the 3D sketch spline")
    return spline


def sketch_ellipse(model, cx, cy, major_radius, minor_radius, angle_rad=0.0):
    """Create a full native ellipse from center, semiaxes and rotation."""
    major_radius = _positive_finite("major_radius", major_radius)
    minor_radius = _positive_finite("minor_radius", minor_radius)
    if major_radius < minor_radius:
        raise ValueError("major_radius must be greater than or equal to minor_radius")
    angle_rad = float(angle_rad)
    if not math.isfinite(angle_rad):
        raise ValueError("angle_rad must be finite")
    major = (float(cx) + major_radius * math.cos(angle_rad),
             float(cy) + major_radius * math.sin(angle_rad))
    minor = (float(cx) - minor_radius * math.sin(angle_rad),
             float(cy) + minor_radius * math.cos(angle_rad))
    segment = model.SketchManager.CreateEllipse(
        float(cx), float(cy), 0.0,
        major[0], major[1], 0.0,
        minor[0], minor[1], 0.0,
    )
    if segment is None:
        raise RuntimeError("SolidWorks did not create the ellipse")
    return segment


def sketch_parabola(model, focus, apex, start, end):
    """Create a bounded native parabola from focus, apex and endpoints."""
    points = [tuple(float(value) for value in point) for point in (focus, apex, start, end)]
    if any(len(point) != 2 or not all(math.isfinite(value) for value in point) for point in points):
        raise ValueError("focus, apex, start and end must be finite 2D points")
    values = [coordinate for point in points for coordinate in (*point, 0.0)]
    segment = model.SketchManager.CreateParabola(*values)
    if segment is None:
        raise RuntimeError("SolidWorks did not create the parabola")
    return segment


def sketch_equation_curve(
    model, x_expression, y_expression, range_start, range_end,
    *, z_expression="", angle_range=False, rotation_angle=0.0,
    x_offset=0.0, y_offset=0.0, lock_start=False, lock_end=False,
):
    """Create a native parametric equation-driven sketch spline."""
    if not str(x_expression).strip() or not str(y_expression).strip():
        raise ValueError("x_expression and y_expression cannot be empty")
    range_start, range_end = float(range_start), float(range_end)
    if not all(math.isfinite(value) for value in (range_start, range_end)) or range_end <= range_start:
        raise ValueError("equation range must be finite and increasing")
    spline = model.SketchManager.CreateEquationSpline2(
        str(x_expression), str(y_expression), str(z_expression),
        range_start, range_end, bool(angle_range), float(rotation_angle),
        float(x_offset), float(y_offset), bool(lock_start), bool(lock_end),
    )
    if spline is None:
        raise RuntimeError("SolidWorks did not create the equation-driven curve")
    return spline


def sketch_text(
    model, x, y, text, *, alignment=0, flip_direction=False,
    horizontal_mirror=False, width_factor=1.0, character_spacing=0.0,
):
    """Insert native sketch text at a point in the active 2D sketch."""
    text = str(text)
    if not text:
        raise ValueError("text cannot be empty")
    width_factor = _positive_finite("width_factor", width_factor)
    result = get_com_member(
        model, "InsertSketchText",
        float(x), float(y), 0.0, text, int(alignment),
        bool(flip_direction), bool(horizontal_mirror),
        width_factor, float(character_spacing),
    )
    if result is None:
        raise RuntimeError("SolidWorks did not create sketch text")
    return result


def _active_sketch_segments(model):
    """Return current sketch segments as a tuple."""
    sketch_obj = _safe_com_member(model.SketchManager, "ActiveSketch")
    if sketch_obj is None:
        raise RuntimeError("no active sketch")
    return _as_tuple(_safe_com_member(sketch_obj, "GetSketchSegments"))


def _select_sketch_entities(model, entities):
    """Select an explicit non-empty entity sequence for sketch operations."""
    values = _as_tuple(entities)
    if not values:
        raise ValueError("at least one sketch entity is required")
    model.ClearSelection2(True)
    for index, entity in enumerate(values):
        if not _select_com_object(entity, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select sketch entity at index {index}")
    return values


def sketch_convert_entities(model, entities, *, chain=False, inner_loops=False):
    """Convert selected model/sketch entities into the active native sketch."""
    before = len(_active_sketch_segments(model))
    _select_sketch_entities(model, entities)
    try:
        result = model.SketchManager.SketchUseEdge3(bool(chain), bool(inner_loops))
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if len(after) <= before:
        raise RuntimeError("Convert Entities did not add sketch geometry")
    return tuple(after[before:])


def sketch_offset_entities(
    model, entities, offset, *, both_directions=False, chain=False,
    cap_ends=False, construction=False, add_dimensions=True,
):
    """Offset selected native sketch entities and return newly added segments."""
    offset = float(offset)
    if not math.isfinite(offset) or offset == 0.0:
        raise ValueError("offset must be finite and non-zero")
    before = len(_active_sketch_segments(model))
    _select_sketch_entities(model, entities)
    try:
        result = model.SketchManager.SketchOffset2(
            offset, bool(both_directions), bool(chain), bool(cap_ends),
            bool(construction), bool(add_dimensions),
        )
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if len(after) <= before:
        raise RuntimeError(f"Offset Entities did not add sketch geometry: {result}")
    return tuple(after[before:])


def _select_sketch_pick_points(model, selections, *, mark=0):
    """Select ``(entity, (x, y, z))`` pairs while preserving pick points."""
    values = tuple(selections or ())
    if not values:
        raise ValueError("at least one sketch entity and pick point are required")
    model.ClearSelection2(True)
    for index, item in enumerate(values):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("each selection must be (entity, (x, y, z))")
        entity, point = item
        point = tuple(float(value) for value in point)
        if len(point) != 3 or not all(math.isfinite(value) for value in point):
            raise ValueError("each pick point must contain three finite coordinates")
        selected = False
        name = _safe_com_member(entity, "GetName")
        if name:
            selected = bool(model.Extension.SelectByID2(
                str(name), "SKETCHSEGMENT", *point, index > 0, int(mark),
                _empty_callout(), 0,
            ))
        if not selected:
            selected = select_com_object_at(
                model, entity, point, append=index > 0, mark=mark
            )
        if not selected:
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select sketch entity at index {index}")
    return values


def sketch_trim(model, option, selections, *, trim_point=None, mark=0):
    """Trim explicitly selected active-sketch entities using native pick points.

    ``selections`` contains ``(entity, (x, y, z))`` pairs.  SolidWorks uses
    those pick points to resolve which part of each segment is trimmed.  Only
    Power Trim (option 3) accepts a non-zero ``trim_point`` argument.
    """
    option = int(option)
    _select_sketch_pick_points(model, selections, mark=int(mark))
    if option == 3:
        trim_values = tuple(trim_point) if trim_point is not None else ()
        if len(trim_values) != 3:
            raise ValueError("Power Trim requires a three-coordinate trim_point")
        coordinates = tuple(float(value) for value in trim_values)
    else:
        if trim_point is not None:
            raise ValueError("trim_point is only valid for Power Trim option 3")
        coordinates = (0.0, 0.0, 0.0)
    try:
        result = model.SketchManager.SketchTrim(option, *coordinates)
    finally:
        model.ClearSelection2(True)
    if result is False:
        raise RuntimeError("Sketch trim failed")
    return result


def sketch_extend(model, entity, *, pick_point=(0.0, 0.0, 0.0)):
    """Extend one selected sketch entity to the nearest intersecting entity."""
    _select_sketch_pick_points(model, ((entity, pick_point),))
    try:
        result = model.SketchManager.SketchExtend(0.0, 0.0, 0.0)
    finally:
        model.ClearSelection2(True)
    if result is False:
        raise RuntimeError("Sketch extend failed")
    return result


def linear_sketch_pattern(
    model, entities, count_x, spacing_x, *, count_y=1, spacing_y=0.0,
    angle_x=0.0, angle_y=math.pi / 2.0, delete_instances=False,
    add_dimensions=True,
):
    """Create a native linear sketch step-and-repeat from explicit entities."""
    count_x, count_y = int(count_x), int(count_y)
    if count_x < 1 or count_y < 1 or count_x * count_y < 2:
        raise ValueError("linear sketch pattern must create at least two total instances")
    before = len(_active_sketch_segments(model))
    _select_sketch_entities(model, entities)
    try:
        result = model.SketchManager.CreateLinearSketchStepAndRepeat(
            count_x, count_y, float(spacing_x), float(spacing_y),
            float(angle_x), float(angle_y), bool(delete_instances),
            bool(add_dimensions), bool(add_dimensions), bool(add_dimensions),
            bool(add_dimensions), bool(add_dimensions),
        )
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if len(after) <= before:
        raise RuntimeError(f"linear sketch pattern added no geometry: {result}")
    return tuple(after[before:])


def circular_sketch_pattern(
    model, entities, radius, total_angle, count, *, rotate_instances=True,
    delete_instances=False, add_dimensions=True,
):
    """Create a circular sketch pattern using SW's positive ``ArcRadius``.

    SolidWorks infers the pattern center from the seed geometry; for an
    unambiguous circle seed the center is one arc radius in +X from the seed.
    The native API does not expose independent center coordinates.
    """
    radius = _positive_finite("radius", radius)
    total_angle = _positive_finite("total_angle", total_angle)
    count = int(count)
    if count < 2:
        raise ValueError("circular sketch pattern count must be at least 2")
    before = len(_active_sketch_segments(model))
    _select_sketch_entities(model, entities)
    try:
        result = model.SketchManager.CreateCircularSketchStepAndRepeat(
            radius, total_angle, count, total_angle / count,
            bool(rotate_instances), bool(delete_instances),
            bool(add_dimensions), bool(add_dimensions), bool(add_dimensions),
        )
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if len(after) <= before:
        raise RuntimeError(f"circular sketch pattern added no geometry: {result}")
    return tuple(after[before:])


def sketch_mirror_entities(model, entities, centerline):
    """Mirror explicit sketch entities about one selected centerline.

    The native ``IModelDoc2.SketchMirror`` contract requires entity selection
    mark 1 and mirror-centerline selection mark 2.
    """
    values = _as_tuple(entities)
    if not values:
        raise ValueError("at least one sketch entity is required")
    if centerline is None:
        raise ValueError("a mirror centerline is required")
    before = _active_sketch_segments(model)
    model.ClearSelection2(True)
    try:
        for index, entity in enumerate(values):
            if not _select_com_object(entity, append=index > 0, mark=1):
                raise RuntimeError(f"failed to select mirror entity at index {index}")
        if not _select_com_object(centerline, append=True, mark=2):
            raise RuntimeError("failed to select sketch mirror centerline")
        model.SketchMirror()
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if len(after) <= len(before):
        raise RuntimeError("SketchMirror added no geometry")
    return tuple(after[len(before):])


def move_sketch_point(point, x, y, z=0.0):
    """Move one unconstrained native sketch point and verify its coordinates."""
    coordinates = tuple(float(value) for value in (x, y, z))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("sketch-point coordinates must be finite")
    if not bool(point.SetCoords(*coordinates)):
        raise RuntimeError("SolidWorks rejected sketch-point coordinates")
    actual = tuple(float(get_com_member(point, axis)) for axis in ("X", "Y", "Z"))
    if math.dist(actual, coordinates) > 1e-9:
        raise RuntimeError(f"sketch point did not reach requested coordinates: {actual}")
    return actual


def set_sketch_construction(entities, construction=True):
    """Set construction state on explicit native sketch segments."""
    values = _as_tuple(entities)
    if not values:
        raise ValueError("at least one sketch segment is required")
    for entity in values:
        entity.ConstructionGeometry = bool(construction)
        if bool(get_com_member(entity, "ConstructionGeometry")) != bool(construction):
            raise RuntimeError("SolidWorks did not update construction state")
    return values


def delete_sketch_entities(model, entities, *, delete_options=0):
    """Delete explicitly selected entities from the active native sketch."""
    before = _active_sketch_segments(model)
    values = _select_sketch_entities(model, entities)
    try:
        deleted = bool(model.Extension.DeleteSelection2(int(delete_options)))
    finally:
        model.ClearSelection2(True)
    after = _active_sketch_segments(model)
    if not deleted or len(after) > len(before) - len(values):
        raise RuntimeError("SolidWorks did not delete all requested sketch entities")
    return {"deleted": len(before) - len(after), "remaining": len(after)}


def auto_dimension_sketch(model, sketch=None, sketch_segments=None):
    """@brief 按官方 AutoDimension2 流程为当前草图创建真实模型尺寸。

    SolidWorks 的工程图 ``InsertModelAnnotations`` 只能导入模型中已有的
    显示尺寸，不能凭空为拉伸深度或矩形轮廓生成尺寸。该函数在草图编辑态
    选择水平/垂直基准线，再调用 ``ISketch.AutoDimension2``，因此生成的尺寸
    会成为模型的真实 DisplayDimension，可被工程图导入并复核。

    返回值包含 ``status_code``（官方约定 0 表示成功）、选择数量和是否创建
    尺寸的可审计信息。函数不会把失败伪装成成功。
    """
    active = sketch or _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None:
        return {"status": "blocked", "status_code": None, "error_code": "SKETCH_NOT_ACTIVE", "selected": 0}

    def segments():
        supplied = _as_tuple(sketch_segments)
        if supplied:
            return supplied
        for name in ("GetSketchSegments", "IGetSketchSegments"):
            value = _safe_com_member(active, name)
            result = _as_tuple(value)
            if result:
                return result
        return ()

    horizontal = None
    vertical = None
    for segment in segments():
        try:
            start = get_com_member(segment, "GetStartPoint2")
            end = get_com_member(segment, "GetEndPoint2")
            dx = abs(float(get_com_member(start, "X")) - float(get_com_member(end, "X")))
            dy = abs(float(get_com_member(start, "Y")) - float(get_com_member(end, "Y")))
        except Exception:
            continue
        if dx > dy and horizontal is None:
            horizontal = segment
        elif dy > dx and vertical is None:
            vertical = segment

    model.ClearSelection2(True)
    selected = 0
    # SW2024 swAutodimMark_e：2=水平基准，4=垂直基准。
    # 官方示例要求垂直线作为水平基准、水平线作为垂直基准。
    for segment, mark in ((vertical, 2), (horizontal, 4)):
        if segment is None:
            continue
        try:
            if bool(segment.Select3(selected > 0, mark, _empty_callout())):
                selected += 1
        except Exception:
            try:
                if bool(segment.Select4(selected > 0, _empty_callout())):
                    selected += 1
            except Exception:
                pass

    status_code = None
    try:
        # swAutodimEntitiesAll=1, Baseline=1, Below=-1, Left=-1。
        status_code = int(get_com_member(active, "AutoDimension2", 1, 1, -1, 1, -1))
    except Exception as exc:
        model.ClearSelection2(True)
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "SKETCH_AUTODIMENSION_CALL_FAILED",
            "error": str(exc),
            "selected": selected,
        }
    try:
        model.GraphicsRedraw2()
    except Exception:
        pass
    model.ClearSelection2(True)
    return {
        "status": "pass" if status_code == 0 else "blocked",
        "status_code": status_code,
        "error_code": None if status_code == 0 else "SKETCH_AUTODIMENSION_REJECTED",
        "selected": selected,
    }


def add_dimension(model, x, y):
    """在指定位置添加尺寸标注"""
    return model.AddDimension2(x, y, 0)


def display_dimension_attached_entities(display_dimension):
    """Return the native entities attached to one display dimension."""
    annotation = get_com_member(display_dimension, "GetAnnotation")
    return _as_tuple(get_com_member(annotation, "GetAttachedEntities3"))


def _select_display_dimension(model, display_dimension):
    """Select a display dimension by annotation, then by stable selection name."""
    model.ClearSelection2(True)
    annotation = get_com_member(display_dimension, "GetAnnotation")
    selected = bool(_safe_com_member(
        annotation, "Select3", False, _empty_callout(), default=False
    ))
    if not selected:
        selection_name = str(
            _safe_com_member(display_dimension, "GetNameForSelection", default="") or ""
        )
        if selection_name:
            selected = bool(model.Extension.SelectByID2(
                selection_name, "DIMENSION", 0.0, 0.0, 0.0,
                False, 0, _empty_callout(), 0,
            ))
    return selected


def rebind_sketch_dimension(
    model, display_dimension, new_entities, x, y, z=0.0, *, preserve_value=True,
    preserve_name=True, preserve_tolerance=True,
):
    """Recreate a driving sketch dimension on explicit replacement entities.

    SW2025 returns ``False`` from ``IAnnotation.SetAttachedEntities`` for a
    driving sketch dimension.  This wrapper therefore performs an explicit
    native delete-and-recreate operation and restores the driving value.
    The returned display dimension is a new model object; callers must replace
    stale references to the deleted dimension.
    """
    coordinates = tuple(float(value) for value in (x, y, z))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("dimension placement coordinates must be finite")
    values = _as_tuple(new_entities)
    if not values:
        raise ValueError("at least one replacement entity is required")
    old_dimension = get_com_member(display_dimension, "GetDimension2", 0)
    old_value = float(get_com_member(old_dimension, "SystemValue"))
    old_name = str(_safe_com_member(old_dimension, "Name", default="") or "")
    old_tolerance_type = int(
        _safe_com_member(old_dimension, "GetToleranceType", default=0)
    )
    old_tolerance_values = tuple(float(value) for value in _as_tuple(
        _safe_com_member(old_dimension, "GetToleranceValues", default=(0.0, 0.0))
    ))
    if not _select_display_dimension(model, display_dimension):
        raise RuntimeError("failed to select the old sketch dimension")
    try:
        deleted = bool(model.Extension.DeleteSelection2(0))
    finally:
        model.ClearSelection2(True)
    if not deleted:
        raise RuntimeError("SolidWorks did not delete the old sketch dimension")
    _select_sketch_entities(model, values)
    try:
        replacement = model.AddDimension2(*coordinates)
    finally:
        model.ClearSelection2(True)
    if replacement is None:
        raise RuntimeError("SolidWorks did not recreate the sketch dimension")
    replacement_dimension = get_com_member(replacement, "GetDimension2", 0)
    if preserve_value:
        replacement_dimension.SystemValue = old_value
    actual_value = float(get_com_member(replacement_dimension, "SystemValue"))
    if preserve_value and abs(actual_value - old_value) > 1e-9:
        raise RuntimeError("recreated sketch dimension did not preserve its driving value")
    if preserve_name and old_name:
        replacement_dimension.Name = old_name
    actual_name = str(_safe_com_member(replacement_dimension, "Name", default="") or "")
    if preserve_name and old_name and actual_name != old_name:
        raise RuntimeError(
            f"recreated sketch dimension did not preserve its name: {actual_name} != {old_name}"
        )
    if preserve_tolerance:
        if not bool(get_com_member(replacement_dimension, "SetToleranceType", old_tolerance_type)):
            raise RuntimeError("recreated sketch dimension rejected its tolerance type")
        if len(old_tolerance_values) >= 2 and not bool(get_com_member(
            replacement_dimension, "SetToleranceValues",
            old_tolerance_values[0], old_tolerance_values[1],
        )):
            raise RuntimeError("recreated sketch dimension rejected its tolerance values")
    actual_tolerance_type = int(
        _safe_com_member(replacement_dimension, "GetToleranceType", default=0)
    )
    actual_tolerance_values = tuple(float(value) for value in _as_tuple(
        _safe_com_member(replacement_dimension, "GetToleranceValues", default=(0.0, 0.0))
    ))
    if preserve_tolerance and (
        actual_tolerance_type != old_tolerance_type
        or len(actual_tolerance_values) < 2
        or len(old_tolerance_values) < 2
        or any(abs(actual_tolerance_values[index] - old_tolerance_values[index]) > 1e-12 for index in range(2))
    ):
        raise RuntimeError("recreated sketch dimension did not preserve its tolerance")
    attached = display_dimension_attached_entities(replacement)
    if not attached:
        raise RuntimeError("recreated sketch dimension has no attached entities")
    return {
        "display_dimension": replacement,
        "strategy": "delete_recreate",
        "value": actual_value,
        "name": actual_name,
        "tolerance": {
            "type": actual_tolerance_type,
            "values": actual_tolerance_values,
        },
        "attached_count": len(attached),
    }


def add_sketch_relation(model, relation_type):
    """
    添加草图几何关系

    常用 relation_type:
        "sgFIXED", "sgHORIZONTAL", "sgVERTICAL", "sgCOLINEAR",
        "sgPARALLEL", "sgPERPENDICULAR", "sgTANGENT", "sgCONCENTRIC",
        "sgEQUAL", "sgSYMMETRIC", "sgMIDPOINT", "sgCOINCIDENT"
    """
    return model.SketchAddConstraints(relation_type)


def sketch_relations(model, *, filter_type=0):
    """Return relations from the active sketch's native RelationManager.

    ``filter_type`` follows ``swSketchRelationFilterType_e``; 0 is ``swAll``.
    """
    filter_type = int(filter_type)
    if filter_type < 0 or filter_type > 7:
        raise ValueError("filter_type must be a swSketchRelationFilterType_e value from 0 to 7")
    sketch = _safe_com_member(model.SketchManager, "ActiveSketch")
    if sketch is None:
        raise RuntimeError("no active sketch")
    manager = _safe_com_member(sketch, "RelationManager")
    if manager is None:
        raise RuntimeError("active sketch does not expose a RelationManager")
    return _as_tuple(_safe_com_member(manager, "GetRelations", filter_type))


def sketch_relation_summary(relation):
    """Read the stable native type, entity count and suppression state."""
    return {
        "type": int(get_com_member(relation, "GetRelationType")),
        "entity_count": int(get_com_member(relation, "GetEntitiesCount")),
        "suppressed": bool(get_com_member(relation, "Suppressed")),
    }


def add_sketch_relation_to_entities(model, entities, relation_type):
    """Add one native geometric relation to explicit active-sketch entities."""
    relation_type = str(relation_type).strip()
    if not relation_type.startswith("sg"):
        raise ValueError("relation_type must be a SolidWorks sg* relation identifier")
    before = sketch_relations(model)
    _select_sketch_entities(model, entities)
    try:
        model.SketchAddConstraints(relation_type)
    finally:
        model.ClearSelection2(True)
    after = sketch_relations(model)
    if len(after) <= len(before):
        raise RuntimeError(f"SolidWorks did not add sketch relation {relation_type}")
    return after[len(before):]


def add_sketch_relation_direct(model, entities, constraint_type):
    """Add a native sketch relation through ``ISketchRelationManager``.

    This selection-independent entry point uses ``swConstraintType_e`` values
    and preserves the returned ``ISketchRelation`` for definition readback and
    later replacement/suppression operations.
    """
    values = _as_tuple(entities)
    if not values or any(entity is None for entity in values):
        raise ValueError("at least one valid sketch entity is required")
    constraint_type = int(constraint_type)
    if constraint_type <= 0 or constraint_type > 85:
        raise ValueError("constraint_type must be a valid swConstraintType_e value")
    sketch = _safe_com_member(model.SketchManager, "ActiveSketch")
    manager = _safe_com_member(sketch, "RelationManager") if sketch is not None else None
    if manager is None:
        raise RuntimeError("active sketch does not expose a RelationManager")
    before = _as_tuple(_safe_com_member(manager, "GetRelations", 0))
    relation = manager.AddRelation(_dispatch_array(values), constraint_type)
    after = _as_tuple(_safe_com_member(manager, "GetRelations", 0))
    if relation is None or len(after) <= len(before):
        raise RuntimeError("SolidWorks did not add the direct sketch relation")
    summary = sketch_relation_summary(relation)
    if summary["type"] != constraint_type:
        raise RuntimeError(
            f"direct sketch relation type mismatch: {summary['type']} != {constraint_type}"
        )
    return relation


def add_sketch_relations_direct_batch(model, relation_specs):
    """Add multiple direct relations with rollback on partial failure.

    Each item is ``(entities, swConstraintType_e)``.  All items are validated
    before mutation.  If SolidWorks rejects a later item, every relation
    created by this batch is removed through ``RelationManager.DeleteRelation``.
    """
    specs = tuple(relation_specs)
    if not specs:
        raise ValueError("relation_specs cannot be empty")
    normalized = []
    for index, spec in enumerate(specs):
        if len(spec) != 2:
            raise ValueError(f"relation spec {index} must contain entities and type")
        entities, constraint_type = spec
        values = _as_tuple(entities)
        constraint_type = int(constraint_type)
        if not values or any(entity is None for entity in values):
            raise ValueError(f"relation spec {index} has no valid entities")
        if constraint_type <= 0 or constraint_type > 85:
            raise ValueError(f"relation spec {index} has an invalid constraint type")
        normalized.append((values, constraint_type))
    sketch = _safe_com_member(model.SketchManager, "ActiveSketch")
    manager = _safe_com_member(sketch, "RelationManager") if sketch is not None else None
    if manager is None:
        raise RuntimeError("active sketch does not expose a RelationManager")
    baseline = len(_as_tuple(_safe_com_member(manager, "GetRelations", 0)))
    created = []
    try:
        for entities, constraint_type in normalized:
            created.append(add_sketch_relation_direct(model, entities, constraint_type))
    except Exception:
        for relation in reversed(created):
            if not bool(manager.DeleteRelation(relation)):
                raise RuntimeError("direct relation batch failed and rollback was incomplete")
        remaining = len(_as_tuple(_safe_com_member(manager, "GetRelations", 0)))
        if remaining != baseline:
            raise RuntimeError(
                f"direct relation batch rollback count mismatch: {remaining} != {baseline}"
            )
        raise
    return tuple(created)


def set_sketch_relation_suppressed(relation, suppressed=True):
    """Suppress or restore one native sketch relation and verify readback."""
    requested = bool(suppressed)
    relation.Suppressed = requested
    actual = bool(get_com_member(relation, "Suppressed"))
    if actual != requested:
        raise RuntimeError("SolidWorks did not update sketch-relation suppression")
    return actual


def replace_sketch_relation_entity(relation, old_entity, new_entity):
    """Rebind one native sketch relation from ``old_entity`` to ``new_entity``."""
    if old_entity is None or new_entity is None:
        raise ValueError("old_entity and new_entity are required")
    before_count = int(get_com_member(relation, "GetEntitiesCount"))
    replaced = bool(relation.ReplaceEntity(old_entity, new_entity))
    after_count = int(get_com_member(relation, "GetEntitiesCount"))
    if not replaced or after_count != before_count:
        raise RuntimeError("SolidWorks did not replace the sketch-relation entity")
    return relation


def replace_sketch_relation_entities_batch(replacements):
    """Replace entities across existing relations with reverse rollback.

    Each item is ``(relation, old_entity, new_entity)``.  All inputs are
    validated before mutation.  If a later replacement fails, prior changes
    from this batch are reversed in last-in-first-out order.
    """
    items = tuple(replacements)
    if not items:
        raise ValueError("replacements cannot be empty")
    normalized = []
    for index, item in enumerate(items):
        if len(item) != 3:
            raise ValueError(f"replacement {index} must contain relation, old, and new")
        relation, old_entity, new_entity = item
        if relation is None or old_entity is None or new_entity is None:
            raise ValueError(f"replacement {index} contains an invalid object")
        normalized.append((relation, old_entity, new_entity))
    completed = []
    try:
        for relation, old_entity, new_entity in normalized:
            replace_sketch_relation_entity(relation, old_entity, new_entity)
            completed.append((relation, old_entity, new_entity))
    except Exception:
        for relation, old_entity, new_entity in reversed(completed):
            try:
                replace_sketch_relation_entity(relation, new_entity, old_entity)
            except Exception as rollback_error:
                raise RuntimeError(
                    "sketch-relation batch replacement failed and rollback was incomplete"
                ) from rollback_error
        raise
    return tuple(relation for relation, _old, _new in completed)


def delete_sketch_relation(model, entity, relation_index, relation_type):
    """Delete one indexed relation from an explicitly selected sketch entity."""
    relation_index = int(relation_index)
    if relation_index < 0:
        raise ValueError("relation_index must be zero or greater")
    relation_type = str(relation_type).strip()
    if not relation_type.startswith("sg"):
        raise ValueError("relation_type must be a SolidWorks sg* relation identifier")
    before = sketch_relations(model)
    _select_sketch_entities(model, (entity,))
    try:
        model.SketchConstraintsDel(relation_index, relation_type)
    finally:
        model.ClearSelection2(True)
    after = sketch_relations(model)
    if len(after) >= len(before):
        raise RuntimeError(f"SolidWorks did not delete sketch relation {relation_type}")
    return {"deleted": len(before) - len(after), "remaining": len(after)}


# ============================================================
# 特征操作
# ============================================================

def extrude_boss(
    model,
    sketch_name,
    depth,
    direction=True,
    merge=True,
    draft_angle=0.0,
    draft_outward=True,
):
    """
    凸台拉伸

    参数:
        model: IModelDoc2
        sketch_name: 草图名称（如 "Sketch1"）
        depth: 拉伸深度（米）
        direction: True=正方向
        merge: True=合并结果
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: 单向拉伸
        False,        # Flip
        direction,    # Dir: 拉伸方向
        0,            # T1: Blind
        0,            # T2: Blind
        depth,        # D1
        0.0,          # D2
        abs(float(draft_angle)) > 1e-12,  # Dchk1: enable forward draft
        False,        # Dchk2
        bool(draft_outward),  # Ddir1: outward draft
        False,        # Ddir2
        abs(float(draft_angle)),  # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        merge,        # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0: 从草图平面开始
        0.0,          # StartOffset
        False         # FlipStartOffset
    )


def extrude_cut(model, sketch_name, depth, direction=True, flip=False,
                reverse_direction=False):
    """
    切除拉伸

    参数:
        model: IModelDoc2
        sketch_name: 草图名称
        depth: 切除深度（米），0 表示完全贯穿
        direction: True=正方向
        flip: True=翻转切除方向
    """
    _ensure_sketch_selected(model, sketch_name)
    if depth == 0:
        # 完全贯穿
        end_condition = 1  # swEndCondThroughAll
        depth = 0.01  # 占位值
    else:
        end_condition = 0  # swEndCondBlind

    return model.FeatureManager.FeatureCut4(
        direction, flip, bool(reverse_direction),
        end_condition, 0,
        depth, 0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0, False, False
    )


def extrude_midplane(model, sketch_name, total_depth):
    """
    中面拉伸（两侧对称拉伸）

    参数:
        total_depth: 总深度（米），每侧为 total_depth/2
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: 单向定义，终止条件控制为中面
        False,        # Flip
        True,         # Dir
        6,            # T1: swEndCondMidPlane
        0,            # T2
        total_depth,  # D1
        0.0,          # D2
        False,        # Dchk1
        False,        # Dchk2
        False,        # Ddir1
        False,        # Ddir2
        0.0,          # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        True,         # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0
        0.0,          # StartOffset
        False         # FlipStartOffset
    )


def extrude_boss_midplane(model, sketch_name, total_depth, merge=True):
    """Create a symmetric native boss extrusion with the requested total depth."""
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True, False, True,
        6, 0,
        float(total_depth), 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        bool(merge), False, True,
        0, 0.0, False,
    )


def extrude_cut_through_all(model, sketch_name, reverse_direction=False):
    """Create a one-direction native through-all cut."""
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureCut4(
        True, False, bool(reverse_direction),
        1, 0,
        0.01, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0.0, False, False,
    )


def extrude_cut_midplane(model, sketch_name, total_depth,
                         reverse_direction=False):
    """Create a symmetric native cut with the requested total depth."""
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureCut4(
        True, False, bool(reverse_direction),
        6, 0,
        float(total_depth), 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0.0, False, False,
    )


def _revolve_scope_flags(model, affected_bodies):
    """Select explicit revolve scope bodies and return API scope flags."""
    if affected_bodies is None:
        return True, True
    bodies = _as_tuple(affected_bodies)
    if not bodies:
        raise ValueError("affected_bodies cannot be empty")
    for index, body in enumerate(bodies):
        if not _select_com_object_with_data(
            model, body, append=True, mark=1,
        ):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select revolve scope body {index}")
    return True, False


def revolve_feature(model, sketch_name, angle_rad, cut=False,
                    reverse_direction=False, merge=True,
                    affected_bodies=None):
    """Create a native revolve from a sketch containing one centerline axis."""
    _ensure_sketch_selected(model, sketch_name)
    use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
    return model.FeatureManager.FeatureRevolve2(
        True, True, False,
        bool(cut), bool(reverse_direction), False,
        0, 0,
        angle_rad, 0,
        False, False,
        0.0, 0.0,
        0, 0, 0, bool(merge), use_scope, auto_select
    )


def revolve_feature_two_directions(
    model, sketch_name, direction1_angle_rad, direction2_angle_rad, *,
    cut=False, reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a native blind revolve with independent angles in two directions."""
    angle1 = float(direction1_angle_rad)
    angle2 = float(direction2_angle_rad)
    if not (0.0 < angle1 <= math.tau and 0.0 < angle2 <= math.tau):
        raise ValueError("both revolve direction angles must be in (0, 2*pi]")
    if angle1 + angle2 > math.tau + 1e-12:
        raise ValueError("the two revolve angles must not overlap beyond 2*pi")
    _ensure_sketch_selected(model, sketch_name)
    use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
    feature = model.FeatureManager.FeatureRevolve2(
        False, True, False,
        bool(cut), bool(reverse_direction), False,
        0, 0,
        angle1, angle2,
        False, False,
        0.0, 0.0,
        0, 0, 0, bool(merge), use_scope, auto_select,
    )
    if feature is None:
        raise RuntimeError("FeatureRevolve2 returned no two-direction feature")
    return feature


def revolve_feature_midplane(
    model, sketch_name, total_angle_rad, *, cut=False, merge=True,
    affected_bodies=None,
):
    """Create a native mid-plane revolve symmetric about the sketch plane.

    ``total_angle_rad`` is the complete included angle.  SolidWorks revolves
    half of it on either side of the sketch plane.  ``ReverseDir`` has no
    meaning for ``swEndCondMidPlane`` and is therefore always passed as false.
    """
    total_angle = float(total_angle_rad)
    if not 0.0 < total_angle <= math.tau:
        raise ValueError("mid-plane revolve total angle must be in (0, 2*pi]")
    _ensure_sketch_selected(model, sketch_name)
    use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
    feature = model.FeatureManager.FeatureRevolve2(
        True, True, False,
        bool(cut), False, False,
        6, 0,
        total_angle, 0.0,
        False, False,
        0.0, 0.0,
        0, 0.0, 0.0,
        bool(merge), use_scope, auto_select,
    )
    if feature is None:
        raise RuntimeError("FeatureRevolve2 returned no mid-plane feature")
    return feature


def revolve_thin_feature(
    model, sketch_name, direction1_angle_rad, thickness1, *,
    thin_type=0, thickness2=0.0, direction2_angle_rad=None,
    cut=False, reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a native thin revolve from an open profile.

    ``thin_type`` follows ``swThinWallType_e``: 0 one direction, 1 opposite
    direction, 2 mid-plane, and 3 two independent wall thicknesses.  For
    mid-plane, ``thickness1`` is the total wall thickness.
    """
    angle1 = float(direction1_angle_rad)
    angle2 = 0.0 if direction2_angle_rad is None else float(direction2_angle_rad)
    single_direction = direction2_angle_rad is None
    if not 0.0 < angle1 <= math.tau:
        raise ValueError("direction 1 angle must be in (0, 2*pi]")
    if not single_direction:
        if not 0.0 < angle2 <= math.tau:
            raise ValueError("direction 2 angle must be in (0, 2*pi]")
        if angle1 + angle2 > math.tau + 1e-12:
            raise ValueError("the two revolve angles must not overlap beyond 2*pi")
    thin_type = int(thin_type)
    if thin_type not in (0, 1, 2, 3):
        raise ValueError("thin_type must be a swThinWallType_e value 0..3")
    thickness1 = float(thickness1)
    thickness2 = float(thickness2)
    if thickness1 <= 0.0:
        raise ValueError("thin revolve thickness1 must be positive")
    if thin_type == 3:
        if thickness2 <= 0.0:
            raise ValueError("two-direction thin wall requires positive thickness2")
    else:
        thickness2 = 0.0

    _ensure_sketch_selected(model, sketch_name)
    use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
    feature = model.FeatureManager.FeatureRevolve2(
        single_direction, True, True,
        bool(cut), bool(reverse_direction), False,
        0, 0,
        angle1, angle2,
        False, False,
        0.0, 0.0,
        thin_type, thickness1, thickness2,
        bool(merge), use_scope, auto_select,
    )
    if feature is None:
        raise RuntimeError("FeatureRevolve2 returned no thin feature")
    return feature


def revolve_feature_to_reference(
    model, sketch_name, target_reference, end_condition, *,
    offset_distance=0.0, offset_reverse=False, cut=False,
    reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a native one-direction revolve terminated by model geometry.

    ``end_condition`` accepts ``up_to_vertex`` (3), ``up_to_surface`` (4), or
    ``offset_from_surface`` (5).  SolidWorks requires the target reference at
    selection mark 32.
    """
    end_conditions = {
        "up_to_vertex": 3,
        "up_to_surface": 4,
        "offset_from_surface": 5,
    }
    if isinstance(end_condition, str):
        try:
            condition = end_conditions[end_condition.strip().lower()]
        except KeyError as exc:
            raise ValueError(
                "end_condition must be up_to_vertex, up_to_surface, or "
                "offset_from_surface"
            ) from exc
    else:
        condition = int(end_condition)
        if condition not in end_conditions.values():
            raise ValueError("unsupported revolve reference end condition")
    offset_distance = float(offset_distance)
    if condition == 5:
        if offset_distance <= 0.0:
            raise ValueError("offset_from_surface requires a positive offset_distance")
    elif abs(offset_distance) > 1e-15:
        raise ValueError("offset_distance only applies to offset_from_surface")

    _ensure_sketch_selected(model, sketch_name)
    if not _select_com_object_with_data(
        model, target_reference, append=True, mark=32,
    ):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select revolve end reference with mark 32")
    try:
        use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
        feature = model.FeatureManager.FeatureRevolve2(
            True, True, False,
            bool(cut), bool(reverse_direction), False,
            condition, 0,
            0.0, 0.0,
            bool(offset_reverse), False,
            offset_distance, 0.0,
            0, 0.0, 0.0,
            bool(merge), use_scope, auto_select,
        )
        if feature is None:
            raise RuntimeError("FeatureRevolve2 returned no reference-terminated feature")
        return feature
    finally:
        model.ClearSelection2(True)


def revolve_feature_two_directions_to_same_reference(
    model, sketch_name, target_reference, end_condition, *,
    direction2_end_condition=None,
    offset_distance1=0.0, offset_distance2=0.0,
    offset_reverse1=False, offset_reverse2=False,
    cut=False, merge=True, affected_bodies=None,
):
    """Create a two-direction revolve terminated by one shared reference.

    SolidWorks requires the reference to be selected exactly once at mark 32
    with ``BothDirectionUpToSameEntity=True``.  Selecting it separately for
    both directions negates the first selection and prevents feature creation.
    """
    end_conditions = {
        "up_to_vertex": 3,
        "up_to_surface": 4,
        "offset_from_surface": 5,
    }
    def resolve_condition(value):
        if isinstance(value, str):
            try:
                return end_conditions[value.strip().lower()]
            except KeyError as exc:
                raise ValueError(
                    "end condition must be up_to_vertex, up_to_surface, or "
                    "offset_from_surface"
                ) from exc
        resolved = int(value)
        if resolved not in end_conditions.values():
            raise ValueError("unsupported revolve reference end condition")
        return resolved

    condition1 = resolve_condition(end_condition)
    condition2 = resolve_condition(
        end_condition if direction2_end_condition is None
        else direction2_end_condition
    )

    offset1 = float(offset_distance1)
    offset2 = float(offset_distance2)
    for direction, condition, offset in (
        (1, condition1, offset1), (2, condition2, offset2),
    ):
        if condition == 5:
            if offset <= 0.0:
                raise ValueError(
                    f"direction {direction} offset_from_surface requires a positive offset"
                )
        elif abs(offset) > 1e-15:
            raise ValueError(
                f"direction {direction} offset applies only to offset_from_surface"
            )

    _ensure_sketch_selected(model, sketch_name)
    if not _select_com_object_with_data(
        model, target_reference, append=True, mark=32,
    ):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select shared revolve end reference with mark 32")
    try:
        use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
        feature = model.FeatureManager.FeatureRevolve2(
            False, True, False,
            bool(cut), False, True,
            condition1, condition2,
            0.0, 0.0,
            bool(offset_reverse1), bool(offset_reverse2),
            offset1, offset2,
            0, 0.0, 0.0,
            bool(merge), use_scope, auto_select,
        )
        if feature is None:
            raise RuntimeError(
                "FeatureRevolve2 returned no shared-reference two-direction feature"
            )
        return feature
    finally:
        model.ClearSelection2(True)


def revolve_feature_two_references(
    model, sketch_name, direction1_reference, direction2_reference,
    direction1_end_condition, direction2_end_condition, *,
    offset_distance1=0.0, offset_distance2=0.0,
    offset_reverse1=False, offset_reverse2=False,
    cut=False, merge=True, affected_bodies=None,
):
    """Create a two-direction revolve terminated by two distinct references.

    Direction 1 uses selection mark 32 and direction 2 uses the next bitmask,
    mark 64.  The references must represent distinct SolidWorks entities;
    use :func:`revolve_feature_two_directions_to_same_reference` otherwise.
    """
    end_conditions = {
        "up_to_vertex": 3,
        "up_to_surface": 4,
        "offset_from_surface": 5,
    }

    def resolve_condition(value):
        if isinstance(value, str):
            try:
                return end_conditions[value.strip().lower()]
            except KeyError as exc:
                raise ValueError(
                    "end condition must be up_to_vertex, up_to_surface, or "
                    "offset_from_surface"
                ) from exc
        resolved = int(value)
        if resolved not in end_conditions.values():
            raise ValueError("unsupported revolve reference end condition")
        return resolved

    condition1 = resolve_condition(direction1_end_condition)
    condition2 = resolve_condition(direction2_end_condition)
    offset1 = float(offset_distance1)
    offset2 = float(offset_distance2)
    for direction, condition, offset in (
        (1, condition1, offset1), (2, condition2, offset2),
    ):
        if condition == 5:
            if offset <= 0.0:
                raise ValueError(
                    f"direction {direction} offset_from_surface requires a positive offset"
                )
        elif abs(offset) > 1e-15:
            raise ValueError(
                f"direction {direction} offset applies only to offset_from_surface"
            )

    _ensure_sketch_selected(model, sketch_name)
    if not _select_com_object_with_data(
        model, direction1_reference, append=True, mark=32,
    ):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select direction 1 revolve reference with mark 32")
    if not _select_com_object_with_data(
        model, direction2_reference, append=True, mark=64,
    ):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select direction 2 revolve reference with mark 64")
    try:
        use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
        feature = model.FeatureManager.FeatureRevolve2(
            False, True, False,
            bool(cut), False, False,
            condition1, condition2,
            0.0, 0.0,
            bool(offset_reverse1), bool(offset_reverse2),
            offset1, offset2,
            0, 0.0, 0.0,
            bool(merge), use_scope, auto_select,
        )
        if feature is None:
            raise RuntimeError(
                "FeatureRevolve2 returned no two-reference feature"
            )
        return feature
    finally:
        model.ClearSelection2(True)


def revolve_feature_blind_and_reference(
    model, sketch_name, blind_angle_rad, target_reference,
    reference_end_condition, *, blind_in_direction1=True,
    offset_distance=0.0, offset_reverse=False,
    cut=False, reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a two-direction revolve with one blind and one reference end.

    The reference uses mark 32 when it controls direction 1 and mark 64 when
    it controls direction 2.  ``blind_angle_rad`` is assigned to the other
    direction only.
    """
    angle = float(blind_angle_rad)
    if not 0.0 < angle <= math.tau:
        raise ValueError("blind revolve angle must be in (0, 2*pi]")
    end_conditions = {
        "up_to_vertex": 3,
        "up_to_surface": 4,
        "offset_from_surface": 5,
    }
    if isinstance(reference_end_condition, str):
        try:
            condition = end_conditions[reference_end_condition.strip().lower()]
        except KeyError as exc:
            raise ValueError(
                "reference end condition must be up_to_vertex, up_to_surface, "
                "or offset_from_surface"
            ) from exc
    else:
        condition = int(reference_end_condition)
        if condition not in end_conditions.values():
            raise ValueError("unsupported revolve reference end condition")
    offset = float(offset_distance)
    if condition == 5:
        if offset <= 0.0:
            raise ValueError("offset_from_surface requires a positive offset_distance")
    elif abs(offset) > 1e-15:
        raise ValueError("offset_distance only applies to offset_from_surface")

    blind_first = bool(blind_in_direction1)
    condition1, condition2 = (0, condition) if blind_first else (condition, 0)
    angle1, angle2 = (angle, 0.0) if blind_first else (0.0, angle)
    offset1, offset2 = (0.0, offset) if blind_first else (offset, 0.0)
    offset_reverse1, offset_reverse2 = (
        (False, bool(offset_reverse)) if blind_first
        else (bool(offset_reverse), False)
    )
    reference_mark = 64 if blind_first else 32

    _ensure_sketch_selected(model, sketch_name)
    if not _select_com_object_with_data(
        model, target_reference, append=True, mark=reference_mark,
    ):
        model.ClearSelection2(True)
        raise RuntimeError(
            f"failed to select mixed revolve reference with mark {reference_mark}"
        )
    try:
        use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)
        feature = model.FeatureManager.FeatureRevolve2(
            False, True, False,
            bool(cut), bool(reverse_direction), False,
            condition1, condition2,
            angle1, angle2,
            offset_reverse1, offset_reverse2,
            offset1, offset2,
            0, 0.0, 0.0,
            bool(merge), use_scope, auto_select,
        )
        if feature is None:
            raise RuntimeError("FeatureRevolve2 returned no mixed-end feature")
        return feature
    finally:
        model.ClearSelection2(True)


def _revolve_feature_with_axis_selector(
    model, sketch_name, angle_rad, select_axis, *, cut=False,
    reverse_direction=False, merge=True, affected_bodies=None,
):
    """Shared ``FeatureRevolve2`` implementation for independent axis kinds."""
    angle_rad = float(angle_rad)
    if not 0.0 < angle_rad <= math.tau:
        raise ValueError("revolve angle must be in the interval (0, 2*pi]")

    profile = _safe_com_member(model, "FeatureByName", str(sketch_name))
    if profile is None:
        raise RuntimeError(f"revolve profile sketch was not found: {sketch_name}")

    model.ClearSelection2(True)
    try:
        if not _select_com_object(profile, append=False, mark=0):
            raise RuntimeError("failed to select revolve profile sketch with mark 0")

        if not bool(select_axis()):
            raise RuntimeError("failed to select the independent revolve axis")

        use_scope, auto_select = _revolve_scope_flags(model, affected_bodies)

        selection_manager = model.SelectionManager
        selected_count = int(get_com_member(
            selection_manager, "GetSelectedObjectCount2", -1,
        ))
        selection_contract = tuple(
            (
                int(get_com_member(
                    selection_manager, "GetSelectedObjectType3", index, -1,
                )),
                int(get_com_member(
                    selection_manager, "GetSelectedObjectMark", index,
                )),
            )
            for index in range(1, selected_count + 1)
        )
        feature = model.FeatureManager.FeatureRevolve2(
            True, True, False,
            bool(cut), bool(reverse_direction), False,
            0, 0,
            angle_rad, 0,
            False, False,
            0.0, 0.0,
            0, 0, 0, bool(merge), use_scope, auto_select,
        )
        if feature is None:
            raise RuntimeError(
                "FeatureRevolve2 returned no feature; "
                f"selection_contract={selection_contract}"
            )
        return feature
    finally:
        model.ClearSelection2(True)


def revolve_feature_about_axis(
    model, sketch_name, axis_reference, angle_rad, *, cut=False,
    reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a native revolve around an independent datum-axis feature.

    SolidWorks' SW2025 API examples select the profile sketch with mark 0 and
    the independent ``AXIS`` reference with mark 16. ``axis_reference`` may be
    a reference-axis feature object or its exact FeatureManager name.
    """
    if isinstance(axis_reference, str):
        select_axis = lambda: _select_by_id(
            model.Extension, axis_reference, "AXIS", append=True, mark=16,
        )
    else:
        select_axis = lambda: _select_com_object(
            axis_reference, append=True, mark=16,
        )
    return _revolve_feature_with_axis_selector(
        model, sketch_name, angle_rad, select_axis,
        cut=cut, reverse_direction=reverse_direction, merge=merge,
        affected_bodies=affected_bodies,
    )


def revolve_feature_about_sketch_segment(
    model, sketch_name, axis_segment, angle_rad, *, cut=False,
    reverse_direction=False, merge=True, affected_bodies=None,
):
    """Revolve around another sketch's line through a native datum axis.

    SW2025 exposes a segment from another sketch as ``swSelEXTSKETCHSEGS`` and
    ``FeatureRevolve2`` rejects it as a direct axis.  Creating an editable
    datum axis from that line first is the stable native parametric workflow.
    """
    datum_axis = reference_axis_from_sketch_line(model, axis_segment)
    return revolve_feature_about_axis(
        model, sketch_name, datum_axis, angle_rad,
        cut=cut, reverse_direction=reverse_direction, merge=merge,
        affected_bodies=affected_bodies,
    )


def revolve_feature_about_edge(
    model, sketch_name, axis_edge, angle_rad, *, cut=False,
    reverse_direction=False, merge=True, affected_bodies=None,
):
    """Create a native revolve around an existing straight solid edge."""
    edge_geometry(axis_edge)
    return _revolve_feature_with_axis_selector(
        model, sketch_name, angle_rad,
        lambda: _select_com_object_with_data(
            model, axis_edge, append=True, mark=4,
        ),
        cut=cut, reverse_direction=reverse_direction, merge=merge,
        affected_bodies=affected_bodies,
    )


def revolve_boss(model, sketch_name, angle_rad, axis_sketch_name=None):
    """Backward-compatible native boss revolve wrapper.

    ``axis_sketch_name`` was historically unused.  The supported path uses a
    single construction centerline in ``sketch_name`` as the revolve axis.
    """
    if axis_sketch_name not in (None, sketch_name):
        raise ValueError("A separate axis sketch is not supported; use one construction line in the profile sketch")
    return revolve_feature(model, sketch_name, angle_rad, cut=False)


def sweep_feature(model, profile_sketch_name, path_sketch_name, cut=False,
                  merge=True):
    """Create a native sweep using object selections with documented marks.

    Sweep profile uses selection mark 1 and path uses mark 4.  The caller is
    responsible for proving both sketches are fully defined and compatible.
    """
    profile = _safe_com_member(model, "FeatureByName", profile_sketch_name)
    path = _safe_com_member(model, "FeatureByName", path_sketch_name)
    if profile is None or path is None:
        raise RuntimeError("Sweep profile or path sketch was not found")
    model.ClearSelection2(True)
    if not _select_com_object(profile, append=False, mark=1):
        raise RuntimeError("Could not select sweep profile sketch with mark 1")
    if not _select_com_object(path, append=True, mark=4):
        raise RuntimeError("Could not select sweep path sketch with mark 4")
    manager = model.FeatureManager
    if cut:
        return manager.InsertCutSwept(
            True, False, 0, False, False,
            0, 0, False, 0.0, 0.0, 0,
            True, True,
        )
    return manager.InsertProtrusionSwept(
        True, False, 0, False, False,
        0, 0, False, 0.0, 0.0, 0,
        bool(merge), True, True,
    )


def sweep_boss_with_guides(
    model, profile_sketch, path_sketch, guide_curves, *,
    merge=True, twist_control=0, path_alignment=0,
    merge_smooth_faces=True, twist_angle=0.0, direction=0,
):
    """Create a native boss sweep from profile, path, and guide sketches."""
    profile = _feature_object(model, profile_sketch)
    path = _feature_object(model, path_sketch)
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    if not guides:
        raise ValueError("guide-curve sweep requires at least one guide curve")
    twist_control = int(twist_control)
    path_alignment = int(path_alignment)
    twist_angle = float(twist_angle)
    direction = int(direction)
    if direction not in (0, 1, 2):
        raise ValueError("direction must be a swSweepDirection_e value 0..2")
    model.ClearSelection2(True)
    try:
        if not _select_com_object(profile, append=False, mark=1):
            raise RuntimeError("failed to select sweep profile with mark 1")
        if not _select_com_object(path, append=True, mark=4):
            raise RuntimeError("failed to select sweep path with mark 4")
        for index, guide in enumerate(guides):
            if not _select_com_object(guide, append=True, mark=2):
                raise RuntimeError(f"failed to select sweep guide at index {index}")
        feature = model.FeatureManager.InsertProtrusionSwept4(
            False, False, twist_control,
            False, False, 0, 0,
            False, 0.0, 0.0, 0,
            path_alignment, bool(merge), True, True,
            twist_angle, bool(merge_smooth_faces), False, 0.0, direction,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the guide-curve sweep")
    return feature


def sweep_cut_with_guides(
    model, profile_sketch, path_sketch, guide_curves, *,
    twist_control=0, path_alignment=0, merge_smooth_faces=True,
    twist_angle=0.0, direction=0,
):
    """Create a native cut sweep from profile, path, and guide sketches."""
    profile = _feature_object(model, profile_sketch)
    path = _feature_object(model, path_sketch)
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    if not guides:
        raise ValueError("guide-curve cut sweep requires at least one guide curve")
    twist_control = int(twist_control)
    path_alignment = int(path_alignment)
    twist_angle = float(twist_angle)
    direction = int(direction)
    if direction not in (0, 1, 2):
        raise ValueError("direction must be a swSweepDirection_e value 0..2")
    model.ClearSelection2(True)
    try:
        if not _select_com_object(profile, append=False, mark=1):
            raise RuntimeError("failed to select cut-sweep profile with mark 1")
        if not _select_com_object(path, append=True, mark=4):
            raise RuntimeError("failed to select cut-sweep path with mark 4")
        for index, guide in enumerate(guides):
            if not _select_com_object(guide, append=True, mark=2):
                raise RuntimeError(f"failed to select cut-sweep guide at index {index}")
        feature = model.FeatureManager.InsertCutSwept5(
            False, False, twist_control,
            False, False, 0, 0,
            False, 0.0, 0.0, 0,
            path_alignment, True, True,
            twist_angle, bool(merge_smooth_faces),
            False, False, False,
            False, 0.0, direction,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the guide-curve cut sweep")
    return feature


def sweep_thin_feature(
    model, profile_sketch, path_sketch, thickness1, *,
    guide_curves=(), thin_type=0, thickness2=0.0, cut=False,
    merge=True, twist_control=0, path_alignment=0,
    merge_smooth_faces=True, twist_angle=0.0, direction=0,
):
    """Create a native thin boss/cut sweep, optionally with guide curves.

    SOLIDWORKS still requires a closed sketch profile for boss/base and cut
    sweeps; ``ThinFeature`` controls wall offset on that closed profile and does
    not make an open sketch legal.  Open profiles belong to surface sweeps and
    can be thickened as a separate native feature when equivalent geometry is
    required.
    """
    profile = _feature_object(model, profile_sketch)
    path = _feature_object(model, path_sketch)
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    profile_definition = _safe_com_member(profile, "GetSpecificFeature2")
    if profile_definition is not None:
        contours = _as_tuple(_safe_com_member(
            profile_definition, "GetSketchContours", default=(),
        ))
        if contours and any(
            not bool(_safe_com_member(contour, "IsClosed", default=False))
            for contour in contours
        ):
            raise ValueError(
                "solid thin sweep requires closed sketch contours; "
                "use sweep_surface followed by thicken_surface for an open profile"
            )
    thin_type = int(thin_type)
    if thin_type not in (0, 1, 2, 3):
        raise ValueError("thin_type must be a swThinWallType_e value 0..3")
    thickness1 = float(thickness1)
    thickness2 = float(thickness2)
    if thickness1 <= 0.0:
        raise ValueError("thin sweep thickness1 must be positive")
    if thin_type == 3:
        if thickness2 <= 0.0:
            raise ValueError("two-direction thin sweep requires positive thickness2")
    else:
        thickness2 = 0.0
    direction = int(direction)
    if direction not in (0, 1, 2):
        raise ValueError("direction must be a swSweepDirection_e value 0..2")
    twist_control = int(twist_control)
    path_alignment = int(path_alignment)
    twist_angle = float(twist_angle)

    model.ClearSelection2(True)
    try:
        if not _select_com_object(profile, append=False, mark=1):
            raise RuntimeError("failed to select thin-sweep profile with mark 1")
        if not _select_com_object(path, append=True, mark=4):
            raise RuntimeError("failed to select thin-sweep path with mark 4")
        for index, guide in enumerate(guides):
            if not _select_com_object(guide, append=True, mark=2):
                raise RuntimeError(f"failed to select thin-sweep guide at index {index}")
        common = (
            False, False, twist_control,
            False, False, 0, 0,
            True, thickness1, thickness2, thin_type,
            path_alignment,
        )
        simple_contract = not guides and direction == 0 and abs(twist_angle) <= 1e-15
        if cut and simple_contract:
            feature = model.FeatureManager.InsertCutSwept(
                True, False, twist_control,
                False, False, 0, 0,
                True, thickness1, thickness2, thin_type,
                True, True,
            )
        elif cut:
            feature = model.FeatureManager.InsertCutSwept5(
                *common, True, True,
                twist_angle, bool(merge_smooth_faces),
                False, False, False,
                False, 0.0, direction,
            )
        elif simple_contract:
            feature = model.FeatureManager.InsertProtrusionSwept(
                True, False, twist_control,
                False, False, 0, 0,
                True, thickness1, thickness2, thin_type,
                bool(merge), True, True,
            )
        else:
            feature = model.FeatureManager.InsertProtrusionSwept4(
                *common, bool(merge), True, True,
                twist_angle, bool(merge_smooth_faces),
                False, 0.0, direction,
            )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the thin sweep")
    return feature


def sweep_feature_advanced(
    model, profile_sketch, path_sketch, *, guide_curves=(), cut=False,
    merge=True, twist_control=0, twist_angle=0.0,
    path_alignment=0, direction=0, merge_smooth_faces=True,
):
    """Create a non-thin sweep with explicit direction and twist controls."""
    profile = _feature_object(model, profile_sketch)
    path = _feature_object(model, path_sketch)
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    twist_control = int(twist_control)
    valid_twist = {0, 1, 2, 3, 8, 9}
    if twist_control not in valid_twist:
        raise ValueError("unsupported swTwistControlType_e value")
    twist_angle = float(twist_angle)
    if not math.isfinite(twist_angle):
        raise ValueError("twist_angle must be finite")
    if twist_control not in (8, 9) and abs(twist_angle) > 1e-15:
        raise ValueError("twist_angle applies only to constant-twist controls 8 or 9")
    direction = int(direction)
    if direction not in (0, 1, 2):
        raise ValueError("direction must be a swSweepDirection_e value 0..2")
    path_alignment = int(path_alignment)
    if path_alignment not in (0, 2, 3):
        raise ValueError("path_alignment must be 0, 2, or 3")

    model.ClearSelection2(True)
    try:
        if not _select_com_object(profile, append=False, mark=1):
            raise RuntimeError("failed to select advanced-sweep profile with mark 1")
        if not _select_com_object(path, append=True, mark=4):
            raise RuntimeError("failed to select advanced-sweep path with mark 4")
        for index, guide in enumerate(guides):
            if not _select_com_object(guide, append=True, mark=2):
                raise RuntimeError(f"failed to select advanced-sweep guide {index}")
        common = (
            False, False, twist_control,
            False, False, 0, 0,
            False, 0.0, 0.0, 0,
            path_alignment,
        )
        if cut:
            feature = model.FeatureManager.InsertCutSwept5(
                *common, True, True,
                twist_angle, bool(merge_smooth_faces),
                False, False, False,
                False, 0.0, direction,
            )
        else:
            feature = model.FeatureManager.InsertProtrusionSwept4(
                *common, bool(merge), True, True,
                twist_angle, bool(merge_smooth_faces),
                False, 0.0, direction,
            )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the advanced sweep")
    return feature


def offset_plane(model, base_plane_name, distance, reverse_direction=False):
    """Create a native distance-offset reference plane from a named plane."""
    model.ClearSelection2(True)
    selected = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(base_plane_name), "PLANE"
    )
    if not selected:
        raise RuntimeError(f"Could not select base plane: {base_plane_name}")
    constraint = 8 | (256 if reverse_direction else 0)
    return model.FeatureManager.InsertRefPlane(
        constraint, float(distance), 0, 0.0, 0, 0.0
    )


def constraint_reference_plane(model, references):
    """Create a native plane from one to three explicitly marked references.

    Each reference is ``(entity, constraint, angle_or_distance)``. Constraint
    values follow the SW2025 ``swRefPlaneReferenceConstraints_e`` type library:
    parallel=1, perpendicular=2, coincident=4, distance=8, angle=16,
    tangent=32, project=64, and mid-plane=128. Option flags can be ORed into
    the relevant constraint value.
    """
    items = tuple(references)
    if not 1 <= len(items) <= 3:
        raise ValueError("reference plane requires one to three references")
    normalized = []
    for index, item in enumerate(items):
        if len(item) != 3:
            raise ValueError(
                "each reference plane item must contain entity, constraint, and value"
            )
        entity, constraint, value = item
        if entity is None or int(constraint) == 0:
            raise ValueError(f"reference plane item {index} is invalid")
        normalized.append((entity, int(constraint), float(value)))
    model.ClearSelection2(True)
    try:
        for index, (entity, _constraint, _value) in enumerate(normalized):
            if not _select_com_object(entity, append=index > 0, mark=index):
                raise RuntimeError(
                    f"failed to select reference plane entity {index} with mark {index}"
                )
        parameters = []
        for _entity, constraint, value in normalized:
            parameters.extend((constraint, value))
        while len(parameters) < 6:
            parameters.extend((0, 0.0))
        plane = model.FeatureManager.InsertRefPlane(*parameters)
        if plane is None:
            raise RuntimeError("SolidWorks did not create the constraint reference plane")
        return plane
    finally:
        model.ClearSelection2(True)


def reference_plane_geometry(reference_plane):
    """Read a reference plane's world origin and normal from its Transform."""
    transform = get_com_member(reference_plane, "Transform")
    data = tuple(float(value) for value in (get_com_member(transform, "ArrayData") or ()))
    if len(data) < 12:
        raise RuntimeError(f"reference plane transform is incomplete: {data}")
    normal = data[6:9]
    magnitude = math.sqrt(sum(value * value for value in normal))
    if magnitude <= 1e-12:
        raise RuntimeError("reference plane transform has a zero normal")
    return {
        "origin": data[9:12],
        "normal": tuple(value / magnitude for value in normal),
        "transform": data,
    }


def reference_plane_through_three_vertices(model, first, second, third):
    """Create a native plane coincident with three non-collinear vertices."""
    return constraint_reference_plane(
        model,
        ((first, 4, 0.0), (second, 4, 0.0), (third, 4, 0.0)),
    )


def reference_plane_at_angle(
    model, planar_reference, hinge_reference, angle_radians, *, flip=False,
):
    """Create a native plane angled from a plane/face about a coincident hinge."""
    angle = float(angle_radians)
    if not math.isfinite(angle) or not 0.0 < angle < math.pi:
        raise ValueError("reference plane angle must be between 0 and pi radians")
    return constraint_reference_plane(
        model,
        (
            (planar_reference, 16 | (256 if flip else 0), angle),
            (hinge_reference, 4, 0.0),
        ),
    )


def reference_midplane(model, first_planar_reference, second_planar_reference):
    """Create a native mid-plane between two planar references."""
    return constraint_reference_plane(
        model,
        (
            (first_planar_reference, 128, 0.0),
            (second_planar_reference, 128, 0.0),
        ),
    )


def reference_plane_tangent_parallel(
    model, curved_face, planar_reference, *, flip=False,
):
    """Create a native plane tangent to a curved face and parallel to a plane."""
    surface = get_com_member(curved_face, "GetSurface")
    if surface is None or not (
        bool(_safe_com_member(surface, "IsCylinder", default=False))
        or bool(_safe_com_member(surface, "IsCone", default=False))
    ):
        raise ValueError("tangent reference plane requires a cylindrical or conical face")
    return constraint_reference_plane(
        model,
        (
            (curved_face, 32 | (256 if flip else 0), 0.0),
            (planar_reference, 1, 0.0),
        ),
    )


def reference_plane_tangent_at_projected_point(
    model, curved_face, sketch_point_reference, *, projection="nearest", flip=False,
):
    """Create a tangent plane where a sketch point projects onto a surface.

    ``projection='nearest'`` uses SolidWorks' nearest-location on-surface
    solution.  ``projection='sketch_normal'`` projects along the source sketch
    normal and requires that ray to intersect the selected curved face.
    """
    modes = {"nearest": 1024, "sketch_normal": 2048}
    if projection not in modes:
        raise ValueError("projection must be nearest or sketch_normal")
    surface = get_com_member(curved_face, "GetSurface")
    if surface is None or not (
        bool(_safe_com_member(surface, "IsCylinder", default=False))
        or bool(_safe_com_member(surface, "IsCone", default=False))
    ):
        raise ValueError("projected tangent plane requires a cylindrical or conical face")
    return constraint_reference_plane(
        model,
        (
            (curved_face, 32 | (256 if flip else 0), 0.0),
            (sketch_point_reference, 64 | modes[projection], 0.0),
        ),
    )


def reference_plane_normal_to_curve(model, curve_reference, point_reference, *, flip=False):
    """Create a native plane normal to a curve at an explicit point on it."""
    return constraint_reference_plane(
        model,
        (
            (curve_reference, 2 | (256 if flip else 0), 0.0),
            (point_reference, 4, 0.0),
        ),
    )


def reference_plane_parallel_through_point(
    model, planar_reference, point_reference, *, flip=False,
):
    """Create a native plane parallel to a plane/face through a point."""
    return constraint_reference_plane(
        model,
        (
            (planar_reference, 1 | (256 if flip else 0), 0.0),
            (point_reference, 4, 0.0),
        ),
    )


def _feature_after_legacy_insert(model, before_last, result, operation):
    """Recover a feature created by a boolean/HRESULT-style legacy API."""
    feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if result is False or feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError(f"SolidWorks did not create the {operation}")
    return feature


def reference_points(
    model, selections, point_type, *, along_curve_type=0,
    distance_or_percent=0.0, count=1,
):
    """Create native reference points with ``InsertReferencePoint``.

    ``point_type`` uses verified SW2025 ``swRefPointType_e`` values 2..7.
    The returned value is always a tuple because along-curve creation can
    produce multiple reference-point features.
    """
    values = _as_tuple(selections)
    if not values:
        raise ValueError("reference point requires at least one selection")
    point_type, along_curve_type, count = int(point_type), int(along_curve_type), int(count)
    if point_type not in range(2, 8):
        raise ValueError("point_type must be a valid swRefPointType_e value 2..7")
    if along_curve_type not in (0, 1, 2):
        raise ValueError("along_curve_type must be distance, percentage, or evenly distributed")
    if count < 1:
        raise ValueError("reference point count must be at least 1")
    model.ClearSelection2(True)
    for index, entity in enumerate(values):
        if not _select_com_object(entity, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select reference-point entity {index}")
    try:
        features = _as_tuple(model.FeatureManager.InsertReferencePoint(
            point_type, along_curve_type, float(distance_or_percent), count
        ))
    finally:
        model.ClearSelection2(True)
    if not features:
        raise RuntimeError("SolidWorks did not create a reference point")
    return features


def reference_point_face_center(model, face):
    """Create one native reference point at a selected face center."""
    return reference_points(model, face, 4)[0]


def reference_point_edge_center(model, edge):
    """Create one native reference point at the center of a circular edge."""
    circular_edge_geometry(edge)
    return reference_points(model, edge, 3)[0]


def reference_point_along_curve(
    model, curve, value=0.5, *, mode="percentage", count=1,
):
    """Create native point geometry along a selected edge or curve."""
    modes = {"distance": 0, "percentage": 1, "evenly_distributed": 2}
    if mode not in modes:
        raise ValueError(f"unsupported along-curve reference point mode: {mode}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value) or numeric_value < 0.0:
        raise ValueError("along-curve distance or percentage must be finite and non-negative")
    if mode == "percentage" and numeric_value > 100.0:
        raise ValueError("along-curve percentage must be between 0 and 100")
    return reference_points(
        model, curve, 2, along_curve_type=modes[mode],
        distance_or_percent=numeric_value, count=count,
    )


def reference_point_face_vertex_projection(model, face, vertex):
    """Project a selected vertex normally onto a selected face."""
    return reference_points(model, (face, vertex), 5)[0]


def reference_point_intersection(model, first, second):
    """Create a native point at the intersection of two selected entities."""
    return reference_points(model, (first, second), 6)[0]


def reference_point_from_sketch_point(model, sketch_point_entity):
    """Create a native reference point from a selected sketch point."""
    return reference_points(model, sketch_point_entity, 7)[0]


def reference_point_geometry(feature):
    """Read a native reference point feature's model-space coordinates."""
    specific = get_com_member(feature, "GetSpecificFeature2")
    math_point = get_com_member(specific, "GetRefPoint")
    point = tuple(float(value) for value in get_com_member(math_point, "ArrayData")[:3])
    if len(point) != 3:
        raise RuntimeError("reference point did not return three coordinates")
    return point


def reference_plane_normal_at_curve_location(
    model, curve_reference, value=50.0, *, mode="percentage", flip=False,
):
    """Create a native point on a curve and a plane normal through that point.

    Both features remain in FeatureManager, so the location is driven by the
    curve reference and the point's native distance/percentage definition.
    """
    point_feature = reference_point_along_curve(
        model, curve_reference, value, mode=mode, count=1,
    )[0]
    plane_feature = reference_plane_normal_to_curve(
        model, curve_reference, point_feature, flip=flip,
    )
    return point_feature, plane_feature


def reference_axis(model, references, *, auto_size=True):
    """Create a native selection-driven reference axis from one or two entities."""
    entities = _as_tuple(references)
    if not 1 <= len(entities) <= 2 or any(entity is None for entity in entities):
        raise ValueError("reference axis requires one or two valid reference entities")
    model.ClearSelection2(True)
    for index, entity in enumerate(entities):
        if not _select_com_object(entity, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select reference-axis entity {index}")
    before_last = _last_model_feature(model)
    try:
        result = get_com_member(model, "InsertAxis2", bool(auto_size))
        return _feature_after_legacy_insert(model, before_last, result, "reference axis")
    finally:
        model.ClearSelection2(True)


def reference_axis_from_vertices(model, first_vertex, second_vertex, *, auto_size=True):
    """Create a native reference axis through two geometrically distinct vertices."""
    first_point = vertex_geometry(first_vertex)["point"]
    second_point = vertex_geometry(second_vertex)["point"]
    if math.dist(first_point, second_point) <= 1e-12:
        raise ValueError("reference axis requires two distinct vertices")
    return reference_axis(model, (first_vertex, second_vertex), auto_size=auto_size)


def reference_axis_from_planes(model, first_plane, second_plane, *, auto_size=True):
    """Create a native reference axis at the intersection of two planes/faces."""
    return reference_axis(model, (first_plane, second_plane), auto_size=auto_size)


def reference_axis_from_cylindrical_face(model, cylindrical_face, *, auto_size=True):
    """Create a native reference axis from one cylindrical or conical face."""
    cylindrical_face_geometry(cylindrical_face)
    return reference_axis(model, cylindrical_face, auto_size=auto_size)


def reference_axis_from_conical_face(model, conical_face, *, auto_size=True):
    """Create a native reference axis from one conical face."""
    conical_face_geometry(conical_face)
    return reference_axis(model, conical_face, auto_size=auto_size)


def reference_axis_from_point_and_plane(model, point_reference, planar_reference, *, auto_size=True):
    """Create a native axis through a point and normal to a planar reference."""
    return reference_axis(
        model, (point_reference, planar_reference), auto_size=auto_size,
    )


def reference_axis_from_straight_edge(model, edge, *, auto_size=True):
    """Create a native reference axis coincident with a straight solid edge."""
    edge_geometry(edge)
    return reference_axis(model, edge, auto_size=auto_size)


def reference_axis_from_sketch_line(model, sketch_segment, *, auto_size=True):
    """Create a native reference axis coincident with a straight sketch line."""
    segment_type = int(get_com_member(sketch_segment, "GetType"))
    if segment_type != 0:
        raise ValueError("reference axis sketch segment must be a straight line")
    return reference_axis(model, sketch_segment, auto_size=auto_size)


def coordinate_system_numeric(model, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    """Create a native coordinate system from location and XYZ rotations."""
    location = tuple(float(value) for value in location)
    rotation = tuple(float(value) for value in rotation)
    if len(location) != 3 or len(rotation) != 3:
        raise ValueError("location and rotation must each contain three values")
    if not all(math.isfinite(value) for value in (*location, *rotation)):
        raise ValueError("location and rotation must be finite")
    feature = model.FeatureManager.CreateCoordinateSystemUsingNumericalValues(
        any(value != 0.0 for value in location), *location,
        any(value != 0.0 for value in rotation), *rotation,
    )
    if feature is None:
        raise RuntimeError("SolidWorks did not create the coordinate system")
    return feature


SCALE_TYPES = {"centroid": 0, "origin": 1, "coordinate_system": 2}


def scale_feature(
    model, x_factor, y_factor=None, z_factor=None, *, about="centroid", bodies=None,
    coordinate_system=None,
):
    """Create an editable native Scale feature for all or selected bodies.

    Supplying only ``x_factor`` creates a uniform scale.  Supplying both
    ``y_factor`` and ``z_factor`` creates a non-uniform XYZ scale.  The stable
    ``about="coordinate_system"`` requires a native coordinate-system feature.
    Bodies and the coordinate-system reference are selected together, allowing
    the same operation to target either every body or an explicit body subset.
    """
    if about not in SCALE_TYPES:
        raise ValueError("about must be 'centroid', 'origin', or 'coordinate_system'")
    if about == "coordinate_system" and coordinate_system is None:
        raise ValueError("coordinate_system is required for coordinate-system scaling")
    if about != "coordinate_system" and coordinate_system is not None:
        raise ValueError("coordinate_system is only valid when about='coordinate_system'")
    if (y_factor is None) != (z_factor is None):
        raise ValueError("non-uniform scaling requires both y_factor and z_factor")
    uniform = y_factor is None
    x_value = _positive_finite("x_factor", x_factor)
    y_value = x_value if uniform else _positive_finite("y_factor", y_factor)
    z_value = x_value if uniform else _positive_finite("z_factor", z_factor)
    selected_bodies = _as_tuple(bodies) if bodies is not None else ()

    model.ClearSelection2(True)
    try:
        append = False
        if coordinate_system is not None:
            if not _select_com_object(coordinate_system, append=False, mark=0):
                raise RuntimeError("failed to select Scale coordinate system")
            append = True
        for index, body in enumerate(selected_bodies):
            if not _select_com_object(body, append=append or index > 0, mark=0):
                raise RuntimeError(f"failed to select Scale body {index}")
        before_last = _last_model_feature(model)
        feature = model.FeatureManager.InsertScale(
            SCALE_TYPES[about], bool(uniform), x_value, y_value, z_value,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Scale feature")
    return feature


def scale_feature_evidence(feature):
    """Read native IScaleFeatureData values without relying on display names."""
    if feature is None:
        raise ValueError("feature is required")
    data = get_com_member(feature, "GetDefinition")
    if data is None:
        raise RuntimeError("Scale feature did not return IScaleFeatureData")
    uniform = bool(get_com_member(data, "IsUniform"))
    if uniform:
        factor = float(get_com_member(data, "ScaleUniform"))
        factors = (factor, factor, factor)
    else:
        factors = (
            float(get_com_member(data, "ScaleX")),
            float(get_com_member(data, "ScaleY")),
            float(get_com_member(data, "ScaleZ")),
        )
    selected_body_count = int(get_com_member(data, "GetBodiesCount"))
    coordinate_system = _safe_com_member(data, "CoordinateSystem")
    if coordinate_system is None:
        coordinate_system_name = ""
    elif isinstance(coordinate_system, str):
        coordinate_system_name = coordinate_system
    else:
        coordinate_system_name = str(
            _safe_com_member(coordinate_system, "Name", default="") or ""
        )
    return {
        "feature": str(get_com_member(feature, "Name") or ""),
        "type": int(get_com_member(data, "Type")),
        "about": {0: "centroid", 1: "origin", 2: "coordinate_system"}.get(
            int(get_com_member(data, "Type")), "unknown"
        ),
        "uniform": uniform,
        "factors": factors,
        "coordinate_system": coordinate_system_name,
        "selected_body_count": selected_body_count,
        "scope": "all_bodies" if selected_body_count == 0 else "selected_bodies",
        "error_code": int(get_com_member(feature, "GetErrorCode") or 0),
    }


def dome_feature(model, faces, height, *, reverse_direction=False, elliptical=False):
    """Create an editable native Dome feature on one or more selected faces.

    ``IModelDoc2.InsertDome`` is a void method in the SW2025 type library, so
    success is established from the newly appended FeatureManager item rather
    than from its direct return value.
    """
    selected_faces = _as_tuple(faces)
    if not selected_faces:
        raise ValueError("at least one face is required for a Dome feature")
    height_value = _positive_finite("height", height)

    model.ClearSelection2(True)
    before_last = _last_model_feature(model)
    try:
        for index, face in enumerate(selected_faces):
            if not _select_com_object_with_data(
                model, face, append=index > 0, mark=1,
            ):
                raise RuntimeError(f"failed to select Dome face {index}")
        selection_count = _get_selection_count(model)
        selection_types = tuple(
            int(_safe_com_member(
                model.SelectionManager, "GetSelectedObjectType3", index, -1,
                default=-1,
            ))
            for index in range(1, selection_count + 1)
        )
        model.InsertDome(
            height_value, bool(reverse_direction), bool(elliptical),
        )
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
        if feature is None:
            feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError(
            "SolidWorks did not create the Dome feature; "
            f"selected={selection_count}, types={selection_types}"
        )
    return feature


def dome_feature_evidence(feature, model=None):
    """Read the native IDomeFeatureData2 parameters and feature status."""
    if feature is None:
        raise ValueError("feature is required")
    data = get_com_member(feature, "GetDefinition")
    if data is None:
        raise RuntimeError("Dome feature did not return IDomeFeatureData2")
    data = _typed_sldworks_interface(data, "IDomeFeatureData2")
    accessed = False
    if model is not None and getattr(data, "AccessSelections", None) is not None:
        try:
            accessed = bool(data.AccessSelections(model, None))
        except Exception:
            accessed = bool(data.AccessSelections(model, _empty_callout()))
        if not accessed:
            raise RuntimeError("Dome FeatureData selections could not be accessed")
    try:
        face_count = int(_safe_com_member(data, "GetFaceCount", default=0) or 0)
        return {
            "feature": str(get_com_member(feature, "Name") or ""),
            "height": float(get_com_member(data, "Height")),
            "reverse_direction": bool(get_com_member(data, "ReverseDir")),
            "elliptical": bool(get_com_member(data, "Elliptical")),
            "face_count": face_count,
            "has_constraint": _safe_com_member(data, "ConstraintPointOrSketch") is not None,
            "has_direction": _safe_com_member(data, "Direction") is not None,
            "error_code": int(get_com_member(feature, "GetErrorCode") or 0),
        }
    finally:
        if accessed:
            data.ReleaseSelectionAccess()


def update_dome_feature(
    feature, model, *, height=None, reverse_direction=None, elliptical=None,
    constraint=None, direction=None,
):
    """Edit supported native IDomeFeatureData2 parameters in place.

    ``constraint`` accepts a sketch point or sketch reference supported by
    SolidWorks. ``direction`` accepts a valid direction entity such as an edge.
    Passing ``None`` leaves the corresponding reference unchanged.
    """
    if feature is None or model is None:
        raise ValueError("feature and model are required")
    data = get_com_member(feature, "GetDefinition")
    if data is None:
        raise RuntimeError("Dome feature did not return IDomeFeatureData2")
    data = _typed_sldworks_interface(data, "IDomeFeatureData2")
    try:
        accessed = bool(data.AccessSelections(model, None))
    except Exception:
        accessed = bool(data.AccessSelections(model, _empty_callout()))
    if not accessed:
        raise RuntimeError("Dome FeatureData selections could not be accessed")
    try:
        if height is not None:
            data.Height = _positive_finite("height", height)
        if reverse_direction is not None:
            data.ReverseDir = bool(reverse_direction)
        if elliptical is not None:
            data.Elliptical = bool(elliptical)
        if constraint is not None:
            data.ConstraintPointOrSketch = constraint
        if direction is not None:
            data.Direction = direction
        try:
            modified = bool(feature.ModifyDefinition(data, model, None))
        except Exception:
            modified = bool(feature.ModifyDefinition(data, model, _empty_callout()))
    finally:
        try:
            data.ReleaseSelectionAccess()
        except Exception:
            pass
    if not modified:
        raise RuntimeError("SolidWorks did not update the Dome feature definition")
    return feature


def indent_feature(
    model, target_body, tool_regions, *, thickness=0.0, clearance=0.0,
    exclude_selected_regions=True, clearance_direction=True,
    cut=False, cut_direction=False,
):
    """Create a native multi-body Indent feature.

    The official contract uses selection mark 1 for the target body and mark 4
    for each tool-body face, body, or other supported region object.
    """
    if target_body is None:
        raise ValueError("target_body is required")
    regions = _as_tuple(tool_regions)
    if not regions:
        raise ValueError("at least one tool region is required")
    thickness_value = float(thickness)
    clearance_value = float(clearance)
    if not math.isfinite(thickness_value) or thickness_value < 0.0:
        raise ValueError("thickness must be a finite non-negative value")
    if not math.isfinite(clearance_value) or clearance_value < 0.0:
        raise ValueError("clearance must be a finite non-negative value")
    if thickness_value <= 0.0:
        raise ValueError(
            "Indent requires a positive thickness argument; SW2025 also "
            "requires a positive placeholder in cut mode"
        )

    model.ClearSelection2(True)
    try:
        if not _select_com_object_with_data(
            model, target_body, append=False, mark=1, select2_with_data=True,
        ):
            raise RuntimeError("failed to select Indent target body")
        for index, region in enumerate(regions):
            if not _select_com_object_with_data(model, region, append=True, mark=4):
                raise RuntimeError(f"failed to select Indent tool region {index}")
        selection_count = _get_selection_count(model)
        selection_types = tuple(
            int(_safe_com_member(
                model.SelectionManager, "GetSelectedObjectType3", index, -1,
                default=-1,
            ))
            for index in range(1, selection_count + 1)
        )
        feature = _typed_sldworks_feature_manager(model.FeatureManager).InsertIndent(
            thickness_value,
            clearance_value,
            bool(exclude_selected_regions),
            bool(clearance_direction),
            bool(cut),
            bool(cut_direction),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError(
            "SolidWorks did not create the Indent feature; "
            f"selected={selection_count}, types={selection_types}"
        )
    return feature


def indent_feature_evidence(feature, model=None):
    """Read native IIndentFeatureData parameters and selection scope."""
    if feature is None:
        raise ValueError("feature is required")
    data = get_com_member(feature, "GetDefinition")
    if data is None:
        raise RuntimeError("Indent feature did not return IIndentFeatureData")
    data = _typed_sldworks_interface(data, "IIndentFeatureData")
    accessed = False
    if model is not None:
        try:
            accessed = bool(data.AccessSelections(model, None))
        except Exception:
            accessed = bool(data.AccessSelections(model, _empty_callout()))
        if not accessed:
            raise RuntimeError("Indent FeatureData selections could not be accessed")
    try:
        target_body = _safe_com_member(data, "TargetBody")
        tool_regions = _as_tuple(_safe_com_member(data, "ToolBodyRegion"))
        return {
            "feature": str(get_com_member(feature, "Name") or ""),
            "thickness": float(get_com_member(data, "Thickness")),
            "clearance": float(get_com_member(data, "Clearance")),
            "selection_state": int(get_com_member(data, "SelectionState")),
            "clearance_direction": bool(get_com_member(data, "ClearanceDirection")),
            "is_cut": bool(get_com_member(data, "IsCut")),
            "cut_direction": bool(get_com_member(data, "CutDirection")),
            "body_count": int(get_com_member(data, "GetBodiesCount")),
            "target_body": str(_safe_com_member(target_body, "Name", default="") or ""),
            "tool_region_count": len(tool_regions),
            "error_code": int(get_com_member(feature, "GetErrorCode") or 0),
        }
    finally:
        if accessed:
            data.ReleaseSelectionAccess()


FLEX_TYPES = {"bending": 0, "twisting": 1, "tapering": 2, "stretching": 3}


def _finite_xyz(name, values, *, normalize=False):
    result = tuple(float(value) for value in values)
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain three finite values")
    if normalize:
        magnitude = math.sqrt(sum(value * value for value in result))
        if magnitude <= 0.0:
            raise ValueError(f"{name} must be a non-zero vector")
        result = tuple(value / magnitude for value in result)
    return result


def flex_feature(
    model, body, mode, amount, *, rotation_axis=(1.0, 0.0, 0.0),
    tangent_axis=(0.0, 1.0, 0.0), radius_axis=(0.0, 0.0, 1.0),
    pivot=(0.0, 0.0, 0.0), left_trim=0.05, right_trim=0.05,
    hard_edges=False,
):
    """Create a native Flex feature for one selected solid or surface body.

    Modes follow the documented SW contract: bending=0, twisting=1,
    tapering=2, stretching=3. ``amount`` is forwarded to the legacy API's
    ``Angle`` parameter; bend/twist/taper use radians, while SW2025 normalizes
    stretch to the resulting axial distance exposed as display dimension D0.
    ``left_trim``
    and ``right_trim`` are non-negative distances measured independently from
    the two trim sides. Axis roles must match the intended deformation axis.
    """
    key = str(mode).strip().lower()
    if key not in FLEX_TYPES:
        raise ValueError("mode must be bending, twisting, tapering, or stretching")
    if body is None:
        raise ValueError("body is required")
    rotation_values = _finite_xyz("rotation_axis", rotation_axis, normalize=True)
    tangent_values = _finite_xyz("tangent_axis", tangent_axis, normalize=True)
    radius_values = _finite_xyz("radius_axis", radius_axis, normalize=True)
    axes = (
        ("rotation_axis", rotation_values),
        ("tangent_axis", tangent_values),
        ("radius_axis", radius_values),
    )
    for left_index in range(len(axes)):
        for right_index in range(left_index + 1, len(axes)):
            left_name, left_axis = axes[left_index]
            right_name, right_axis = axes[right_index]
            if abs(sum(a * b for a, b in zip(left_axis, right_axis))) > 1e-6:
                raise ValueError(f"{left_name} and {right_name} must be perpendicular")
    pivot_values = _finite_xyz("pivot", pivot)
    amount_value = float(amount)
    left_value = float(left_trim)
    right_value = float(right_trim)
    if not all(math.isfinite(value) for value in (amount_value, left_value, right_value)):
        raise ValueError("amount and trim distances must be finite")
    if left_value < 0.0 or right_value < 0.0:
        raise ValueError("left_trim and right_trim must be non-negative distances")
    if left_value == 0.0 and right_value == 0.0:
        raise ValueError("at least one Flex trim distance must be positive")

    model.ClearSelection2(True)
    try:
        if not _select_com_object_with_data(
            model, body, append=False, mark=1, select2_with_data=True,
        ):
            raise RuntimeError("failed to select Flex body")
        selection_count = _get_selection_count(model)
        selection_types = tuple(
            int(_safe_com_member(
                model.SelectionManager, "GetSelectedObjectType3", index, -1,
                default=-1,
            ))
            for index in range(1, selection_count + 1)
        )
        feature = _typed_sldworks_feature_manager(model.FeatureManager).InsertFlexFeature(
            *rotation_values,
            *tangent_values,
            *radius_values,
            amount_value,
            *pivot_values,
            FLEX_TYPES[key],
            left_value,
            right_value,
            bool(hard_edges),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError(
            "SolidWorks did not create the Flex feature; "
            f"selected={selection_count}, types={selection_types}, mark=1, mode={key}"
        )
    return feature


def flex_feature_evidence(feature, model):
    """Read the native Flex feature state and resulting body geometry."""
    if feature is None or model is None:
        raise ValueError("feature and model are required")
    body_rows = []
    for body in _as_tuple(get_com_member(model, "GetBodies2", 0, False)):
        properties = _as_tuple(get_com_member(body, "GetMassProperties", 1.0))
        body_rows.append({
            "volume": float(properties[3]),
            "box": tuple(float(value) for value in get_com_member(body, "GetBodyBox")),
        })
    dimensions = []
    display_dimension = _safe_com_member(
        feature, "GetFirstDisplayDimension", default=None,
    )
    while display_dimension is not None:
        dimension = _safe_com_member(
            display_dimension, "GetDimension2", 0, default=None,
        )
        if dimension is not None:
            dimensions.append({
                "name": str(_safe_com_member(dimension, "Name", default="") or ""),
                "system_value": float(_safe_com_member(
                    dimension, "SystemValue", default=0.0,
                )),
            })
        display_dimension = _safe_com_member(
            feature, "GetNextDisplayDimension", display_dimension, default=None,
        )
    return {
        "feature": str(get_com_member(feature, "Name") or ""),
        "type": str(get_com_member(feature, "GetTypeName2") or ""),
        "error_code": int(get_com_member(feature, "GetErrorCode") or 0),
        "dimensions": tuple(dimensions),
        "body_count": len(body_rows),
        "bodies": tuple(body_rows),
    }


def combine_bodies(model, operation, bodies, *, main_body=None):
    """Create a native Combine feature for solid bodies.

    ``operation`` is one of the verified SW2025 ``swBodyOperationType_e``
    values: 15901 intersect, 15902 cut, or 15903 add.
    """
    operation = int(operation)
    if operation not in (15901, 15902, 15903):
        raise ValueError("operation must be SWBODYINTERSECT, SWBODYCUT, or SWBODYADD")
    values = _as_tuple(bodies)
    if operation == 15902:
        if main_body is None:
            raise ValueError("cut combine requires main_body")
        tools = tuple(body for body in values if body is not main_body)
        if not tools:
            raise ValueError("cut combine requires at least one distinct tool body")
        main_arg = main_body
    else:
        if len(values) < 2:
            raise ValueError("add/intersect combine requires at least two bodies")
        tools = values
        main_arg = _empty_callout()
    feature = model.FeatureManager.InsertCombineFeature(
        operation, main_arg, _dispatch_array(tools)
    )
    if feature is None:
        raise RuntimeError("SolidWorks did not create the Combine feature")
    return feature


def rollback_to_feature(model, feature_or_name, *, before=True):
    """Move the native rollback bar immediately before or after a feature."""
    feature = _feature_object(model, feature_or_name)
    name = str(get_com_member(feature, "Name"))
    location = 3 if before else 4
    if not bool(model.FeatureManager.EditRollback(location, name)):
        raise RuntimeError(f"SolidWorks could not move rollback bar near {name}")
    return feature


def rollback_to_end(model):
    """Restore the native rollback bar to the end of the feature tree."""
    if not bool(model.FeatureManager.EditRollback(1, "")):
        raise RuntimeError("SolidWorks could not move rollback bar to end")
    return True


def move_copy_bodies(
    model, bodies, *, translation=(0.0, 0.0, 0.0),
    rotation_origin=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
    copy=False, copies=1,
):
    """Create a native Move/Copy Body feature with explicit transforms."""
    values = _as_tuple(bodies)
    if not values:
        raise ValueError("at least one body is required")
    translation = tuple(float(value) for value in translation)
    rotation_origin = tuple(float(value) for value in rotation_origin)
    rotation = tuple(float(value) for value in rotation)
    if any(len(group) != 3 for group in (translation, rotation_origin, rotation)):
        raise ValueError("translation, rotation_origin and rotation require three values")
    if not all(math.isfinite(value) for value in (*translation, *rotation_origin, *rotation)):
        raise ValueError("move/copy transform values must be finite")
    copies = int(copies)
    if copies < 1:
        raise ValueError("copies must be at least 1")
    model.ClearSelection2(True)
    for index, body in enumerate(values):
        if not _select_com_object(body, append=index > 0, mark=1):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select move/copy body {index}")
    try:
        feature = model.FeatureManager.InsertMoveCopyBody2(
            *translation, 0.0, *rotation_origin, *rotation, bool(copy), copies
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the Move/Copy Body feature")
    return feature


def planar_surface_from_sketch(model, sketch_name):
    """Create a native planar surface from one closed sketch."""
    if not _select_sketch_feature_by_name(model, str(sketch_name), mark=0):
        raise RuntimeError(f"failed to select planar-surface sketch: {sketch_name}")
    before_last = _last_model_feature(model)
    try:
        result = get_com_member(model, "InsertPlanarRefSurface")
        return _feature_after_legacy_insert(model, before_last, result, "planar surface")
    finally:
        model.ClearSelection2(True)


def thicken_surface(
    model, surface_body, thickness, *, side=0, merge=True,
    use_feature_scope=True, auto_select=True,
):
    """Create a native solid boss by thickening one selected surface body."""
    thickness = _positive_finite("thickness", thickness)
    side = int(side)
    if side not in (0, 1, 2):
        raise ValueError("side must be 0 (one), 1 (two), or 2 (both)")
    model.ClearSelection2(True)
    if not _select_com_object(surface_body, append=False, mark=1):
        raise RuntimeError("failed to select surface body for thicken")
    try:
        feature = model.FeatureManager.FeatureBossThicken(
            thickness, side, 0, False, bool(merge),
            bool(use_feature_scope), bool(auto_select),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the Thicken feature")
    return feature


def offset_surface(model, faces, distance, *, reverse=False):
    """Create a native offset-surface feature from explicit faces."""
    distance = float(distance)
    if not math.isfinite(distance) or distance < 0.0:
        raise ValueError("surface offset distance must be finite and non-negative")
    values = _as_tuple(faces)
    if not values:
        raise ValueError("at least one face is required for offset surface")
    model.ClearSelection2(True)
    for index, face in enumerate(values):
        if not _select_com_object(face, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select offset-surface face {index}")
    before_last = _last_model_feature(model)
    try:
        result = get_com_member(model, "InsertOffsetSurface", distance, bool(reverse))
        return _feature_after_legacy_insert(model, before_last, result, "offset surface")
    finally:
        model.ClearSelection2(True)


def knit_surfaces(
    model, surfaces, *, try_form_solid=False, merge_entities=True,
    use_gap_filters=False, knit_tolerance=1e-5, max_gap=1e-4,
):
    """Create a native Surface-Knit feature from adjacent surface bodies/faces."""
    values = _as_tuple(surfaces)
    if len(values) < 2:
        raise ValueError("knit requires at least two surface bodies or faces")
    knit_tolerance = _positive_finite("knit_tolerance", knit_tolerance)
    max_gap = _positive_finite("max_gap", max_gap)
    if max_gap < knit_tolerance:
        raise ValueError("max_gap cannot be smaller than knit_tolerance")
    model.ClearSelection2(True)
    for index, entity in enumerate(values):
        if not _select_com_object(entity, append=index > 0, mark=1):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select knit surface {index}")
    selected_count = _get_selection_count(model)
    selected_types = []
    for index in range(1, selected_count + 1):
        selected_types.append(int(get_com_member(
            model.SelectionManager, "GetSelectedObjectType3", index, -1
        )))
    before_last = _last_model_feature(model)
    try:
        feature = model.FeatureManager.InsertSewRefSurface(
            bool(use_gap_filters), bool(try_form_solid), bool(merge_entities),
            knit_tolerance, max_gap,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError(
            "SolidWorks did not create the Surface-Knit feature "
            f"(selected_count={selected_count}, selected_types={selected_types})"
        )
    return feature


def fill_surface(
    model, boundaries, *, resolution=2, optimize=True, constraint_curves=(),
    contact_types=None, direction_faces=None,
):
    """Create a native Fill Surface from explicit closed boundary entities.

    ``contact_types`` uses ``swContactType_e`` values 0/1/2 for contact,
    tangent and curvature continuity. Tangent/curvature boundaries require
    one corresponding direction face. Optional internal constraint curves use
    mark 4 as required by ``InsertFillSurface2``.
    """
    values = _as_tuple(boundaries)
    if not values:
        raise ValueError("at least one fill-surface boundary is required")
    constraints = _as_tuple(constraint_curves)
    controls = (
        (0,) * len(values) if contact_types is None
        else tuple(int(value) for value in _as_tuple(contact_types))
    )
    if len(controls) != len(values) or any(value not in (0, 1, 2) for value in controls):
        raise ValueError("contact_types must contain one 0, 1, or 2 value per boundary")
    if direction_faces is None:
        faces = (None,) * len(values)
    else:
        faces = tuple(direction_faces) if isinstance(direction_faces, (tuple, list)) else (direction_faces,)
        if len(faces) != len(values) or any(face is None for face in faces):
            raise ValueError("direction_faces must contain one valid face per boundary")
    if any(control in (1, 2) and face is None for control, face in zip(controls, faces)):
        raise ValueError("tangent and curvature Fill Surface boundaries require direction faces")
    resolution = int(resolution)
    if resolution not in (1, 2, 3):
        raise ValueError("fill-surface resolution must be 1, 2, or 3")
    model.ClearSelection2(True)
    for index, (boundary, control, face) in enumerate(zip(values, controls, faces)):
        mark = 513 if control == 1 else (257 if control == 2 or face is not None else 1)
        if not _select_com_object(boundary, append=index > 0, mark=mark):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select fill-surface boundary {index}")
    for index, curve in enumerate(constraints):
        if not _select_com_object(curve, append=True, mark=4):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select fill-surface constraint curve {index}")
    # InsertFillSurface2 documents all four geometry/control inputs as arrays.
    # Keep the one-boundary case as explicit SAFEARRAYs too: SW2025 accepts
    # scalar 0/1 values, but silently downgrades scalar swCurvature (2) to
    # swContact while still returning a feature with error code 0.
    patch_boundaries = _dispatch_array(values)
    contact_argument = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, controls)
    null_object = VARIANT(pythoncom.VT_DISPATCH, None)
    face_argument = (
        null_object if all(face is None for face in faces) else _dispatch_array(faces)
    )
    constraint_argument = (
        null_object if not constraints else _dispatch_array(constraints)
    )
    before_last = _last_model_feature(model)
    manager = _typed_sldworks_feature_manager(model.FeatureManager)
    try:
        feature = manager.InsertFillSurface2(
            resolution, 1 if optimize else 0,
            patch_boundaries, contact_argument, face_argument, constraint_argument,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(manager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Fill Surface feature")
    return feature


def ruled_surface_from_edges(
    model, edges, length, *, surface_type=1, alternate_face=False,
    flip_pull_direction=False, flip_direction=False, trim_and_sew=False,
    angle_rad=0.0, direction_vector=None, direction_references=(),
    connect_surface=False,
):
    """Create a native ruled surface from explicit boundary edges.

    ``surface_type`` uses the zero-based creation-method values documented by
    ``InsertRuledSurfaceFromEdge2``: 0 tangent, 1 normal, 2 tapered to vector,
    3 perpendicular to vector, and 4 sweep. Modes 2-3 require one or two
    explicit ``direction_references`` and are finalized through strong-typed
    ``IRuledSurfaceFeatureData``. Sweep mode 4 requires a non-zero XYZ
    ``direction_vector``. FeatureData reports the corresponding one-based
    ``swRuledSurfaceType_e`` value. Mark 4 chooses the default adjacent face
    and mark 6 chooses the alternate face.
    """
    values = _as_tuple(edges)
    if not values:
        raise ValueError("at least one edge is required for ruled surface")
    length = _positive_finite("length", length)
    surface_type = int(surface_type)
    if surface_type not in range(5):
        raise ValueError("surface_type must be between 0 and 4")
    angle_rad = float(angle_rad)
    if not math.isfinite(angle_rad):
        raise ValueError("angle_rad must be finite")
    if direction_vector is None:
        vector = None
    else:
        vector = tuple(float(value) for value in direction_vector)
        if len(vector) != 3 or not all(math.isfinite(value) for value in vector):
            raise ValueError("direction_vector must contain three finite values")
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude <= 1e-12:
            raise ValueError("direction_vector must be non-zero")
        vector = tuple(value / magnitude for value in vector)
    references = _as_tuple(direction_references)
    if surface_type in (2, 3):
        if len(references) not in (1, 2) or any(item is None for item in references):
            raise ValueError(
                "tapered/perpendicular ruled surfaces require one or two direction_references"
            )
        if vector is not None:
            raise ValueError(
                "tapered/perpendicular ruled surfaces use direction_references, not direction_vector"
            )
    elif references:
        raise ValueError(
            "direction_references are only valid for ruled-surface types 2 and 3"
        )
    if surface_type == 4 and vector is None:
        raise ValueError("sweep ruled surfaces require direction_vector")
    if surface_type in (0, 1) and vector is not None:
        raise ValueError("tangent and normal ruled-surface modes do not use direction_vector")
    x, y, z = vector or (0.0, 0.0, 0.0)
    mark = 6 if alternate_face else 4
    model.ClearSelection2(True)
    for index, edge in enumerate(values):
        if not _select_com_object(edge, append=index > 0, mark=mark):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select ruled-surface edge {index}")
    before_last = _last_model_feature(model)
    try:
        # InsertRuledSurfaceFromEdge2 accepts numeric XYZ only for Sweep.
        # Tapered/perpendicular modes are seeded as a valid normal feature and
        # then finalized through IRuledSurfaceFeatureData direction references.
        creation_type = 1 if surface_type in (2, 3) else surface_type
        feature = model.FeatureManager.InsertRuledSurfaceFromEdge2(
            creation_type, length, bool(flip_pull_direction),
            bool(flip_direction), bool(trim_and_sew), angle_rad,
            vector is not None, x, y, z, bool(connect_surface),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Ruled Surface feature")
    if surface_type in (2, 3):
        data = get_com_member(feature, "GetDefinition")
        if data is None:
            raise RuntimeError("Ruled Surface feature did not return IRuledSurfaceFeatureData")
        data = _typed_sldworks_interface(data, "IRuledSurfaceFeatureData")
        try:
            accessed = bool(data.AccessSelections(model, None))
        except Exception:
            accessed = bool(data.AccessSelections(model, _empty_callout()))
        if not accessed:
            raise RuntimeError("Ruled Surface FeatureData selections could not be accessed")
        modified = False
        try:
            data.UseVector = False
            data.SetDirectionReference(
                references[0], references[1] if len(references) == 2 else None,
            )
            data.Type = surface_type + 1
            data.Distance = length
            data.Angle = angle_rad
            data.TrimAndKnit = bool(trim_and_sew)
            data.Connect = bool(connect_surface)
            try:
                modified = bool(feature.ModifyDefinition(data, model, None))
            except Exception:
                modified = bool(feature.ModifyDefinition(data, model, _empty_callout()))
        finally:
            try:
                data.ReleaseSelectionAccess()
            except Exception:
                pass
        if not modified:
            raise RuntimeError(
                "SolidWorks did not apply the vector-mode Ruled Surface definition"
            )
    return feature


def ruled_surface_evidence(feature, model=None):
    """Read stable native IRuledSurfaceFeatureData parameters."""
    if feature is None:
        raise ValueError("feature is required")
    data = get_com_member(feature, "GetDefinition")
    if data is None:
        raise RuntimeError("Ruled Surface feature did not return IRuledSurfaceFeatureData")
    data = _typed_sldworks_interface(data, "IRuledSurfaceFeatureData")
    accessed = False
    if model is not None:
        try:
            accessed = bool(data.AccessSelections(model, None))
        except Exception:
            accessed = bool(data.AccessSelections(model, _empty_callout()))
        if not accessed:
            raise RuntimeError("Ruled Surface FeatureData selections could not be accessed")
    try:
        reference_count = 0
        if int(get_com_member(data, "Type")) in (3, 4, 5):
            try:
                result = data.GetDirectionReference()
                reference_count = int(result[0] if isinstance(result, tuple) else result)
            except Exception:
                reference_count = 0
        return {
            "feature": str(get_com_member(feature, "Name") or ""),
            "type": int(get_com_member(data, "Type")),
            "distance": float(get_com_member(data, "Distance")),
            "angle": float(get_com_member(data, "Angle")),
            "use_vector": bool(get_com_member(data, "UseVector")),
            "direction_reference_count": reference_count,
            "trim_and_knit": bool(get_com_member(data, "TrimAndKnit")),
            "connect": bool(get_com_member(data, "Connect")),
            "error_code": int(get_com_member(feature, "GetErrorCode") or 0),
        }
    finally:
        if accessed:
            data.ReleaseSelectionAccess()


def delete_faces(model, faces, *, heal=False, mode=None):
    """Create a native Delete Face feature from explicit faces.

    ``heal`` remains a compatibility alias for ``mode='patch'``. Explicit
    modes are ``delete``, ``patch``, ``fill``, and ``fill_tangent``.
    """
    modes = {"delete": 0, "patch": 1, "fill": 2, "fill_tangent": 3}
    if mode is not None and mode not in modes:
        raise ValueError(f"unsupported Delete Face mode: {mode}")
    if heal and mode not in (None, "patch"):
        raise ValueError("heal=True cannot be combined with a non-patch mode")
    option = modes[mode] if mode is not None else (1 if heal else None)
    values = _as_tuple(faces)
    if not values:
        raise ValueError("at least one face is required for Delete Face")
    model.ClearSelection2(True)
    for index, face in enumerate(values):
        if not _select_com_object(face, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select delete-face entity {index}")
    before_last = _last_model_feature(model)
    try:
        extension = _safe_com_member(model, "Extension")
        modern = getattr(extension, "InsertDeleteFace", None) if extension is not None else None
        if option is not None and modern is not None:
            result = modern(option)
        elif option in (2, 3):
            raise RuntimeError("Delete Face fill modes require IModelDocExtension.InsertDeleteFace")
        else:
            result = get_com_member(model, "InsertDeleteFace2", bool(heal or option == 1))
        return _feature_after_legacy_insert(model, before_last, result, "Delete Face feature")
    finally:
        model.ClearSelection2(True)


def replace_faces(model, target_faces, replacement_surface_body):
    """Create a native Replace Face feature using selection marks 1 and 2."""
    targets = _as_tuple(target_faces)
    if not targets or replacement_surface_body is None:
        raise ValueError("Replace Face requires target faces and one replacement surface body")
    model.ClearSelection2(True)
    for index, face in enumerate(targets):
        if not _select_com_object(face, append=index > 0, mark=1):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select Replace Face target {index}")
    if not _select_com_object(replacement_surface_body, append=True, mark=2):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select Replace Face replacement surface")
    before_last = _last_model_feature(model)
    try:
        result = get_com_member(model, "InsertFeatureReplaceFace")
        return _feature_after_legacy_insert(model, before_last, result, "Replace Face feature")
    finally:
        model.ClearSelection2(True)


def trim_surface_standard(
    model, trim_tools, keep_points, *, split_system=True,
    extend_linearly=False, sew=False, target_surfaces=None, mutual_trim=False,
    remove_picked=False, mutual_surface_points=None, solid_for_trim=False,
):
    """Create a standard or mutual native Surface Trim.

    ``mutual_trim=True`` uses all selected intersecting surfaces as trim tools;
    otherwise the selected surface, plane, or sketch is the standard trim tool.
    Each model-space point selects one temporary ``SURFACEBODY`` piece to keep
    before ``PostTrimSurface`` finalizes the feature.
    """
    tools = _as_tuple(trim_tools)
    points = tuple(tuple(float(value) for value in point) for point in _as_tuple(keep_points))
    if not tools:
        raise ValueError("at least one surface trim tool is required")
    if mutual_trim and len(tools) < 2:
        raise ValueError("mutual Surface Trim requires at least two intersecting surfaces")
    if not points:
        raise ValueError("at least one surface trim keep point is required")
    if any(len(point) != 3 or not all(math.isfinite(value) for value in point) for point in points):
        raise ValueError("each keep point must contain three finite coordinates")
    mutual_points = (
        tuple(tuple(float(value) for value in point) for point in mutual_surface_points)
        if mutual_surface_points is not None else ()
    )
    if mutual_points and (
        not mutual_trim
        or len(mutual_points) != len(tools)
        or any(len(point) != 3 or not all(math.isfinite(value) for value in point)
               for point in mutual_points)
    ):
        raise ValueError(
            "mutual_surface_points requires one finite XYZ point per mutual trim surface"
        )
    model.ClearSelection2(True)
    tool_boxes = []
    for tool in tools:
        try:
            tool_boxes.append(tuple(float(value) for value in _as_tuple(
                _safe_com_member(tool, "GetBodyBox")
            )))
        except Exception:
            tool_boxes.append(())
    if mutual_points:
        for index, point in enumerate(mutual_points):
            selected = model.Extension.SelectByID2(
                "", "SURFACEBODY", point[0], point[1], point[2],
                True, 0, _empty_callout(), 0,
            )
            if not bool(selected):
                model.ClearSelection2(True)
                raise RuntimeError(f"failed to select mutual trim surface at {point}")
    else:
        for index, tool in enumerate(tools):
            if not _select_com_object(tool, append=index > 0, mark=0):
                model.ClearSelection2(True)
                raise RuntimeError(f"failed to select surface trim tool {index}")
    selection_manager = _safe_com_member(model, "SelectionManager")
    selected_before_pre = int(_safe_com_member(
        selection_manager, "GetSelectedObjectCount2", -1, default=0,
    )) if selection_manager is not None else 0
    before_last = _last_model_feature(model)
    selected_before_post = 0
    selected_types_before_post = ()
    try:
        prepared = model.FeatureManager.PreTrimSurface(
            bool(mutual_trim), bool(split_system), bool(extend_linearly),
            bool(remove_picked),
        )
        if not bool(prepared):
            raise RuntimeError("SolidWorks could not prepare the Surface Trim feature")
        model.FeatureManager.SolidForTrim = bool(solid_for_trim)
        # The selected tools are consumed by PreTrimSurface. Subsequent
        # SURFACEBODY selections identify pieces to keep/remove.
        targets = _as_tuple(target_surfaces) if target_surfaces is not None else ()
        temporary_bodies = []
        for target in targets:
            temporary_bodies.extend(_as_tuple(
                _safe_com_member(model.FeatureManager, "GetPreTrimmedBodies", target)
            ))
        selected_temporary = set()
        for point in points:
            selected = model.Extension.SelectByID2(
                "", "SURFACEBODY", point[0], point[1], point[2],
                True, 0, _empty_callout(), 0,
            )
            if not bool(selected) and temporary_bodies:
                candidates = []
                for index, body in enumerate(temporary_bodies):
                    if index in selected_temporary:
                        continue
                    box = _as_tuple(_safe_com_member(body, "GetBodyBox"))
                    if len(box) >= 6 and all(
                        box[axis] - 1e-9 <= point[axis] <= box[axis + 3] + 1e-9
                        for axis in range(3)
                    ):
                        candidates.append((index, body))
                if len(candidates) == 1:
                    index, body = candidates[0]
                    selected = _select_com_object(body, append=True, mark=0)
                    if selected:
                        selected_temporary.add(index)
            if not bool(selected):
                body_boxes = []
                for body in temporary_bodies:
                    try:
                        body_boxes.append(tuple(float(value) for value in _as_tuple(
                            _safe_com_member(body, "GetBodyBox")
                        )))
                    except Exception:
                        body_boxes.append(())
                raise RuntimeError(
                    f"failed to select trimmed surface piece at {point}; "
                    f"temporary_body_count={len(temporary_bodies)}, boxes={body_boxes}"
                )
        if selection_manager is not None:
            selected_before_post = int(_safe_com_member(
                selection_manager, "GetSelectedObjectCount2", -1, default=0,
            ))
            selected_types_before_post = tuple(
                int(_safe_com_member(
                    selection_manager, "GetSelectedObjectType3", index, -1,
                    default=-1,
                ))
                for index in range(1, selected_before_post + 1)
            )
        feature = model.FeatureManager.PostTrimSurface(bool(sew))
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError(
            "SolidWorks did not create the Surface Trim feature "
            f"(selected_before_pre={selected_before_pre}, "
            f"selected_before_post={selected_before_post}, "
            f"selected_types_before_post={selected_types_before_post}, "
            f"tool_boxes={tool_boxes})"
        )
    return feature


def untrim_surface(
    model, face_or_edges, *, face_untrim_type=0, edge_untrim_type=2,
    distance=0.0, merge=False, trim_opposite_side=False,
):
    """Create a native Untrim Surface feature from selected face or edges."""
    values = _as_tuple(face_or_edges)
    if not values:
        raise ValueError("at least one face or edge is required for Untrim Surface")
    face_untrim_type = int(face_untrim_type)
    edge_untrim_type = int(edge_untrim_type)
    if face_untrim_type not in (0, 1, 2):
        raise ValueError("face_untrim_type must be 0, 1, or 2")
    distance = float(distance)
    if not math.isfinite(distance) or distance < 0.0:
        raise ValueError("untrim distance must be finite and non-negative")
    model.ClearSelection2(True)
    for index, entity in enumerate(values):
        if not _select_com_object(entity, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select untrim entity {index}")
    before_last = _last_model_feature(model)
    try:
        feature = model.FeatureManager.InsertUntrimSurface2(
            face_untrim_type, edge_untrim_type, distance,
            bool(merge), bool(trim_opposite_side),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Untrim Surface feature")
    return feature


def extend_surface(
    model, items, *, linear=False, end_condition=0,
    distance=None, terminal_reference=None,
):
    """Extend surface edges/faces by distance, to point, or to solid face."""
    selections = tuple(_as_tuple(items))
    if not selections:
        raise ValueError("at least one surface edge or face is required")
    condition = int(end_condition)
    if condition not in (0, 1, 2):
        raise ValueError("surface-extend end condition must be 0, 1, or 2")
    if condition == 0:
        if terminal_reference is not None:
            raise ValueError("distance extension does not accept a terminal reference")
        extension_distance = _positive_finite("distance", distance)
    else:
        if terminal_reference is None:
            raise ValueError("to-point/to-surface extension requires a terminal reference")
        if distance not in (None, 0, 0.0):
            raise ValueError("distance is not used by to-point/to-surface extension")
        extension_distance = 0.0
    model.ClearSelection2(True)
    before_last = _last_model_feature(model)
    try:
        for index, item in enumerate(selections):
            if not _select_com_object(item, append=index > 0, mark=0):
                raise RuntimeError(f"failed to select surface-extend item {index}")
        if terminal_reference is not None and not _select_com_object(
            terminal_reference, append=True, mark=0,
        ):
            raise RuntimeError("failed to select surface-extend terminal reference")
        get_com_member(
            model, "InsertExtendSurface", bool(linear), condition, extension_distance,
        )
        feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Surface Extend feature")
    return feature


def extend_surface_distance(model, items, distance, *, linear=False):
    """Extend selected surface edges/faces by a native distance condition."""
    return extend_surface(
        model, items, linear=linear, end_condition=0, distance=distance,
    )


def extend_surface_evidence(feature, model=None):
    """Read native ``ISurfaceExtendFeatureData`` parameters."""
    if feature is None:
        raise ValueError("feature is required")
    definition = _safe_com_member(feature, "GetDefinition")
    if definition is None:
        raise RuntimeError("SolidWorks did not expose Surface Extend FeatureData")
    accessed = False
    if model is not None:
        accessed = bool(_safe_com_member(
            definition, "AccessSelections", model, _empty_callout(), default=False,
        ))
        if not accessed:
            raise RuntimeError("could not access Surface Extend selections")
    try:
        return {
            "feature_name": str(_safe_com_member(feature, "Name", default="")),
            "feature_type": str(_safe_com_member(
                feature, "GetTypeName2", default="",
            )),
            "type": int(_safe_com_member(definition, "Type", default=-1)),
            "end_condition": int(_safe_com_member(
                definition, "EndCondition", default=-1,
            )),
            "distance": float(_safe_com_member(
                definition, "Distance", default=0.0,
            )),
            "item_count": int(_safe_com_member(
                definition, "GetItemsCount", default=0,
            )),
            "propagating_edge_count": int(_safe_com_member(
                definition, "GetPropagatingEdgesCount", default=0,
            )),
            "selection_accessed": accessed,
            "feature_error_code": int(_safe_com_member(
                feature, "GetErrorCode", default=0,
            )),
        }
    finally:
        if accessed:
            _safe_com_member(definition, "ReleaseSelectionAccess")


def radiate_surface(
    model, edges, direction_reference, distance, *, flip=False,
    propagate_tangent=False,
):
    """Create a native Radiate Surface from edges and a direction reference.

    SOLIDWORKS assigns selection mark 2 to the radiated edges and mark 1 to
    the face, reference plane, or reference surface that supplies direction.
    """
    selected_edges = tuple(_as_tuple(edges))
    if not selected_edges:
        raise ValueError("at least one edge is required for Radiate Surface")
    if direction_reference is None:
        raise ValueError("a direction reference is required for Radiate Surface")
    distance = _positive_finite("distance", distance)
    model.ClearSelection2(True)
    before_last = _last_model_feature(model)
    try:
        for index, edge in enumerate(selected_edges):
            if not _select_com_object_with_data(
                model, edge, append=index > 0, mark=2,
            ):
                raise RuntimeError(f"failed to select radiate-surface edge {index}")
        if not _select_com_object_with_data(
            model, direction_reference, append=True, mark=1,
        ):
            raise RuntimeError("failed to select radiate-surface direction reference")
        get_com_member(
            model, "InsertRadiateSurface", distance, bool(flip),
            bool(propagate_tangent),
        )
        feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Radiate Surface feature")
    return feature


def radiate_surface_evidence(feature, model=None):
    """Read native ``ISurfaceRadiateFeatureData`` semantics."""
    if feature is None:
        raise ValueError("feature is required")
    definition = _safe_com_member(feature, "GetDefinition")
    if definition is None:
        raise RuntimeError("SolidWorks did not expose Radiate Surface FeatureData")
    accessed = False
    if model is not None:
        accessed = bool(_safe_com_member(
            definition, "AccessSelections", model, _empty_callout(), default=False,
        ))
        if not accessed:
            raise RuntimeError("could not access Radiate Surface selections")
    try:
        return {
            "feature_name": str(_safe_com_member(feature, "Name", default="")),
            "feature_type": str(_safe_com_member(
                feature, "GetTypeName2", default="",
            )),
            "distance": float(_safe_com_member(
                definition, "Distance", default=0.0,
            )),
            "flip": bool(_safe_com_member(
                definition, "Flip", default=False,
            )),
            "propagate_tangent_faces": bool(_safe_com_member(
                definition, "PropagateToTangentFaces", default=False,
            )),
            "radiated_entity_count": int(_safe_com_member(
                definition, "GetRadiatedEntitiesCount", default=0,
            )),
            "has_direction_reference": _safe_com_member(
                definition, "DirectionReference",
            ) is not None,
            "selection_accessed": accessed,
            "feature_error_code": int(_safe_com_member(
                feature, "GetErrorCode", default=0,
            )),
        }
    finally:
        if accessed:
            _safe_com_member(definition, "ReleaseSelectionAccess")


def flatten_surface(
    model, faces, anchor_vertex, *, accuracy_factor=5, use_tears=False,
):
    """Create a native Surface Flatten feature from faces and one anchor vertex."""
    selected_faces = tuple(_as_tuple(faces))
    if not selected_faces:
        raise ValueError("at least one face or surface is required to flatten")
    if anchor_vertex is None:
        raise ValueError("an anchor vertex is required to flatten a surface")
    accuracy = int(accuracy_factor)
    if accuracy not in range(1, 11):
        raise ValueError("surface-flatten accuracy_factor must be in the range 1..10")
    model.ClearSelection2(True)
    before_last = _last_model_feature(model)
    try:
        for index, face in enumerate(selected_faces):
            if not _select_com_object_with_data(
                model, face, append=index > 0, mark=1,
            ):
                raise RuntimeError(f"failed to select flatten-surface face {index}")
        if not _select_com_object_with_data(
            model, anchor_vertex, append=True, mark=16,
        ):
            raise RuntimeError("failed to select flatten-surface anchor vertex")
        feature = get_com_member(
            model.FeatureManager, "InsertFlattenSurface2",
            accuracy, bool(use_tears),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Surface Flatten feature")
    return feature


def flatten_surface_evidence(feature, model=None):
    """Read native ``ISurfaceFlattenFeatureData`` semantics."""
    if feature is None:
        raise ValueError("feature is required")
    definition = _safe_com_member(feature, "GetDefinition")
    if definition is None:
        raise RuntimeError("SolidWorks did not expose Surface Flatten FeatureData")
    accessed = False
    if model is not None:
        accessed = bool(_safe_com_member(
            definition, "AccessSelections", model, _empty_callout(), default=False,
        ))
        if not accessed:
            raise RuntimeError("could not access Surface Flatten selections")
    try:
        return {
            "feature_name": str(_safe_com_member(feature, "Name", default="")),
            "feature_type": str(_safe_com_member(
                feature, "GetTypeName2", default="",
            )),
            "accuracy_factor": int(_safe_com_member(
                definition, "AccuracyFactor", default=-1,
            )),
            "face_count": len(_as_tuple(_safe_com_member(
                definition, "Faces", default=(),
            ))),
            "has_anchor_vertex": _safe_com_member(
                definition, "FixPointVertex",
            ) is not None,
            "keep_internal_control_curves": bool(_safe_com_member(
                definition, "KeepInternalControlCurves", default=False,
            )),
            "should_make_tears": bool(_safe_com_member(
                definition, "ShouldMakeTears", default=False,
            )),
            "guide_edge_count": len(_as_tuple(_safe_com_member(
                definition, "GuideEdges", default=(),
            ))),
            "tear_edge_count": len(_as_tuple(_safe_com_member(
                definition, "TearEdges", default=(),
            ))),
            "map_edge_count": len(_as_tuple(_safe_com_member(
                definition, "MapEdges", default=(),
            ))),
            "selection_accessed": accessed,
            "feature_error_code": int(_safe_com_member(
                feature, "GetErrorCode", default=0,
            )),
        }
    finally:
        if accessed:
            _safe_com_member(definition, "ReleaseSelectionAccess")


def extrude_surface(
    model, sketch_name, depth, *, direction=True, cap_end=False,
    knit_result=False,
):
    """Create a native blind extruded surface from a named sketch."""
    depth = _positive_finite("depth", depth)
    _ensure_sketch_selected(model, sketch_name)
    before_last = _last_model_feature(model)
    try:
        result = model.FeatureManager.FeatureExtruRefSurface3(
            True, bool(direction), 0, 0.0,
            0, 0, depth, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            bool(cap_end), False, False, bool(knit_result),
        )
        return _feature_after_legacy_insert(model, before_last, result, "Extruded Surface feature")
    finally:
        model.ClearSelection2(True)


def revolve_surface(model, sketch_name, angle_rad, *, reverse_direction=False, revolve_type=0):
    """Create a native revolved surface around a construction line in the sketch."""
    angle_rad = float(angle_rad)
    if not math.isfinite(angle_rad) or not 0.0 < angle_rad <= 2.0 * math.pi:
        raise ValueError("angle_rad must be finite and in (0, 2*pi]")
    revolve_type = int(revolve_type)
    _ensure_sketch_selected(model, sketch_name)
    before_last = _last_model_feature(model)
    try:
        feature = model.FeatureManager.InsertRevolvedRefSurface(
            angle_rad, bool(reverse_direction), 0.0, revolve_type,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Revolved Surface feature")
    return feature


def sweep_surface(
    model, profile_sketch_name, path_sketch_name, *, guide_curves=(), propagate=True,
    twist_control=0, keep_tangency=False, advanced_smoothing=False,
    start_matching_type=0, end_matching_type=0, path_align=0,
    twist_angle=0.0, merge_smooth_faces=True, direction=0,
):
    """Create a native swept surface with optional guide curves."""
    profile = _feature_object(model, profile_sketch_name)
    path = _feature_object(model, path_sketch_name)
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    if profile is None or path is None:
        raise RuntimeError("sweep surface profile or path sketch was not found")
    twist = int(twist_control)
    sweep_direction = int(direction)
    path_alignment = int(path_align)
    if twist not in (0, 1, 2, 3, 8, 9):
        raise ValueError("unsupported sweep-surface twist-control value")
    if sweep_direction not in (0, 1, 2):
        raise ValueError("sweep-surface direction must be 0, 1, or 2")
    if path_alignment not in (0, 2, 3):
        raise ValueError("sweep-surface path alignment must be 0, 2, or 3")
    if guides and sweep_direction == 1:
        raise ValueError("guide curves are not valid for a bidirectional sweep surface")
    if guides and twist in (8, 9):
        raise ValueError("guide curves are not valid with constant-twist sweep modes")
    model.ClearSelection2(True)
    if not _select_com_object(profile, append=False, mark=1):
        raise RuntimeError("failed to select sweep-surface profile with mark 1")
    for index, guide in enumerate(guides):
        if not _select_com_object(guide, append=True, mark=2):
            model.ClearSelection2(True)
            raise RuntimeError(
                f"failed to select sweep-surface guide {index} with mark 2"
            )
    if not _select_com_object(path, append=True, mark=4):
        model.ClearSelection2(True)
        raise RuntimeError("failed to select sweep-surface path with mark 4")
    before_last = _last_model_feature(model)
    try:
        feature = model.FeatureManager.InsertSweepSurface3(
            bool(propagate), twist, bool(keep_tangency),
            bool(advanced_smoothing), int(start_matching_type),
            int(end_matching_type), path_alignment, False, True,
            float(twist_angle), bool(merge_smooth_faces), False, 0.0,
            sweep_direction,
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Swept Surface feature")
    return feature


def sweep_surface_evidence(feature, model=None):
    """Read ``ISweepFeatureData`` semantics for a native swept surface."""
    if feature is None:
        raise ValueError("feature is required")
    definition = _safe_com_member(feature, "GetDefinition")
    if definition is None:
        raise RuntimeError("SolidWorks did not expose Swept Surface FeatureData")
    accessed = False
    if model is not None:
        accessed = bool(_safe_com_member(
            definition, "AccessSelections", model, _empty_callout(), default=False,
        ))
        if not accessed:
            raise RuntimeError("could not access Swept Surface selections")
    try:
        return {
            "feature_name": str(_safe_com_member(feature, "Name", default="")),
            "feature_type": str(_safe_com_member(
                feature, "GetTypeName2", default="",
            )),
            "guide_curve_count": int(_safe_com_member(
                definition, "GetGuideCurvesCount", default=0,
            )),
            "twist_control_type": int(_safe_com_member(
                definition, "TwistControlType", default=-1,
            )),
            "twist_angle": float(_safe_com_member(
                definition, "GetTwistAngle", default=0.0,
            )),
            "path_alignment_type": int(_safe_com_member(
                definition, "PathAlignmentType", default=-1,
            )),
            "direction": int(_safe_com_member(
                definition, "Direction", default=-1,
            )),
            "start_tangency_type": int(_safe_com_member(
                definition, "StartTangencyType", default=-1,
            )),
            "end_tangency_type": int(_safe_com_member(
                definition, "EndTangencyType", default=-1,
            )),
            "merge_smooth_faces": bool(_safe_com_member(
                definition, "MergeSmoothFaces", default=False,
            )),
            "is_boss": bool(_safe_com_member(
                definition, "IsBossFeature", default=False,
            )),
            "selection_accessed": accessed,
            "feature_error_code": int(_safe_com_member(
                feature, "GetErrorCode", default=0,
            )),
        }
    finally:
        if accessed:
            _safe_com_member(definition, "ReleaseSelectionAccess")


def loft_surface(
    model, section_sketch_names, *, guide_curves=(), centerline=None,
    start_tangent_reference=None, end_tangent_reference=None,
    closed=False, keep_tangency=False,
    force_non_rational=False, tess_tolerance_factor=1.0,
    start_matching_type=0, end_matching_type=0,
):
    """Create a native lofted surface with optional guides and centerline.

    Profiles, guides, centerline and start/end direction references use the
    documented selection marks 1, 2, 4, 8 and 32 respectively.
    """
    sections = tuple(
        _feature_object(model, item) for item in _as_tuple(section_sketch_names)
    )
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    if len(sections) < 2:
        raise ValueError("loft surface requires at least two section sketches")
    tolerance = _positive_finite("tess_tolerance_factor", tess_tolerance_factor)
    start_type = int(start_matching_type)
    end_type = int(end_matching_type)
    if start_type not in range(4) or end_type not in range(4):
        raise ValueError("loft-surface matching types must be values 0..3")
    if (start_type == 2) != (start_tangent_reference is not None):
        raise ValueError(
            "loft-surface start vector matching requires exactly one start reference"
        )
    if (end_type == 2) != (end_tangent_reference is not None):
        raise ValueError(
            "loft-surface end vector matching requires exactly one end reference"
        )
    center = _feature_object(model, centerline) if centerline is not None else None
    start_reference = (
        _feature_object(model, start_tangent_reference)
        if start_tangent_reference is not None else None
    )
    end_reference = (
        _feature_object(model, end_tangent_reference)
        if end_tangent_reference is not None else None
    )
    model.ClearSelection2(True)
    try:
        for index, section in enumerate(sections):
            if not _select_com_object(section, append=index > 0, mark=1):
                raise RuntimeError(f"failed to select loft-surface section {index}")
        for index, guide in enumerate(guides):
            if not _select_com_object(guide, append=True, mark=2):
                raise RuntimeError(f"failed to select loft-surface guide {index}")
        if center is not None and not _select_com_object(center, append=True, mark=4):
            raise RuntimeError("failed to select loft-surface centerline")
        if start_reference is not None and not _select_com_object(
            start_reference, append=True, mark=8,
        ):
            raise RuntimeError("failed to select loft-surface start direction reference")
        if end_reference is not None and not _select_com_object(
            end_reference, append=True, mark=32,
        ):
            raise RuntimeError("failed to select loft-surface end direction reference")
        before_last = _last_model_feature(model)
        result = get_com_member(
            model, "InsertLoftRefSurface2",
            bool(closed), bool(keep_tangency), bool(force_non_rational),
            tolerance, start_type, end_type,
        )
        # InsertLoftRefSurface2 is a void legacy API.  GetLastFeatureAdded can
        # remain stale after reference geometry, so recover the actual tree
        # tail first instead of treating that stale object as the new surface.
        feature = _last_model_feature(model)
        if (
            result is False or feature is None
            or _feature_key(feature) == _feature_key(before_last)
        ):
            raise RuntimeError("SolidWorks did not create the Lofted Surface feature")
        return feature
    finally:
        model.ClearSelection2(True)


def loft_surface_evidence(feature, model=None):
    """Read native ``ILoftFeatureData`` evidence for a lofted surface."""
    if feature is None:
        raise ValueError("feature is required")
    feature_name = str(_safe_com_member(feature, "Name", default=""))
    feature_type = str(_safe_com_member(feature, "GetTypeName2", default=""))
    parents = tuple(_as_tuple(_safe_com_member(feature, "GetParents", default=())))
    parent_evidence = tuple({
        "name": str(_safe_com_member(parent, "Name", default="")),
        "type": str(_safe_com_member(parent, "GetTypeName2", default="")),
    } for parent in parents)
    error_code = int(_safe_com_member(feature, "GetErrorCode", default=0))
    definition = get_com_member(feature, "GetDefinition")
    if definition is None:
        # SW2025 BlendRefSurface creates and rebuilds correctly but exposes no
        # ILoftFeatureData through GetDefinition.  Report that boundary instead
        # of inventing profile/guide counts from the original request.
        return {
            "feature_name": feature_name,
            "feature_type": feature_type,
            "feature_data_available": False,
            "parents": parent_evidence,
            "selection_accessed": False,
            "feature_error_code": error_code,
        }
    accessed = False
    if model is not None:
        accessed = bool(_safe_com_member(
            definition, "AccessSelections", model, _empty_callout(), default=False,
        ))
        if not accessed:
            raise RuntimeError("could not access Lofted Surface selections")
    try:
        centerline = _safe_com_member(definition, "Centerline")
        start_vector = _safe_com_member(definition, "StartDirectionVector")
        end_vector = _safe_com_member(definition, "EndDirectionVector")
        return {
            "feature_name": feature_name,
            "feature_type": feature_type,
            "feature_data_available": True,
            "parents": parent_evidence,
            "profile_count": int(_safe_com_member(
                definition, "GetProfileCount", default=0,
            )),
            "guide_curve_count": int(_safe_com_member(
                definition, "GetGuideCurvesCount", default=0,
            )),
            "has_centerline": centerline is not None,
            "start_tangency_type": int(_safe_com_member(
                definition, "StartTangencyType", default=-1,
            )),
            "end_tangency_type": int(_safe_com_member(
                definition, "EndTangencyType", default=-1,
            )),
            "has_start_direction_reference": start_vector is not None,
            "has_end_direction_reference": end_vector is not None,
            "closed": bool(_safe_com_member(definition, "Close", default=False)),
            "is_boss": bool(_safe_com_member(
                definition, "IsBossFeature", default=False,
            )),
            "is_thin": bool(_safe_com_member(
                definition, "IsThinFeature", default=False,
            )),
            "selection_accessed": accessed,
            "feature_error_code": error_code,
        }
    finally:
        if accessed:
            _safe_com_member(definition, "ReleaseSelectionAccess")


def feature_dependency_graph(model, root_feature, *, recursive=True):
    """Return a stable name/type graph from native Feature parents and children.

    COM proxy identity is intentionally ignored; nodes are keyed by the
    FeatureManager name and ``GetTypeName2`` pair so repeated wrappers for the
    same native feature do not create duplicate graph nodes.
    """
    root = _feature_object(model, root_feature)
    root_key = _feature_key(root)
    if root_key is None or not root_key[0]:
        raise ValueError("root feature must have a stable FeatureManager name")
    pending = [root]
    nodes = {}
    edges = set()
    while pending:
        feature = pending.pop(0)
        key = _feature_key(feature)
        if key is None or not key[0] or key in nodes:
            continue
        nodes[key] = feature
        parents = tuple(
            item for item in _as_tuple(_safe_com_member(feature, "GetParents"))
            if item is not None
        )
        children = tuple(
            item for item in _as_tuple(_safe_com_member(feature, "GetChildren"))
            if item is not None
        )
        for parent in parents:
            parent_key = _feature_key(parent)
            if parent_key is None or not parent_key[0]:
                continue
            edges.add((parent_key, key))
            if recursive and parent_key not in nodes:
                pending.append(parent)
        for child in children:
            child_key = _feature_key(child)
            if child_key is None or not child_key[0]:
                continue
            edges.add((key, child_key))
            if recursive and child_key not in nodes:
                pending.append(child)
        if not recursive:
            for related in (*parents, *children):
                related_key = _feature_key(related)
                if related_key is not None and related_key[0] and related_key not in nodes:
                    nodes[related_key] = related

    ordered_keys = sorted(nodes)
    ordered_edges = sorted(edges)
    return {
        "root": {"name": root_key[0], "type": root_key[1]},
        "recursive": bool(recursive),
        "nodes": [
            {
                "name": key[0],
                "type": key[1],
                "parent_count": sum(1 for _parent, child in ordered_edges if child == key),
                "child_count": sum(1 for parent, _child in ordered_edges if parent == key),
            }
            for key in ordered_keys
        ],
        "edges": [
            {
                "parent": {"name": parent[0], "type": parent[1]},
                "child": {"name": child[0], "type": child[1]},
            }
            for parent, child in ordered_edges
        ],
    }


def reorder_feature_after(model, feature_to_move, target_feature):
    """Move one independent feature after another in FeatureManager order."""
    move_name = str(_safe_com_member(feature_to_move, "Name", default=feature_to_move))
    target_name = str(_safe_com_member(target_feature, "Name", default=target_feature))
    if not move_name or not target_name or move_name == target_name:
        raise ValueError("feature names must be non-empty and distinct")
    if _safe_com_member(model, "FeatureByName", move_name) is None:
        raise ValueError(f"feature to move was not found: {move_name}")
    if _safe_com_member(model, "FeatureByName", target_name) is None:
        raise ValueError(f"target feature was not found: {target_name}")
    result = get_com_member(model.Extension, "ReorderFeature", move_name, target_name, 3)
    if not bool(result):
        raise RuntimeError(f"SolidWorks could not move {move_name} after {target_name}")
    ordered = []
    feature = _safe_com_member(model, "FirstFeature")
    while feature is not None:
        ordered.append(str(_safe_com_member(feature, "Name", default="")))
        feature = _safe_com_member(feature, "GetNextFeature")
    if move_name not in ordered or target_name not in ordered:
        raise RuntimeError("reordered features are missing from the FeatureManager tree")
    if ordered.index(move_name) <= ordered.index(target_name):
        raise RuntimeError(
            f"feature order did not change as requested: {move_name}, {target_name}, {ordered}"
        )
    return tuple(ordered)


def feature_dependency_path(model, start_feature, end_feature):
    """Return one native parent-to-child dependency path, or an empty tuple."""
    start = _feature_object(model, start_feature)
    end = _feature_object(model, end_feature)
    start_key, end_key = _feature_key(start), _feature_key(end)
    if start_key == end_key:
        return (start_key,)
    graph = feature_dependency_graph(model, start, recursive=True)
    adjacency = {}
    for edge in graph["edges"]:
        parent = (edge["parent"]["name"], edge["parent"]["type"])
        child = (edge["child"]["name"], edge["child"]["type"])
        adjacency.setdefault(parent, []).append(child)
    pending = [(start_key, (start_key,))]
    visited = set()
    while pending:
        node, path = pending.pop(0)
        if node in visited:
            continue
        visited.add(node)
        for child in adjacency.get(node, ()):
            next_path = path + (child,)
            if child == end_key:
                return next_path
            pending.append((child, next_path))
    return ()


def reorder_feature_after_safe(model, feature_to_move, target_feature):
    """Reorder independent/dependent features without breaking ancestry.

    A feature cannot be moved after any of its native descendants.  That case
    is rejected before ``IModelDocExtension.ReorderFeature`` is called.
    """
    move = _feature_object(model, feature_to_move)
    target = _feature_object(model, target_feature)
    path = feature_dependency_path(model, move, target)
    if len(path) > 1:
        names = " -> ".join(item[0] for item in path)
        raise ValueError(
            f"cannot move a parent feature after its descendant: {names}"
        )
    return reorder_feature_after(model, move, target)


def intersect_bodies(
    model, bodies, *, include_region_indices=None, target_volume=None,
    volume_tolerance=1e-9, merge=True, consume=True, cap_planar=False,
    region_type=0,
):
    """Create a native Intersect feature from explicit solid/surface bodies.

    Regions can be included by explicit preview index or by one unique preview
    volume. All remaining regions are passed to ``PostIntersect`` as excluded.
    """
    values = _as_tuple(bodies)
    if len(values) < 2:
        raise ValueError("Intersect requires at least two bodies")
    region_type = int(region_type)
    if region_type not in (0, 1, 2):
        raise ValueError("region_type must be 0 (intersecting), 1 (internal), or 2 (both)")
    model.ClearSelection2(True)
    for index, body in enumerate(values):
        if not _select_com_object(body, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select Intersect body {index}")
    before_last = _last_model_feature(model)
    manager = _typed_sldworks_feature_manager(model.FeatureManager)
    try:
        # PreIntersect is obsolete.  SW2025 can still return preview bodies
        # from it, but PostIntersect does not reliably commit that preview.
        regions = _as_tuple(
            manager.PreIntersect2(bool(cap_planar), region_type)
        )
        if not regions:
            raise RuntimeError("SolidWorks returned no preview regions for Intersect")
        # The official create example clears the input-tool selection between
        # PreIntersect and PostIntersect.  Keeping it selected lets SW2025
        # preview regions but prevents the feature from being committed.
        model.ClearSelection2(True)
        if include_region_indices is not None:
            included = {int(index) for index in _as_tuple(include_region_indices)}
        elif target_volume is not None:
            target_volume = _positive_finite("target_volume", target_volume)
            matches = []
            for index, region in enumerate(regions):
                properties = _as_tuple(_safe_com_member(region, "GetMassProperties", 1.0))
                if len(properties) > 3 and abs(float(properties[3]) - target_volume) <= float(volume_tolerance):
                    matches.append(index)
            if len(matches) != 1:
                raise RuntimeError(f"target Intersect volume matched {len(matches)} preview regions")
            included = set(matches)
        else:
            included = set(range(len(regions)))
        if not included or min(included) < 0 or max(included) >= len(regions):
            raise ValueError("included Intersect region indices are out of range")
        excluded = tuple(index not in included for index in range(len(regions)))
        excluded_variant = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_BOOL,
            excluded,
        )
        feature = manager.PostIntersect(
            excluded_variant, bool(merge), bool(consume),
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        feature = _safe_com_member(manager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        preview_volumes = []
        for region in regions:
            properties = _as_tuple(_safe_com_member(region, "GetMassProperties", 1.0))
            preview_volumes.append(float(properties[3]) if len(properties) > 3 else None)
        raise RuntimeError(
            "SolidWorks did not create the Intersect feature "
            f"(regions={len(regions)}, preview_volumes={preview_volumes}, "
            f"included={tuple(sorted(included))}, excluded={excluded}, "
            f"last={_feature_key(feature)}, before={_feature_key(before_last)})"
        )
    return {"feature": feature, "preview_regions": regions, "included_indices": tuple(sorted(included))}


def split_bodies(
    model, cutting_tools, *, save_paths, override_template_name="",
):
    """Blocked public Split entry: SW2025 still opens an interactive Save As dialog."""
    raise RuntimeError(
        "split_bodies is blocked for unattended use: SW2025 PostSplitBody2 "
        "opens an interactive Save As dialog even when all save paths are supplied"
    )


def _split_bodies_experimental(
    model, cutting_tools, *, consume_cut=True, save_paths=None,
    override_template_name="", allow_modal=False,
):
    """Supervised-only Split candidate that may open SolidWorks Save As dialogs."""
    if allow_modal is not True:
        raise RuntimeError(
            "experimental Split is modal and disabled; pass allow_modal=True only "
            "during an attended diagnostic run"
        )
    if os.environ.get("SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC") != "1":
        raise RuntimeError(
            "experimental Split is modal and disabled; set "
            "SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC=1 only during an attended "
            "diagnostic run"
        )
    tools = _as_tuple(cutting_tools)
    if not tools:
        raise ValueError("at least one cutting tool is required for Split")
    model.ClearSelection2(True)
    for index, tool in enumerate(tools):
        if not _select_com_object(tool, append=index > 0, mark=0):
            model.ClearSelection2(True)
            raise RuntimeError(f"failed to select Split cutting tool {index}")
    before_last = _last_model_feature(model)
    try:
        preview_bodies = _as_tuple(get_com_member(model.FeatureManager, "PreSplitBody2"))
        if len(preview_bodies) < 2:
            raise RuntimeError(f"Split preview returned {len(preview_bodies)} bodies")
        model.ClearSelection2(True)
        paths = tuple(str(path) for path in _as_tuple(save_paths)) if save_paths is not None else tuple(
            "" for _ in preview_bodies
        )
        if len(paths) != len(preview_bodies):
            raise ValueError("save_paths must match the Split preview body count")
        body_array = _dispatch_array(preview_bodies)
        origins = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            tuple(None for _ in preview_bodies),
        )
        save_paths = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_BSTR,
            paths,
        )
        result = model.FeatureManager.PostSplitBody2(
            body_array, bool(consume_cut), origins, save_paths,
            str(override_template_name),
        )
    finally:
        model.ClearSelection2(True)
    feature = result if result is not None and not isinstance(result, (tuple, list, bool)) else None
    if feature is None:
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
    if feature is None:
        feature = _last_model_feature(model)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Split feature")
    return {"feature": feature, "preview_bodies": preview_bodies}


def loft_feature(model, section_sketch_names, cut=False, merge=True):
    """Create a native loft from ordered sketch sections selected with mark 1."""
    model.ClearSelection2(True)
    for index, name in enumerate(section_sketch_names):
        feature = _safe_com_member(model, "FeatureByName", name)
        if feature is None:
            raise RuntimeError(f"Loft section sketch was not found: {name}")
        if not _select_com_object(feature, append=index > 0, mark=1):
            raise RuntimeError(f"Could not select loft section with mark 1: {name}")
    manager = model.FeatureManager
    if cut:
        return manager.InsertCutBlend(
            False, False, False, 1.0, 0, 0,
            False, 0.0, 0.0, 0, True, True,
        )
    return manager.InsertProtrusionBlend(
        False, False, False, 1.0, 0, 0,
        0.0, 0.0, False, False,
        False, 0.0, 0.0, 0,
        bool(merge), True, True,
    )


def loft_boss_with_guides(
    model, section_sketches, guide_curves, *, centerline=None,
    merge=True, closed=False, keep_tangency=True,
    guide_curve_influence=0,
):
    """Create a native boss loft with ordered profiles and guide curves.

    Profile sketches use selection mark 1. Each independent guide group uses
    ``4096 * group + 2`` as documented by the SW2025 loft examples; an optional
    centerline uses mark 4.
    """
    if len(_as_tuple(section_sketches)) < 2:
        raise ValueError("guide-curve loft requires at least two section sketches")
    if not _as_tuple(guide_curves):
        raise ValueError("guide-curve loft requires at least one guide curve")
    return loft_feature_advanced(
        model, section_sketches, guide_curves=guide_curves,
        centerline=centerline, merge=merge, closed=closed,
        keep_tangency=keep_tangency,
        guide_curve_influence=guide_curve_influence,
    )


def loft_cut_with_guides(
    model, section_sketches, guide_curves, *, centerline=None,
    closed=False, keep_tangency=True,
):
    """Create a native lofted cut with ordered profiles and guide curves.

    SW2025 ``InsertCutBlend`` uses mark 1 for profiles, mark 2 for every
    guide curve, and mark 4 for an optional centerline. Unlike
    ``InsertProtrusionBlend2``, this API has no guide-influence argument.
    """
    if len(_as_tuple(section_sketches)) < 2:
        raise ValueError("guide-curve loft cut requires at least two section sketches")
    if not _as_tuple(guide_curves):
        raise ValueError("guide-curve loft cut requires at least one guide curve")
    return loft_feature_advanced(
        model, section_sketches, guide_curves=guide_curves,
        centerline=centerline, cut=True, closed=closed,
        keep_tangency=keep_tangency,
    )


def loft_feature_advanced(
    model, section_sketches, *, guide_curves=(), centerline=None,
    section_pick_points=None,
    cut=False, merge=True, closed=False, keep_tangency=True,
    guide_curve_influence=0,
    start_matching_type=0, end_matching_type=0,
    start_tangent_length=1.0, end_tangent_length=1.0,
    reverse_start_tangent=False, reverse_end_tangent=False,
    start_tangent_reference=None, end_tangent_reference=None,
    thin_type=None, thickness1=0.0, thickness2=0.0,
):
    """Create an advanced native boss or cut loft.

    Profiles use mark 1, optional centerline mark 4, start/end direction
    references marks 8/32. Boss guide groups use ``4096*n+2``; the older
    SW2025 cut API requires every guide selection at mark 2.
    """
    sections = tuple(_feature_object(model, item) for item in _as_tuple(section_sketches))
    guides = tuple(_feature_object(model, item) for item in _as_tuple(guide_curves))
    if len(sections) < 2:
        raise ValueError("advanced loft requires at least two section sketches")
    pick_points = None
    if section_pick_points is not None:
        pick_points = tuple(tuple(float(value) for value in point)
                            for point in section_pick_points)
        if len(pick_points) != len(sections) or any(len(point) != 3 for point in pick_points):
            raise ValueError("section_pick_points must contain one model-space XYZ point per section")
        if any(not all(math.isfinite(value) for value in point) for point in pick_points):
            raise ValueError("section pick points must be finite")
    influence = int(guide_curve_influence)
    if influence not in range(4):
        raise ValueError("guide_curve_influence must be a swGuideCurveInfluence_e value 0..3")
    if cut and influence != 0:
        raise ValueError("SW2025 InsertCutBlend does not expose guide-curve influence")
    start_type = int(start_matching_type)
    end_type = int(end_matching_type)
    if start_type not in range(4) or end_type not in range(4):
        raise ValueError("loft matching types must be swTangencyType_e values 0..3")
    if (start_type == 2) != (start_tangent_reference is not None):
        raise ValueError("start direction-vector tangency requires exactly one start reference")
    if (end_type == 2) != (end_tangent_reference is not None):
        raise ValueError("end direction-vector tangency requires exactly one end reference")
    start_length = _positive_finite("start_tangent_length", start_tangent_length)
    end_length = _positive_finite("end_tangent_length", end_tangent_length)
    if cut and (
        abs(start_length - 1.0) > 1e-15
        or abs(end_length - 1.0) > 1e-15
        or bool(reverse_start_tangent)
        or bool(reverse_end_tangent)
    ):
        raise ValueError(
            "SW2025 InsertCutBlend does not expose tangent lengths or reverse flags"
        )
    is_thin = thin_type is not None
    wall_type = 0 if thin_type is None else int(thin_type)
    if wall_type not in range(4):
        raise ValueError("thin_type must be a swThinWallType_e value 0..3")
    first_thickness = float(thickness1)
    second_thickness = float(thickness2)
    if is_thin:
        first_thickness = _positive_finite("thickness1", first_thickness)
        if wall_type == 3:
            second_thickness = _positive_finite("thickness2", second_thickness)
        elif second_thickness < 0.0 or not math.isfinite(second_thickness):
            raise ValueError("thickness2 must be finite and non-negative")
    elif abs(first_thickness) > 1e-15 or abs(second_thickness) > 1e-15:
        raise ValueError("thin thicknesses require thin_type")
    center = _feature_object(model, centerline) if centerline is not None else None
    start_reference = (
        _feature_object(model, start_tangent_reference)
        if start_tangent_reference is not None else None
    )
    end_reference = (
        _feature_object(model, end_tangent_reference)
        if end_tangent_reference is not None else None
    )
    model.ClearSelection2(True)
    try:
        for index, section in enumerate(sections):
            if pick_points is None:
                selected = _select_com_object(section, append=index > 0, mark=1)
            else:
                name = str(_safe_com_member(section, "Name", default=""))
                point = pick_points[index]
                selected = bool(model.Extension.SelectByID2(
                    name, "SKETCH", point[0], point[1], point[2],
                    index > 0, 1, _empty_callout(), 0,
                ))
            if not selected:
                raise RuntimeError(f"failed to select loft section at index {index}")
        for index, guide in enumerate(guides):
            mark = 2 if cut else 4096 * (index + 1) + 2
            if not _select_com_object(guide, append=True, mark=mark):
                raise RuntimeError(f"failed to select loft guide at index {index}")
        if center is not None and not _select_com_object(center, append=True, mark=4):
            raise RuntimeError("failed to select loft centerline")
        if start_reference is not None and not _select_com_object(
            start_reference, append=True, mark=8,
        ):
            raise RuntimeError("failed to select loft start direction reference")
        if end_reference is not None and not _select_com_object(
            end_reference, append=True, mark=32,
        ):
            raise RuntimeError("failed to select loft end direction reference")
        if cut:
            feature = model.FeatureManager.InsertCutBlend(
                bool(closed), bool(keep_tangency), False,
                1.0, start_type, end_type,
                is_thin, first_thickness, second_thickness, wall_type,
                True, True,
            )
        else:
            feature = model.FeatureManager.InsertProtrusionBlend2(
                bool(closed), bool(keep_tangency), False,
                1.0, start_type, end_type,
                start_length, end_length,
                bool(reverse_start_tangent), bool(reverse_end_tangent),
                is_thin, first_thickness, second_thickness, wall_type,
                bool(merge), True, True, influence,
            )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the advanced loft")
    return feature


def boundary_feature(
    model, direction1_curves, direction2_curves=(), *,
    feature_type=1, wants_solid=True, merge=True,
    direction1_data=None, direction2_data=None,
    direction_influence=(32, 32), trim_curves=(0, 0),
    closed_directions=(False, False),
    thin=False, thickness1=0.0, thickness2=0.0,
    reverse_thickness=False, thin_type=0, use_shared_thickness=False,
    cap_ends=False, end_thickness=0.0,
    auto_fillet=False, fillet_radius=0.0,
    force_nonrational=True, create_solid=None,
    allow_experimental=False, use_legacy=False,
):
    """Create a native Boundary base/boss/surface/cut with ``InsertNetBlend2``.

    ``feature_type`` follows the SW2025 type library: 0=base, 1=boss,
    2=surface, 3=cut.  Each item in ``direction*_data`` can be a mapping with
    ``tangency_type``, ``draft_angle``, ``tangent_length`` and ``apply_all``.
    Standard sketch curves, faces and edges use the documented selection marks
    ``8192*(index+1)+1/2`` for solid boundary features and marks 1/2 for a
    boundary surface.
    """
    d1 = tuple(_feature_object(model, item) for item in _as_tuple(direction1_curves))
    d2 = tuple(_feature_object(model, item) for item in _as_tuple(direction2_curves))
    kind = int(feature_type)
    if kind not in (0, 1, 2, 3):
        raise ValueError("feature_type must be 0=base, 1=boss, 2=surface, or 3=cut")
    if len(d1) < 2 and not (d1 and d2):
        raise ValueError("boundary feature requires two Direction-1 curves or both directions")

    def normalize_curve_data(items, values, label):
        if values is None:
            values = ({},) * len(items)
        values = tuple(values)
        if len(values) != len(items):
            raise ValueError(f"{label} must contain one item per curve")
        normalized = []
        for index, value in enumerate(values):
            value = dict(value)
            tangency = int(value.get("tangency_type", 0))
            if tangency not in (0, 1, 2, 3, 4, 6):
                raise ValueError(f"{label}[{index}] tangency_type is invalid")
            draft = float(value.get("draft_angle", 0.0))
            tangent_length = float(value.get("tangent_length", 1.0))
            if not math.isfinite(draft) or not math.isfinite(tangent_length) or tangent_length <= 0.0:
                raise ValueError(f"{label}[{index}] contains invalid curve data")
            normalized.append((
                tangency, draft, tangent_length,
                bool(value.get("apply_all", True)),
            ))
        return tuple(normalized)

    curve_data = (
        normalize_curve_data(d1, direction1_data, "direction1_data"),
        normalize_curve_data(d2, direction2_data, "direction2_data"),
    )
    influence = tuple(int(value) for value in direction_influence)
    trims = tuple(int(value) for value in trim_curves)
    closed = tuple(bool(value) for value in closed_directions)
    if len(influence) != 2 or len(trims) != 2 or len(closed) != 2:
        raise ValueError("direction settings must contain exactly two values")
    valid_influence = {0, 1, 2, 3, 16, 32, 64, 144}
    if any(value not in valid_influence for value in influence):
        raise ValueError("direction influence value is invalid")
    if any(value not in (0, 1) for value in trims):
        raise ValueError("trim_curves values must be 0 or 1")

    thin = bool(thin)
    first_thickness = float(thickness1)
    second_thickness = float(thickness2)
    wall_type = int(thin_type)
    if wall_type not in range(4):
        raise ValueError("thin_type must be a swThinWallType_e value 0..3")
    if thin:
        first_thickness = _positive_finite("thickness1", first_thickness)
        if wall_type == 3:
            second_thickness = _positive_finite("thickness2", second_thickness)
        elif second_thickness < 0.0 or not math.isfinite(second_thickness):
            raise ValueError("thickness2 must be finite and non-negative")
    elif abs(first_thickness) > 1e-15 or abs(second_thickness) > 1e-15:
        raise ValueError("boundary thicknesses require thin=True")
    cap_thickness = float(end_thickness)
    corner_radius = float(fillet_radius)
    if not math.isfinite(cap_thickness) or cap_thickness < 0.0:
        raise ValueError("end_thickness must be finite and non-negative")
    if bool(auto_fillet):
        corner_radius = _positive_finite("fillet_radius", corner_radius)
    elif not math.isfinite(corner_radius) or corner_radius < 0.0:
        raise ValueError("fillet_radius must be finite and non-negative")
    if create_solid is None:
        create_solid = kind != 2 and bool(wants_solid)
    call_thickness1 = first_thickness if thin else -1.0
    call_thickness2 = second_thickness if thin else -1.0
    call_wall_type = wall_type if thin else -1
    call_end_thickness = cap_thickness if bool(cap_ends) else -1.0
    call_fillet_radius = corner_radius if bool(auto_fillet) else -1.0

    if not bool(allow_experimental) or os.environ.get(
        "SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC"
    ) != "1":
        raise RuntimeError(
            "boundary feature creation is disabled because the SW2025 "
            "InsertNetBlend path can terminate SolidWorks; diagnostic use "
            "requires allow_experimental=True and "
            "SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC=1"
        )

    manager = _typed_sldworks_feature_manager(model.FeatureManager)
    short = int
    model.ClearSelection2(True)
    try:
        for direction, curves in enumerate((d1, d2)):
            for index, curve in enumerate(curves):
                mark = direction + 1 if kind == 2 else 8192 * (index + 1) + direction + 1
                append = bool(direction or index)
                if not _select_boundary_entity(
                    model, curve, append=append, mark=mark,
                ):
                    raise RuntimeError(
                        f"failed to select boundary direction {direction + 1} curve {index}"
                    )
        selection_evidence = []
        selection_manager = _safe_com_member(model, "SelectionManager")
        if selection_manager is not None:
            count = int(_safe_com_member(
                selection_manager, "GetSelectedObjectCount2", -1, default=0,
            ))
            selection_evidence = [
                (
                    int(_safe_com_member(
                        selection_manager, "GetSelectedObjectType3", index, -1,
                        default=-1,
                    )),
                    int(_safe_com_member(
                        selection_manager, "GetSelectedObjectMark", index,
                        default=-1,
                    )),
                )
                for index in range(1, count + 1)
            ]
        unsupported_types = sorted({
            object_type for object_type, _mark in selection_evidence
            if object_type not in (1, 2, 10)
        })
        if unsupported_types:
            raise RuntimeError(
                "unsafe Boundary selection entity types; use B-Rep edges/faces "
                "or true SKETCHSEGMENT selections, not external sketch proxies: "
                f"types={unsupported_types}, evidence={selection_evidence}"
            )
        for direction, values in enumerate(curve_data):
            for index, (tangency, draft, length, apply_all) in enumerate(values):
                manager.SetNetBlendCurveData(
                    short(direction), short(index), short(tangency),
                    draft, length, apply_all,
                )
            manager.SetNetBlendDirectionData(
                short(direction), short(influence[direction]),
                short(trims[direction]),
                closed[direction], False,
            )
        arguments = (
            short(kind), short(len(d1)), short(len(d2)), False, 0.0001,
            bool(wants_solid), bool(merge), True, True,
            thin, call_thickness1, call_thickness2,
            bool(reverse_thickness), short(call_wall_type), bool(use_shared_thickness),
            bool(cap_ends), call_end_thickness,
            bool(auto_fillet), call_fillet_radius, bool(force_nonrational),
        )
        # SW2025 marks InsertNetBlend obsolete, but its official Boundary
        # Surface example still uses the 20-argument member.  Keep that route
        # explicit and diagnostic-only; never retry it after InsertNetBlend2
        # consumes a selection set.
        if bool(use_legacy):
            insert_legacy = getattr(manager, "InsertNetBlend", None)
            feature = insert_legacy(*arguments) if callable(insert_legacy) else None
        else:
            insert2 = getattr(manager, "InsertNetBlend2", None)
            feature = (
                insert2(*arguments, bool(create_solid))
                if callable(insert2) else None
            )
    finally:
        try:
            model.ClearSelection2(True)
        except Exception:
            # A server-side Boundary fault can invalidate the document proxy.
            # Preserve the original creation error instead of masking it with
            # a second COM failure during best-effort selection cleanup.
            pass
    if feature is None:
        raise RuntimeError(
            "SolidWorks did not create the boundary feature; "
            f"selection evidence={selection_evidence}"
        )
    return feature


def boundary_boss(model, direction1_curves, direction2_curves=(), **kwargs):
    """Create a native solid Boundary Boss/Base feature."""
    kwargs.setdefault("feature_type", 1)
    kwargs.setdefault("wants_solid", True)
    kwargs.setdefault("create_solid", True)
    return boundary_feature(model, direction1_curves, direction2_curves, **kwargs)


def boundary_surface(model, direction1_curves, direction2_curves=(), **kwargs):
    """Create a native Boundary Surface feature."""
    kwargs.setdefault("feature_type", 2)
    kwargs.setdefault("wants_solid", False)
    kwargs.setdefault("merge", False)
    kwargs.setdefault("create_solid", False)
    return boundary_feature(model, direction1_curves, direction2_curves, **kwargs)


def boundary_surface_command(
    model, direction1_edges, direction2_edges, *,
    allow_experimental=False, wait_seconds=0.75,
):
    """Manual-only Boundary Surface diagnostic through a native PM command.

    This function opens a PropertyManager and is intentionally excluded from
    unattended live regressions.  Prefer ``boundary_surface`` once its direct
    COM route is verified for the requested geometry.
    """
    if not bool(allow_experimental) or os.environ.get(
        "SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC"
    ) != "1":
        raise RuntimeError(
            "Boundary Surface command requires allow_experimental=True and "
            "SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC=1"
        )
    d1 = tuple(_as_tuple(direction1_edges))
    d2 = tuple(_as_tuple(direction2_edges))
    if not d1 or not d2:
        raise ValueError("Boundary Surface command requires both edge directions")
    delay = float(wait_seconds)
    if not math.isfinite(delay) or delay < 0.0 or delay > 5.0:
        raise ValueError("wait_seconds must be finite and between 0 and 5")
    app = get_com_member(model, "GetSwApp")
    if app is None:
        raise RuntimeError("could not resolve the owning SolidWorks application")
    model.ClearSelection2(True)
    property_manager_open = False
    try:
        selected = 0
        for direction, curves in enumerate((d1, d2), start=1):
            for edge in curves:
                if not _select_boundary_entity(
                    model, edge, append=selected > 0, mark=direction,
                ):
                    raise RuntimeError("failed to select Boundary Surface edge")
                selected += 1
        manager = model.SelectionManager
        count = int(get_com_member(manager, "GetSelectedObjectCount2", -1))
        evidence = [
            (
                int(get_com_member(manager, "GetSelectedObjectType3", index, -1)),
                int(get_com_member(manager, "GetSelectedObjectMark", index)),
            )
            for index in range(1, count + 1)
        ]
        expected_marks = [1] * len(d1) + [2] * len(d2)
        if count != len(expected_marks) or any(item[0] != 1 for item in evidence) or [
            item[1] for item in evidence
        ] != expected_marks:
            raise RuntimeError(f"unsafe Boundary command selection: {evidence}")
        before = _last_model_feature(model)
        if not bool(get_com_member(app, "RunCommand", 618, "Boundary Surface")):
            raise RuntimeError("SolidWorks rejected Insert Boundary Surface command")
        property_manager_open = True
        if delay:
            time.sleep(delay)
        if not bool(get_com_member(app, "RunCommand", -2, "Accept Boundary Surface")):
            raise RuntimeError("SolidWorks rejected Boundary Surface PropertyManager OK")
        property_manager_open = False
        if delay:
            time.sleep(min(delay, 0.5))
        feature = _last_model_feature(model)
        if feature is None or _feature_key(feature) == _feature_key(before):
            raise RuntimeError("Boundary Surface command created no feature")
        return feature
    finally:
        if property_manager_open:
            try:
                get_com_member(app, "RunCommand", -1, "Cancel Boundary Surface")
            except Exception:
                pass
        try:
            model.ClearSelection2(True)
        except Exception:
            pass


def fillet(model, radius, edges=None):
    """
    倒圆角

    参数:
        model: IModelDoc2
        radius: 圆角半径（米）
        edges: 明确的边线列表；None 时保留调用方的当前选择（兼容旧代码）
    """
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("radius must be a positive finite value in metres")
    if edges is not None:
        _select_feature_edges(model, edges)
    try:
        feature = model.FeatureManager.FeatureFillet(
            195, radius, 0, 0, None, None, None
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the fillet feature")
    return feature


def create_feature_folder(model, features, *, name=None):
    """Create a native FeatureManager folder containing explicit features."""
    values = tuple(_feature_object(model, item) for item in _as_tuple(features))
    if not values:
        raise ValueError("at least one feature is required")
    model.ClearSelection2(True)
    try:
        for index, feature in enumerate(values):
            if not _select_com_object(feature, append=index > 0, mark=0):
                raise RuntimeError(f"failed to select feature at index {index}")
        folder_feature = model.FeatureManager.InsertFeatureTreeFolder2(2)
    finally:
        model.ClearSelection2(True)
    if folder_feature is None:
        raise RuntimeError("SolidWorks did not create the FeatureManager folder")
    if name is not None:
        requested = str(name).strip()
        if not requested:
            raise ValueError("folder name cannot be empty")
        folder_feature.Name = requested
        actual = str(get_com_member(folder_feature, "Name"))
        if actual != requested:
            raise RuntimeError(f"SolidWorks renamed the folder to {actual!r}")
    folder = get_com_member(folder_feature, "GetSpecificFeature2")
    count = int(get_com_member(folder, "GetFeatureCount"))
    if count < len(values):
        raise RuntimeError(
            f"FeatureManager folder contains {count} features, expected at least {len(values)}"
        )
    return folder_feature


def chamfer(model, distance, angle_deg=45, edges=None):
    """
    倒角

    参数:
        distance: 倒角距离（米）
        angle_deg: 倒角角度（度）
    """
    distance = float(distance)
    angle_deg = float(angle_deg)
    if not math.isfinite(distance) or distance <= 0.0:
        raise ValueError("distance must be a positive finite value in metres")
    if not math.isfinite(angle_deg) or not 0.0 < angle_deg < 90.0:
        raise ValueError("angle_deg must be between 0 and 90 degrees")
    if edges is not None:
        _select_feature_edges(model, edges)
    angle_rad = math.radians(angle_deg)
    try:
        feature = model.FeatureManager.InsertFeatureChamfer(
            4, 1, distance, angle_rad, 0, 0, 0, 0
        )
    finally:
        model.ClearSelection2(True)
    if feature is None:
        raise RuntimeError("SolidWorks did not create the chamfer feature")
    return feature


def linear_pattern(model, feature_name, d1_x, d1_y, d1_z, d1_spacing, d1_count,
                    d2_x=0, d2_y=0, d2_z=0, d2_spacing=0, d2_count=1):
    """
    线性阵列

    参数:
        feature_name: 要阵列的特征名称
        d1_*: 方向1 的方向向量、间距（米）和数量
        d2_*: 方向2（可选）
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    return model.FeatureManager.FeatureLinearPattern3(
        d1_spacing, d2_spacing,
        d1_count, d2_count,
        False, False,
        str(d1_x), str(d1_y), str(d1_z),
        str(d2_x), str(d2_y), str(d2_z),
        False, False
    )


def circular_pattern(model, feature_name, axis_name, angle_rad, count, equal_spacing=True):
    """
    圆形阵列

    参数:
        feature_name: 要阵列的特征名称
        axis_name: 旋转轴名称
        angle_rad: 总角度（弧度）
        count: 实例数量
        equal_spacing: True=等间距
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, axis_name, "AXIS", append=True, mark=1)
    return model.FeatureManager.FeatureCircularPattern4(
        count, angle_rad, False, "None", False, equal_spacing, False
    )


def shell(model, thickness, faces_to_remove=None, outward=False):
    """
    抽壳

    参数:
        thickness: 壁厚（米）
        faces_to_remove: 需预先选择要移除的面
    """
    thickness = _positive_finite("thickness", thickness)
    if faces_to_remove is not None:
        faces = _as_tuple(faces_to_remove)
        if not faces:
            raise ValueError("faces_to_remove cannot be empty")
        model.ClearSelection2(True)
        for index, face in enumerate(faces):
            if not _select_com_object(face, append=index > 0, mark=0):
                model.ClearSelection2(True)
                raise RuntimeError(f"failed to select shell removal face at index {index}")
    before_last = _last_model_feature(model)
    try:
        inserted = get_com_member(model, "InsertFeatureShell", thickness, bool(outward))
        feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
        if feature is None:
            feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last) or inserted is False:
        raise RuntimeError("SolidWorks did not create the shell feature")
    return feature


def mirror_feature(model, feature_name, mirror_plane_name):
    """
    镜像特征

    参数:
        feature_name: 要镜像的特征名称
        mirror_plane_name: 镜像基准面名称
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, mirror_plane_name, "PLANE", append=True, mark=1)
    return model.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)


def hole_wizard(model, hole_type, standard, fastener_type, size, depth, x, y, z):
    """
    异型孔向导（简化版）
    注意：完整的异型孔向导参数复杂，建议参考 API 文档调整
    """
    point = (float(x), float(y), float(z))
    candidates = []
    for face in solid_faces(model):
        try:
            geometry = planar_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        box = geometry["box"]
        if all(box[index] - 1e-7 <= point[index] <= box[index + 3] + 1e-7 for index in range(3)):
            candidates.append(face)
    if len(candidates) != 1:
        raise RuntimeError(f"hole position must resolve one planar face, got {len(candidates)}")
    diameter = _positive_finite("size", size)
    return hole_wizard_simple(
        model, candidates[0], point, diameter,
        depth=None if float(depth) <= 0.0 else float(depth),
        through=float(depth) <= 0.0,
        generic_hole_type=int(hole_type), standard_index=int(standard),
        fastener_type_index=int(fastener_type), size_name="",
    )


def hole_wizard_simple(
    model,
    face,
    position,
    diameter,
    *,
    depth=None,
    through=False,
    reverse_direction=False,
    generic_hole_type=2,
    standard_index=1,
    fastener_type_index=39,
    size_name="",
):
    """Create a native Hole Wizard simple hole on a selected planar face.

    Defaults are ``swWzdHole``, ANSI Metric and ANSI Metric drill sizes.  This
    white-list intentionally excludes tapped, counterbored and countersunk
    database semantics, which require their own parameter maps.
    """
    diameter = _positive_finite("diameter", diameter)
    if not through:
        depth = _positive_finite("depth", depth)
    else:
        depth = diameter if depth is None else _positive_finite("depth", depth)
    model.ClearSelection2(True)
    select_com_object_at(model, face, position, append=False, mark=0)
    before_last = _last_model_feature(model)
    try:
        feature = model.FeatureManager.HoleWizard5(
            int(generic_hole_type), int(standard_index), int(fastener_type_index),
            str(size_name), 1 if through else 0,
            diameter, depth, depth,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            "", bool(reverse_direction), True, True, False, False, False,
        )
        if feature is None:
            inserted = get_com_member(
                model, "HoleWizard",
                depth, 1 if through else 0, False, bool(reverse_direction), 0,
                diameter, 0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            )
            feature = inserted if inserted is not None and not isinstance(inserted, bool) else None
            if feature is None:
                feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
            if feature is None:
                feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last):
        raise RuntimeError("SolidWorks did not create the Hole Wizard feature")
    return feature


def rib_feature(
    model,
    sketch_name,
    thickness,
    *,
    two_sided=True,
    reverse_thickness=False,
    reverse_material=False,
    reference_edge_index=0,
    draft_angle_rad=0.0,
    draft_outward=False,
    normal_to_sketch=False,
    draft_from_wall=False,
):
    """Create a native rib from an open sketch using the SW2025 signature."""
    thickness = _positive_finite("thickness", thickness)
    draft_angle_rad = float(draft_angle_rad)
    if not math.isfinite(draft_angle_rad) or not 0.0 <= draft_angle_rad < math.pi / 2.0:
        raise ValueError("draft_angle_rad must be finite and in [0, pi/2)")
    reference_edge_index = int(reference_edge_index)
    if reference_edge_index < 0:
        raise ValueError("reference_edge_index cannot be negative")
    _ensure_sketch_selected(model, sketch_name)
    before_last = _last_model_feature(model)
    try:
        inserted = model.FeatureManager.InsertRib(
            bool(two_sided), bool(reverse_thickness), thickness,
            reference_edge_index, bool(reverse_material),
            draft_angle_rad > 0.0, bool(draft_outward), draft_angle_rad,
            bool(normal_to_sketch), bool(draft_from_wall),
        )
        feature = inserted if inserted is not None and not isinstance(inserted, bool) else None
        if feature is None:
            feature = _safe_com_member(model.FeatureManager, "GetLastFeatureAdded")
        if feature is None:
            feature = _last_model_feature(model)
    finally:
        model.ClearSelection2(True)
    if feature is None or _feature_key(feature) == _feature_key(before_last) or inserted is False:
        raise RuntimeError("SolidWorks did not create the rib feature")
    return feature


def rib(model, sketch_name, thickness, direction=True):
    """Backward-compatible rib wrapper; ``direction`` maps to two-sided mode."""
    return rib_feature(model, sketch_name, thickness, two_sided=bool(direction))
