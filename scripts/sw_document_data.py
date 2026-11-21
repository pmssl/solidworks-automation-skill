"""SolidWorks native configurations, parameters, and custom properties.

Every mutable path uses an API with explicit configuration scope and native
readback.  Matrix-style ``IConfiguration.GetParameters`` access is deliberately
read-only because SOLIDWORKS does not guarantee accurate values without a design
table and the corresponding Set APIs do not round-trip reliably in SW2025 COM.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

try:
    from .sw_connect import get_com_member, save_document
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member, save_document
    from sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()

PROPERTY_TYPES = {
    "number": 3,
    "double": 5,
    "yes_no": 11,
    "text": 30,
    "date": 64,
}
SET_VALUE_MODES = {
    "current": 1,
    "all": 2,
    "specific": 3,
}
SET_VALUE_STATUS = {
    0: "successful",
    1: "failure",
    2: "invalid_value",
    3: "driven_dimension",
    4: "model_not_loaded",
    5: "frozen_feature_owner",
}
FEATURE_SUPPRESSION_ACTIONS = {
    "suppress": 0,
    "unsuppress": 1,
    "unsuppress_dependent": 2,
}
FEATURE_CONFIGURATION_SCOPES = {
    "current": 1,
    "all": 2,
    "specific": 3,
}
BOM_PART_NUMBER_SOURCES = {
    "document_name": 1,
    "configuration_name": 2,
    "parent_name": 4,
    "user_specified": 8,
}
BOM_PART_NUMBER_SOURCE_NAMES = {
    value: key for key, value in BOM_PART_NUMBER_SOURCES.items()
}


def _configuration_names(model) -> list[str]:
    """返回文档配置名，兼容 COM 返回 tuple/list/None。"""
    names = get_com_member(model, "GetConfigurationNames")
    return [str(name) for name in (names or [])]


def _resolve_configuration_name(names: Sequence[str], requested: str) -> str | None:
    """@brief 按 SolidWorks 配置名不区分大小写语义返回实际名称。"""
    matches = [str(name) for name in names if str(name).casefold() == requested.casefold()]
    if len(matches) > 1:
        raise RuntimeError(f"配置名大小写匹配不唯一: {requested}")
    return matches[0] if matches else None


def _active_configuration_name(model) -> str:
    """@brief 返回当前活动配置名；接口不可用时返回空字符串。"""
    try:
        manager = get_com_member(model, "ConfigurationManager")
        active = get_com_member(manager, "ActiveConfiguration")
        return str(get_com_member(active, "Name") or "")
    except Exception:
        return ""


def inspect_configurations(model) -> dict[str, Any]:
    """@brief 读取配置清单和活动配置；基础清单/切换能力已真机验证。"""
    names = _configuration_names(model)
    current = _active_configuration_name(model)
    return {
        "status": "verified" if names else "blocked",
        "configurations": names,
        "active_configuration": current,
        "review_required": False,
        "limitations": ["不包含设计表创建/编辑", "复杂配置族仍需按层级、尺寸、属性、抑制状态、显示状态和实体几何逐项回读"],
    }


def _configuration_feature_evidence(model, *, traversal_limit: int = 10000) -> dict[str, Any]:
    """Collect top-level FeatureManager error evidence for the active configuration."""
    rows: list[dict[str, Any]] = []
    feature = get_com_member(model, "FirstFeature")
    while feature is not None:
        if len(rows) >= traversal_limit:
            raise RuntimeError(f"特征树遍历超过安全上限 {traversal_limit}")
        error_code = int(get_com_member(feature, "GetErrorCode") or 0)
        rows.append({
            "name": str(get_com_member(feature, "Name") or ""),
            "type": str(get_com_member(feature, "GetTypeName2") or ""),
            "error_code": error_code,
        })
        feature = get_com_member(feature, "GetNextFeature")
    return {
        "features": rows,
        "feature_count": len(rows),
        "feature_errors": [row for row in rows if row["error_code"] != 0],
    }


def _configuration_solid_body_evidence(model) -> dict[str, Any]:
    """Collect active-configuration solid body count, volume, and bounding boxes."""
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    rows: list[dict[str, Any]] = []
    for index, body in enumerate(bodies):
        mass_properties = tuple(get_com_member(body, "GetMassProperties", 1.0) or ())
        if len(mass_properties) < 4:
            raise RuntimeError(f"实体 {index} 的 GetMassProperties 返回值不完整")
        box_m = tuple(float(value) for value in (get_com_member(body, "GetBodyBox") or ()))
        if len(box_m) != 6:
            raise RuntimeError(f"实体 {index} 的 GetBodyBox 返回值不完整")
        rows.append({
            "index": index,
            "volume_mm3": float(mass_properties[3]) * 1e9,
            "bounding_box_mm": [value * 1000.0 for value in box_m],
        })
    if rows:
        boxes = [row["bounding_box_mm"] for row in rows]
        combined = [
            min(box[0] for box in boxes), min(box[1] for box in boxes),
            min(box[2] for box in boxes), max(box[3] for box in boxes),
            max(box[4] for box in boxes), max(box[5] for box in boxes),
        ]
    else:
        combined = None
    return {
        "solid_body_count": len(rows),
        "solid_bodies": rows,
        "volumes_mm3": sorted(row["volume_mm3"] for row in rows),
        "combined_bounding_box_mm": combined,
    }


def audit_configuration_rebuilds(
    model,
    configuration_names: Sequence[str] | None = None,
    *,
    force_rebuild: bool = True,
    restore_active: bool = True,
    require_solid_body: bool = True,
) -> dict[str, Any]:
    """Rebuild and geometrically audit selected native part configurations.

    The operation never saves.  Each configuration is activated, optionally
    rebuilt with ``ForceRebuild3(False)``, and checked for ``NeedsRebuild``,
    top-level feature errors, solid-body count, volumes, and bounding boxes.
    """
    available = _configuration_names(model)
    if not available:
        raise RuntimeError("当前文档没有可审计的配置")
    requested = list(configuration_names) if configuration_names is not None else list(available)
    if not requested:
        raise ValueError("configuration_names 不能为空")
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_name in requested:
        requested_name = str(raw_name).strip()
        if not requested_name:
            raise ValueError("configuration_names 不能包含空名称")
        name = _resolve_configuration_name(available, requested_name)
        if name is None:
            raise LookupError(f"找不到配置: {requested_name}")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"配置名称重复: {requested_name}")
        seen.add(key)
        resolved.append(name)

    active_before = _active_configuration_name(model)
    rows: list[dict[str, Any]] = []
    restoration_error = ""
    try:
        for name in resolved:
            activation = activate_configuration(model, name, rebuild=False, save=False)
            if not activation["success"]:
                rows.append({
                    "configuration": name,
                    "success": False,
                    "activation": activation,
                    "error": f"无法激活配置: {name}",
                })
                continue
            configuration = get_com_member(model, "GetConfigurationByName", name)
            if configuration is None:
                raise RuntimeError(f"无法取得配置对象: {name}")
            needs_rebuild_before = bool(get_com_member(configuration, "NeedsRebuild"))
            rebuild_success = (
                bool(get_com_member(model, "ForceRebuild3", False))
                if force_rebuild else True
            )
            configuration = get_com_member(model, "GetConfigurationByName", name)
            needs_rebuild_after = bool(get_com_member(configuration, "NeedsRebuild"))
            features = _configuration_feature_evidence(model)
            bodies = _configuration_solid_body_evidence(model)
            body_requirement_met = (
                not require_solid_body or bodies["solid_body_count"] > 0
            )
            success = (
                rebuild_success
                and not needs_rebuild_after
                and not features["feature_errors"]
                and body_requirement_met
            )
            rows.append({
                "configuration": name,
                "success": success,
                "activation": activation,
                "needs_rebuild_before": needs_rebuild_before,
                "needs_rebuild_after": needs_rebuild_after,
                "force_rebuild_requested": force_rebuild,
                "rebuild_success": rebuild_success,
                "require_solid_body": require_solid_body,
                "solid_body_requirement_met": body_requirement_met,
                **features,
                **bodies,
            })
    finally:
        if restore_active and active_before:
            try:
                restoration = activate_configuration(
                    model, active_before, rebuild=False, save=False,
                )
                if not restoration["success"]:
                    restoration_error = f"无法恢复活动配置: {active_before}"
            except Exception as exc:
                restoration_error = str(exc)

    active_after = _active_configuration_name(model)
    active_restored = not restore_active or active_after == active_before
    return {
        "success": (
            len(rows) == len(resolved)
            and all(row["success"] for row in rows)
            and active_restored
            and not restoration_error
        ),
        "configurations": rows,
        "configuration_names": resolved,
        "force_rebuild_requested": force_rebuild,
        "require_solid_body": require_solid_body,
        "active_before": active_before,
        "active_after": active_after,
        "restored_active": active_restored,
        "restoration_error": restoration_error,
        "saved": False,
    }


def inspect_configuration_properties(model, configuration_name: str) -> dict[str, Any]:
    """Read editable native properties of one part configuration."""
    requested = str(configuration_name).strip()
    if not requested:
        raise ValueError("configuration_name 不能为空")
    names = _configuration_names(model)
    name = _resolve_configuration_name(names, requested)
    if name is None:
        raise LookupError(f"找不到配置: {requested}")
    configuration = get_com_member(model, "GetConfigurationByName", name)
    if configuration is None:
        raise RuntimeError(f"无法取得配置对象: {name}")
    source_value = int(get_com_member(configuration, "BOMPartNoSource"))
    derived = bool(get_com_member(configuration, "IsDerived"))
    parent = get_com_member(configuration, "GetParent") if derived else None
    return {
        "configuration": name,
        "comment": str(get_com_member(configuration, "Comment") or ""),
        "description": str(get_com_member(configuration, "Description") or ""),
        "alternate_name": str(get_com_member(configuration, "AlternateName") or ""),
        "bom_part_number_source": BOM_PART_NUMBER_SOURCE_NAMES.get(
            source_value, f"unknown_{source_value}"
        ),
        "bom_part_number_source_value": source_value,
        "use_alternate_name_in_bom": bool(
            get_com_member(configuration, "UseAlternateNameInBOM")
        ),
        "use_description_in_bom": bool(
            get_com_member(configuration, "UseDescriptionInBOM")
        ),
        "suppress_new_features": bool(
            get_com_member(configuration, "SuppressNewFeatures")
        ),
        "derived": derived,
        "parent": str(get_com_member(parent, "Name")) if parent is not None else None,
        "active": _active_configuration_name(model) == name,
    }


def update_configuration_properties(
    model,
    configuration_name: str,
    *,
    comment: str | None = None,
    description: str | None = None,
    alternate_name: str | None = None,
    use_alternate_name_in_bom: bool | None = None,
    use_description_in_bom: bool | None = None,
    suppress_new_features: bool | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Update native configuration properties with readback and active-state safety."""
    before = inspect_configuration_properties(model, configuration_name)
    name = before["configuration"]
    requested_fields = {
        "comment": comment,
        "description": description,
        "alternate_name": alternate_name,
        "use_alternate_name_in_bom": use_alternate_name_in_bom,
        "use_description_in_bom": use_description_in_bom,
        "suppress_new_features": suppress_new_features,
    }
    if all(value is None for value in requested_fields.values()):
        raise ValueError("至少提供一个要修改的配置属性")

    active_before = _active_configuration_name(model)
    switched_for_inactive_property = False
    switch_target = None
    if suppress_new_features is not None and active_before == name:
        switch_target = next(
            (item for item in _configuration_names(model) if item.casefold() != name.casefold()),
            None,
        )
        if switch_target is None:
            raise ValueError("设置 suppress_new_features 需要至少一个其他配置用于临时切换")
        activation = activate_configuration(model, switch_target, rebuild=True, save=False)
        if not activation["success"]:
            raise RuntimeError(f"无法临时激活配置: {switch_target}")
        switched_for_inactive_property = True

    configuration = get_com_member(model, "GetConfigurationByName", name)
    if configuration is None:
        raise RuntimeError(f"无法取得配置对象: {name}")
    try:
        if comment is not None:
            setattr(configuration, "Comment", str(comment))
        if description is not None:
            setattr(configuration, "Description", str(description))
        if alternate_name is not None:
            setattr(configuration, "AlternateName", str(alternate_name))
        if use_alternate_name_in_bom is not None:
            setattr(
                configuration,
                "UseAlternateNameInBOM",
                bool(use_alternate_name_in_bom),
            )
        if use_description_in_bom is not None:
            setattr(configuration, "UseDescriptionInBOM", bool(use_description_in_bom))
        if suppress_new_features is not None:
            setattr(configuration, "SuppressNewFeatures", bool(suppress_new_features))
        rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild else True
    finally:
        if switched_for_inactive_property:
            restoration = activate_configuration(model, active_before, rebuild=True, save=False)
            if not restoration["success"]:
                raise RuntimeError(f"无法恢复活动配置: {active_before}")

    after = inspect_configuration_properties(model, name)
    requested_verified = True
    for field, value in requested_fields.items():
        if value is None:
            continue
        expected = bool(value) if field in {
            "use_alternate_name_in_bom", "use_description_in_bom",
            "suppress_new_features",
        } else str(value)
        requested_verified = requested_verified and after[field] == expected
    active_after = _active_configuration_name(model)
    active_restored = active_after == active_before
    hierarchy_preserved = (
        before["derived"] == after["derived"] and before["parent"] == after["parent"]
    )
    return {
        "success": (
            requested_verified and rebuild_success
            and active_restored and hierarchy_preserved
        ),
        "configuration": name,
        "before": before,
        "after": after,
        "requested": requested_fields,
        "requested_verified": requested_verified,
        "switched_for_inactive_property": switched_for_inactive_property,
        "temporary_configuration": switch_target,
        "active_before": active_before,
        "active_after": active_after,
        "active_restored": active_restored,
        "hierarchy_preserved": hierarchy_preserved,
        "rebuild_success": rebuild_success,
        "saved": False,
    }


def activate_configuration(
    model,
    configuration_name: str,
    *,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """@brief 激活现有配置并通过活动配置名回读验证。"""
    requested_name = str(configuration_name).strip()
    if not requested_name:
        raise ValueError("configuration_name 不能为空")
    names = _configuration_names(model)
    name = _resolve_configuration_name(names, requested_name)
    if name is None:
        raise LookupError(f"找不到配置: {requested_name}")

    before = _active_configuration_name(model)
    api_called = before != name
    api_return = bool(get_com_member(model, "ShowConfiguration2", name)) if api_called else None
    after = _active_configuration_name(model)
    readback_verified = after == name
    api_success = readback_verified
    rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild and readback_verified else readback_verified
    save_success = bool(save_document(model)) if save and readback_verified and rebuild_success else not save
    success = readback_verified and rebuild_success and save_success
    return {
        "success": success,
        "configuration": name,
        "requested_configuration": requested_name,
        "before": before,
        "after": after,
        "api_called": api_called,
        "api_return": api_return,
        "api_success": api_success,
        "readback_verified": readback_verified,
        "rebuild_success": rebuild_success,
        "save_requested": save,
        "save_success": save_success,
        "review_required": True,
    }


def create_configuration(
    model,
    configuration_name: str,
    *,
    comment: str = "",
    alternate_name: str = "",
    options: int = 0,
    if_exists: str = "reuse",
    activate: bool = True,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """@brief 使用 AddConfiguration3 创建配置，并校验清单及活动配置回读。

    ``options`` 对应官方 ``swConfigurationOptions2_e`` 位掩码。默认值 0 保持
    SolidWorks 默认行为；非零值必须由调用者基于目标版本枚举显式提供。
    """
    requested_name = str(configuration_name).strip()
    if not requested_name:
        raise ValueError("configuration_name 不能为空")
    if if_exists not in {"reuse", "error"}:
        raise ValueError("if_exists 只支持 reuse 或 error")
    if int(options) < 0:
        raise ValueError("options 不能为负数")

    before_names = _configuration_names(model)
    existing_name = _resolve_configuration_name(before_names, requested_name)
    existed = existing_name is not None
    name = existing_name or requested_name
    if existed and if_exists == "error":
        raise FileExistsError(f"配置已存在: {name}")

    created = None if existed else get_com_member(
        model,
        "AddConfiguration3",
        name,
        str(comment),
        str(alternate_name),
        int(options),
    )
    if not existed and created is None:
        raise RuntimeError(f"AddConfiguration3 未返回配置对象: {name}")

    after_names = _configuration_names(model)
    listed_name = _resolve_configuration_name(after_names, name)
    listed = listed_name is not None
    name = listed_name or name
    activation = (
        activate_configuration(model, name, rebuild=rebuild, save=False)
        if activate and listed
        else None
    )
    if activation:
        rebuild_success = bool(activation["rebuild_success"])
    elif rebuild and listed:
        rebuild_success = bool(get_com_member(model, "EditRebuild3"))
    else:
        rebuild_success = listed
    active_verified = activation["readback_verified"] if activation else True
    save_success = bool(save_document(model)) if save and listed and rebuild_success and active_verified else not save
    success = listed and rebuild_success and active_verified and save_success
    return {
        "success": success,
        "configuration": name,
        "requested_configuration": requested_name,
        "created": not existed,
        "reused": existed,
        "listed_after_create": listed,
        "configurations_before": before_names,
        "configurations_after": after_names,
        "options": int(options),
        "activation": activation,
        "save_requested": save,
        "save_success": save_success,
        "review_required": True,
    }


def feature_suppression_states(
    model,
    feature_name: str,
    *,
    configuration_names: Sequence[str] | None = None,
    restore_active: bool = True,
) -> dict[str, Any]:
    """Read one feature's suppression state in explicit configurations.

    The readback intentionally activates each configuration and uses
    ``IFeature.IsSuppressed``. This verifies the resolved model state instead
    of trusting only the array returned by ``IsSuppressed2``.
    """
    requested_feature = str(feature_name).strip()
    if not requested_feature:
        raise ValueError("feature_name 不能为空")
    if get_com_member(model, "FeatureByName", requested_feature) is None:
        raise LookupError(f"找不到特征: {requested_feature}")
    available = _configuration_names(model)
    requested = list(configuration_names or available)
    if not requested:
        raise ValueError("configuration_names 不能为空")
    resolved = []
    for raw_name in requested:
        name = _resolve_configuration_name(available, str(raw_name).strip())
        if name is None:
            raise LookupError(f"找不到配置: {raw_name}")
        if name not in resolved:
            resolved.append(name)

    original = _active_configuration_name(model)
    states: dict[str, bool] = {}
    try:
        for name in resolved:
            activation = activate_configuration(model, name, rebuild=True, save=False)
            if not activation["success"]:
                raise RuntimeError(f"无法激活配置以读取特征抑制状态: {name}")
            feature = get_com_member(model, "FeatureByName", requested_feature)
            if feature is None:
                raise RuntimeError(f"配置 {name} 中找不到特征: {requested_feature}")
            states[name] = bool(get_com_member(feature, "IsSuppressed"))
    finally:
        if restore_active and original and original in available:
            activate_configuration(model, original, rebuild=True, save=False)
    return {
        "feature": requested_feature,
        "states": states,
        "active_before": original,
        "active_after": _active_configuration_name(model),
        "restored_active": not restore_active or _active_configuration_name(model) == original,
    }


def set_feature_suppression(
    model,
    feature_name: str,
    action: str,
    *,
    configuration_mode: str = "current",
    configuration_names: Sequence[str] | None = None,
    rebuild: bool = True,
    restore_active: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """Set native feature suppression in current, all, or named configurations."""
    requested_feature = str(feature_name).strip()
    if not requested_feature:
        raise ValueError("feature_name 不能为空")
    if action not in FEATURE_SUPPRESSION_ACTIONS:
        raise ValueError(f"不支持的特征抑制动作: {action}")
    if configuration_mode not in FEATURE_CONFIGURATION_SCOPES:
        raise ValueError(f"不支持的配置范围: {configuration_mode}")
    feature = get_com_member(model, "FeatureByName", requested_feature)
    if feature is None:
        raise LookupError(f"找不到特征: {requested_feature}")

    available = _configuration_names(model)
    active_before = _active_configuration_name(model)
    raw_names = [str(name).strip() for name in (configuration_names or ()) if str(name).strip()]
    if configuration_mode == "specific" and not raw_names:
        raise ValueError("specific 模式必须提供 configuration_names")
    if configuration_mode != "specific" and raw_names:
        raise ValueError("configuration_names 仅适用于 specific 模式")
    resolved_names = []
    for raw_name in raw_names:
        name = _resolve_configuration_name(available, raw_name)
        if name is None:
            raise LookupError(f"找不到配置: {raw_name}")
        if name not in resolved_names:
            resolved_names.append(name)

    if configuration_mode == "specific":
        evidence_names = resolved_names
        names_argument = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_BSTR, tuple(resolved_names),
        )
    elif configuration_mode == "all":
        evidence_names = available
        names_argument = VARIANT(pythoncom.VT_EMPTY, None)
    else:
        evidence_names = [active_before]
        names_argument = VARIANT(pythoncom.VT_EMPTY, None)

    requested_suppressed = action == "suppress"
    api_success = bool(feature.SetSuppression2(
        FEATURE_SUPPRESSION_ACTIONS[action],
        FEATURE_CONFIGURATION_SCOPES[configuration_mode],
        names_argument,
    ))
    rebuild_success = (
        bool(get_com_member(model, "EditRebuild3")) if rebuild and api_success else api_success
    )
    readback = feature_suppression_states(
        model,
        requested_feature,
        configuration_names=evidence_names,
        restore_active=restore_active,
    )
    state_verified = all(
        state == requested_suppressed for state in readback["states"].values()
    )
    save_success = (
        bool(save_document(model))
        if save and api_success and rebuild_success and state_verified
        else not save
    )
    return {
        "success": api_success and rebuild_success and state_verified and save_success,
        "feature": requested_feature,
        "action": action,
        "configuration_mode": configuration_mode,
        "configuration_names": resolved_names,
        "active_before": active_before,
        "api_success": api_success,
        "rebuild_success": rebuild_success,
        "requested_suppressed": requested_suppressed,
        "readback": readback,
        "state_verified": state_verified,
        "save_requested": save,
        "save_success": save_success,
    }


def _dimension_value_mm(dimension, configuration_name: str | None = None) -> float:
    """读取尺寸系统值并转为毫米。"""
    if configuration_name:
        return float(dimension.GetSystemValue2(configuration_name)) * 1000.0
    return float(get_com_member(dimension, "SystemValue")) * 1000.0


def update_dimension_mm(
    model,
    dimension_name: str,
    value_mm: float,
    *,
    configuration_mode: str = "current",
    configuration_names: Sequence[str] | None = None,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """修改命名尺寸并返回可审计证据。

    ``configuration_mode`` 支持 ``current``、``all``、``specific``；specific
    必须提供配置名。SolidWorks API 内部单位为米。
    """
    if not dimension_name.strip():
        raise ValueError("dimension_name 不能为空")
    if value_mm <= 0:
        raise ValueError("value_mm 必须大于 0")
    if configuration_mode not in SET_VALUE_MODES:
        raise ValueError(f"不支持的配置范围: {configuration_mode}")

    dimension = model.Parameter(dimension_name)
    if dimension is None:
        raise LookupError(f"找不到尺寸: {dimension_name}")

    requested_names = [str(name).strip() for name in (configuration_names or []) if str(name).strip()]
    if configuration_mode == "specific" and not requested_names:
        raise ValueError("specific 模式必须提供 configuration_names")
    if configuration_mode == "all":
        evidence_names = _configuration_names(model)
    elif configuration_mode == "specific":
        evidence_names = requested_names
    else:
        evidence_names = []

    before = (
        {name: _dimension_value_mm(dimension, name) for name in evidence_names}
        if evidence_names
        else {"current": _dimension_value_mm(dimension)}
    )
    names_variant = (
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, requested_names)
        if configuration_mode == "specific"
        else None
    )
    status_code = int(
        dimension.SetSystemValue3(
            float(value_mm) / 1000.0,
            SET_VALUE_MODES[configuration_mode],
            names_variant,
        )
    )
    rebuild_success = (
        bool(get_com_member(model, "EditRebuild3"))
        if rebuild and status_code == 0
        else status_code == 0
    )
    after = (
        {name: _dimension_value_mm(dimension, name) for name in evidence_names}
        if evidence_names
        else {"current": _dimension_value_mm(dimension)}
    )
    save_success = bool(save_document(model)) if save and status_code == 0 and rebuild_success else not save
    success = status_code == 0 and rebuild_success and save_success
    return {
        "success": success,
        "dimension": dimension_name,
        "configuration_mode": configuration_mode,
        "configuration_names": requested_names,
        "requested_mm": float(value_mm),
        "before_mm": before,
        "after_mm": after,
        "set_status": status_code,
        "set_status_label": SET_VALUE_STATUS.get(status_code, f"unknown_{status_code}"),
        "rebuild_success": rebuild_success,
        "save_requested": save,
        "save_success": save_success,
    }


def _property_manager(model, configuration_name: str = ""):
    manager = model.Extension.CustomPropertyManager(configuration_name)
    if manager is None:
        scope = configuration_name or "文件级"
        raise RuntimeError(f"无法取得 {scope} 自定义属性管理器")
    return manager


def read_custom_property(model, name: str, *, configuration_name: str = "") -> dict[str, Any]:
    """读取一个文件级或配置级自定义属性。"""
    manager = _property_manager(model, configuration_name)
    raw_value = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    resolved_value = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    was_resolved = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    is_linked = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    status = int(manager.Get6(name, False, raw_value, resolved_value, was_resolved, is_linked))
    return {
        "name": name,
        "configuration": configuration_name,
        "status": status,
        "exists": status != 1,
        "raw": str(raw_value.value or ""),
        "resolved": str(resolved_value.value or ""),
        "was_resolved": bool(was_resolved.value),
        "is_linked": bool(is_linked.value),
    }


def set_custom_properties(
    model,
    properties: Mapping[str, Any],
    *,
    configuration_name: str = "",
    property_type: str = "text",
    save: bool = False,
) -> dict[str, Any]:
    """写入文件级或配置级属性，并逐项回读验证。"""
    if not properties:
        raise ValueError("properties 不能为空")
    if property_type not in PROPERTY_TYPES:
        raise ValueError(f"不支持的属性类型: {property_type}")
    manager = _property_manager(model, configuration_name)
    results = []
    for raw_name, raw_value in properties.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("属性名不能为空")
        value = str(raw_value)
        add_status = int(manager.Add3(name, PROPERTY_TYPES[property_type], value, 2))
        readback = read_custom_property(model, name, configuration_name=configuration_name)
        verified = add_status == 0 and readback["exists"] and readback["raw"] == value
        results.append({
            "name": name,
            "requested": value,
            "add_status": add_status,
            "verified": verified,
            "readback": readback,
        })
    save_success = bool(save_document(model)) if save and all(item["verified"] for item in results) else not save
    return {
        "success": all(item["verified"] for item in results) and save_success,
        "configuration": configuration_name,
        "property_type": property_type,
        "properties": results,
        "save_requested": save,
        "save_success": save_success,
    }


def apply_configuration_family(
    model,
    configuration_specs: Sequence[Mapping[str, Any]],
    *,
    restore_active: bool = True,
) -> dict[str, Any]:
    """Create/update a native configuration family without a design table.

    Each specification requires ``name`` and may contain ``dimensions_mm``,
    ``properties`` and ``feature_suppression`` mappings.  The complete request
    is validated before mutation.  Operations use explicit configuration scope
    and never save the document or open Excel/design-table UI.
    """
    specs = tuple(configuration_specs)
    if not specs:
        raise ValueError("configuration_specs 不能为空")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_spec in enumerate(specs):
        if not isinstance(raw_spec, Mapping):
            raise ValueError(f"配置族条目 {index} 必须是映射")
        name = str(raw_spec.get("name", "")).strip()
        if not name:
            raise ValueError(f"配置族条目 {index} 缺少 name")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"配置族名称重复: {name}")
        seen.add(key)
        dimensions = dict(raw_spec.get("dimensions_mm") or {})
        properties = dict(raw_spec.get("properties") or {})
        suppressions = dict(raw_spec.get("feature_suppression") or {})
        for dimension_name, value_mm in dimensions.items():
            if not str(dimension_name).strip() or float(value_mm) <= 0:
                raise ValueError(f"配置 {name} 包含无效尺寸")
        for feature_name, action in suppressions.items():
            if not str(feature_name).strip() or action not in FEATURE_SUPPRESSION_ACTIONS:
                raise ValueError(f"配置 {name} 包含无效特征抑制动作")
        if any(not str(prop_name).strip() for prop_name in properties):
            raise ValueError(f"配置 {name} 包含空属性名")
        normalized.append({
            "name": name,
            "dimensions_mm": dimensions,
            "properties": properties,
            "feature_suppression": suppressions,
        })

    active_before = _active_configuration_name(model)
    results = []
    try:
        for spec in normalized:
            name = spec["name"]
            creation = create_configuration(
                model, name, if_exists="reuse", activate=False,
                rebuild=False, save=False,
            )
            dimension_results = [
                update_dimension_mm(
                    model, str(dimension_name), float(value_mm),
                    configuration_mode="specific", configuration_names=(name,),
                    rebuild=False, save=False,
                )
                for dimension_name, value_mm in spec["dimensions_mm"].items()
            ]
            property_result = (
                set_custom_properties(
                    model, spec["properties"], configuration_name=name, save=False,
                )
                if spec["properties"] else None
            )
            suppression_results = [
                set_feature_suppression(
                    model, str(feature_name), str(action),
                    configuration_mode="specific", configuration_names=(name,),
                    rebuild=False, restore_active=True, save=False,
                )
                for feature_name, action in spec["feature_suppression"].items()
            ]
            success = (
                creation["success"]
                and all(item["success"] for item in dimension_results)
                and (property_result is None or property_result["success"])
                and all(item["success"] for item in suppression_results)
            )
            results.append({
                "name": name,
                "success": success,
                "creation": creation,
                "dimensions": dimension_results,
                "properties": property_result,
                "feature_suppression": suppression_results,
            })
        rebuild_success = bool(get_com_member(model, "EditRebuild3"))
    finally:
        if restore_active and active_before:
            available = _configuration_names(model)
            if _resolve_configuration_name(available, active_before):
                activate_configuration(model, active_before, rebuild=True, save=False)
    active_after = _active_configuration_name(model)
    restored = not restore_active or active_after == active_before
    return {
        "success": all(item["success"] for item in results) and rebuild_success and restored,
        "configurations": results,
        "active_before": active_before,
        "active_after": active_after,
        "restored_active": restored,
        "rebuild_success": rebuild_success,
        "saved": False,
    }


def _configuration_object(model, configuration_name: str | None = None):
    """Resolve a native configuration object by name or use the active one."""
    if configuration_name is None:
        manager = get_com_member(model, "ConfigurationManager")
        configuration = get_com_member(manager, "ActiveConfiguration")
    else:
        requested = str(configuration_name).strip()
        if not requested:
            raise ValueError("configuration_name 不能为空")
        resolved = _resolve_configuration_name(_configuration_names(model), requested)
        if resolved is None:
            raise LookupError(f"找不到配置: {requested}")
        configuration = get_com_member(model, "GetConfigurationByName", resolved)
    if configuration is None:
        raise RuntimeError("无法取得配置对象")
    return configuration


def inspect_display_states(model, *, configuration_name: str | None = None) -> dict[str, Any]:
    """Read display-state names; the first native entry is the active state."""
    configuration = _configuration_object(model, configuration_name)
    names = [str(name) for name in (get_com_member(configuration, "GetDisplayStates") or ())]
    return {
        "configuration": str(get_com_member(configuration, "Name")),
        "display_states": names,
        "active_display_state": names[0] if names else "",
        "count": int(get_com_member(configuration, "GetDisplayStatesCount")),
    }


def create_display_state(
    model,
    display_state_name: str,
    *,
    configuration_name: str | None = None,
    if_exists: str = "reuse",
    activate: bool = True,
) -> dict[str, Any]:
    """Create and optionally activate a native configuration display state."""
    requested = str(display_state_name).strip()
    if not requested:
        raise ValueError("display_state_name 不能为空")
    if if_exists not in {"reuse", "error"}:
        raise ValueError("if_exists 只支持 reuse 或 error")
    configuration = _configuration_object(model, configuration_name)
    before = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    matches = [name for name in before["display_states"] if name.casefold() == requested.casefold()]
    if len(matches) > 1:
        raise RuntimeError(f"显示状态名大小写匹配不唯一: {requested}")
    existed = bool(matches)
    actual_name = matches[0] if matches else requested
    if existed and if_exists == "error":
        raise FileExistsError(f"显示状态已存在: {actual_name}")
    api_success = True if existed else bool(configuration.CreateDisplayState(actual_name))
    if activate and api_success:
        api_success = bool(configuration.ApplyDisplayState(actual_name))
    after = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    listed = any(name.casefold() == actual_name.casefold() for name in after["display_states"])
    active_verified = not activate or after["active_display_state"].casefold() == actual_name.casefold()
    return {
        "success": api_success and listed and active_verified,
        "configuration": after["configuration"],
        "display_state": actual_name,
        "created": not existed,
        "reused": existed,
        "active_verified": active_verified,
        "states_before": before["display_states"],
        "states_after": after["display_states"],
    }


def activate_display_state(
    model, display_state_name: str, *, configuration_name: str | None = None,
) -> dict[str, Any]:
    """Apply a named display state and verify it becomes the first state."""
    configuration = _configuration_object(model, configuration_name)
    before = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    matches = [
        name for name in before["display_states"]
        if name.casefold() == str(display_state_name).strip().casefold()
    ]
    if not matches:
        raise LookupError(f"找不到显示状态: {display_state_name}")
    name = matches[0]
    api_success = bool(configuration.ApplyDisplayState(name))
    after = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    return {
        "success": api_success and after["active_display_state"] == name,
        "configuration": after["configuration"],
        "display_state": name,
        "active_before": before["active_display_state"],
        "active_after": after["active_display_state"],
    }


def rename_display_state(
    model, old_name: str, new_name: str, *, configuration_name: str | None = None,
) -> dict[str, Any]:
    """Rename one native display state and verify the name list."""
    configuration = _configuration_object(model, configuration_name)
    old_name, new_name = str(old_name).strip(), str(new_name).strip()
    if not old_name or not new_name:
        raise ValueError("old_name 和 new_name 不能为空")
    before = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    if not any(name.casefold() == old_name.casefold() for name in before["display_states"]):
        raise LookupError(f"找不到显示状态: {old_name}")
    if any(name.casefold() == new_name.casefold() for name in before["display_states"]):
        raise FileExistsError(f"显示状态已存在: {new_name}")
    api_success = bool(configuration.RenameDisplayState(old_name, new_name))
    after = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    verified = (
        any(name.casefold() == new_name.casefold() for name in after["display_states"])
        and not any(name.casefold() == old_name.casefold() for name in after["display_states"])
    )
    return {"success": api_success and verified, "before": before, "after": after}


def delete_display_state(
    model, display_state_name: str, *, configuration_name: str | None = None,
) -> dict[str, Any]:
    """Delete a non-active native display state and verify removal."""
    configuration = _configuration_object(model, configuration_name)
    requested = str(display_state_name).strip()
    if not requested:
        raise ValueError("display_state_name 不能为空")
    before = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    matches = [name for name in before["display_states"] if name.casefold() == requested.casefold()]
    if not matches:
        raise LookupError(f"找不到显示状态: {requested}")
    name = matches[0]
    if before["active_display_state"] == name:
        raise ValueError("不能删除当前活动显示状态；请先激活另一显示状态")
    api_success = bool(configuration.DeleteDisplayState(name))
    after = inspect_display_states(
        model, configuration_name=str(get_com_member(configuration, "Name")),
    )
    removed = not any(item.casefold() == name.casefold() for item in after["display_states"])
    return {"success": api_success and removed, "before": before, "after": after}


def configuration_hierarchy(model) -> dict[str, Any]:
    """Read native parent/child relationships for every configuration."""
    nodes: dict[str, dict[str, Any]] = {}
    for name in _configuration_names(model):
        configuration = get_com_member(model, "GetConfigurationByName", name)
        if configuration is None:
            raise RuntimeError(f"无法取得配置对象: {name}")
        derived = bool(get_com_member(configuration, "IsDerived"))
        parent = get_com_member(configuration, "GetParent") if derived else None
        children = [
            str(get_com_member(child, "Name"))
            for child in (get_com_member(configuration, "GetChildren") or ())
        ]
        nodes[name] = {
            "derived": derived,
            "parent": str(get_com_member(parent, "Name")) if parent is not None else None,
            "children": children,
        }
    return {"configurations": nodes, "active_configuration": _active_configuration_name(model)}


def rename_configuration(
    model,
    configuration_name: str,
    new_name: str,
    *,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Rename one native configuration through ``IConfiguration.Name``."""
    requested = str(configuration_name).strip()
    requested_new = str(new_name).strip()
    if not requested or not requested_new:
        raise ValueError("configuration_name 和 new_name 不能为空")
    names_before = _configuration_names(model)
    name = _resolve_configuration_name(names_before, requested)
    if name is None:
        raise LookupError(f"找不到配置: {requested}")
    collision = _resolve_configuration_name(names_before, requested_new)
    if collision is not None and collision.casefold() != name.casefold():
        raise FileExistsError(f"配置已存在: {collision}")
    if requested_new == name:
        return {
            "success": requested_new == name,
            "renamed": False,
            "configuration_before": name,
            "configuration_after": name,
            "configurations_before": names_before,
            "configurations_after": names_before,
            "active_before": _active_configuration_name(model),
            "active_after": _active_configuration_name(model),
            "hierarchy_before": configuration_hierarchy(model),
            "hierarchy_after": configuration_hierarchy(model),
            "rebuild_success": True,
            "saved": False,
        }

    hierarchy_before = configuration_hierarchy(model)
    active_before = hierarchy_before["active_configuration"]
    configuration = get_com_member(model, "GetConfigurationByName", name)
    if configuration is None:
        raise RuntimeError(f"无法取得配置对象: {name}")
    setattr(configuration, "Name", requested_new)

    names_after = _configuration_names(model)
    actual_new = next((item for item in names_after if item == requested_new), None)
    old_removed = name not in names_after
    if actual_new is None or not old_removed:
        raise RuntimeError(
            f"配置重命名回读失败: before={names_before}, after={names_after}"
        )
    rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild else True
    hierarchy_after = configuration_hierarchy(model)
    active_after = hierarchy_after["active_configuration"]
    expected_active = actual_new if active_before.casefold() == name.casefold() else active_before
    active_verified = active_after == expected_active
    expected_nodes: dict[str, dict[str, Any]] = {}
    for node_name, node in hierarchy_before["configurations"].items():
        expected_name = actual_new if node_name == name else node_name
        expected_nodes[expected_name] = {
            "derived": node["derived"],
            "parent": actual_new if node["parent"] == name else node["parent"],
            "children": [actual_new if child == name else child for child in node["children"]],
        }
    hierarchy_preserved = hierarchy_after["configurations"] == expected_nodes
    return {
        "success": rebuild_success and active_verified and hierarchy_preserved,
        "renamed": True,
        "configuration_before": name,
        "configuration_after": actual_new,
        "configurations_before": names_before,
        "configurations_after": names_after,
        "active_before": active_before,
        "active_after": active_after,
        "active_verified": active_verified,
        "hierarchy_before": hierarchy_before,
        "hierarchy_after": hierarchy_after,
        "hierarchy_preserved": hierarchy_preserved,
        "rebuild_success": rebuild_success,
        "saved": False,
    }


def delete_configuration(
    model,
    configuration_name: str,
    *,
    include_descendants: bool = False,
    fallback_configuration: str | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Delete a native configuration safely, optionally including its subtree.

    SOLIDWORKS cannot delete the active configuration.  The wrapper therefore
    resolves the full target set first, activates a configuration that will be
    retained when necessary, and deletes descendants before their parent.
    """
    requested = str(configuration_name).strip()
    if not requested:
        raise ValueError("configuration_name 不能为空")
    names_before = _configuration_names(model)
    name = _resolve_configuration_name(names_before, requested)
    if name is None:
        raise LookupError(f"找不到配置: {requested}")
    if len(names_before) <= 1:
        raise ValueError("不能删除文档中的唯一配置")

    hierarchy_before = configuration_hierarchy(model)
    nodes = hierarchy_before["configurations"]
    visiting: set[str] = set()
    visited: set[str] = set()
    delete_order: list[str] = []

    def collect_postorder(current: str) -> None:
        if current in visiting:
            raise RuntimeError(f"配置层级存在循环: {current}")
        if current in visited:
            return
        visiting.add(current)
        for child in nodes[current]["children"]:
            collect_postorder(child)
        visiting.remove(current)
        visited.add(current)
        delete_order.append(current)

    children = list(nodes[name]["children"])
    if children and not include_descendants:
        raise ValueError(
            f"配置 {name} 仍有子配置 {children}；删除整棵子树需 include_descendants=True"
        )
    collect_postorder(name)
    target_keys = {item.casefold() for item in delete_order}
    remaining = [item for item in names_before if item.casefold() not in target_keys]
    if not remaining:
        raise ValueError("删除目标会移除文档中的全部配置")

    if fallback_configuration is not None:
        requested_fallback = str(fallback_configuration).strip()
        if not requested_fallback:
            raise ValueError("fallback_configuration 不能为空")
        fallback = _resolve_configuration_name(names_before, requested_fallback)
        if fallback is None:
            raise LookupError(f"找不到回退配置: {requested_fallback}")
        if fallback.casefold() in target_keys:
            raise ValueError("fallback_configuration 不能位于删除目标中")
    else:
        fallback = remaining[0]

    active_before = hierarchy_before["active_configuration"]
    activation = None
    if active_before.casefold() in target_keys:
        activation = activate_configuration(model, fallback, rebuild=True, save=False)
        if not activation["success"]:
            raise RuntimeError(f"删除前无法激活回退配置: {fallback}")

    deleted: list[str] = []
    for target in delete_order:
        api_success = bool(get_com_member(model, "DeleteConfiguration2", target))
        still_present = _resolve_configuration_name(_configuration_names(model), target)
        if not api_success or still_present is not None:
            raise RuntimeError(
                f"删除配置失败: {target}; 已删除={deleted}; api_success={api_success}"
            )
        deleted.append(target)

    names_after = _configuration_names(model)
    rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild else True
    active_after = _active_configuration_name(model)
    expected_active = fallback if active_before.casefold() in target_keys else active_before
    active_verified = active_after == expected_active
    return {
        "success": rebuild_success and active_verified,
        "configuration": name,
        "include_descendants": bool(include_descendants),
        "delete_order": delete_order,
        "deleted": deleted,
        "configurations_before": names_before,
        "configurations_after": names_after,
        "active_before": active_before,
        "active_after": active_after,
        "fallback_configuration": fallback,
        "activation": activation,
        "active_verified": active_verified,
        "hierarchy_before": hierarchy_before,
        "hierarchy_after": configuration_hierarchy(model),
        "rebuild_success": rebuild_success,
        "saved": False,
    }


def create_derived_configuration(
    model,
    configuration_name: str,
    parent_configuration_name: str,
    *,
    comment: str = "",
    alternate_name: str = "",
    description: str = "",
    options: int = 0,
    rebuild: bool = True,
    restore_active: bool = True,
) -> dict[str, Any]:
    """Create a native derived configuration with ``AddConfiguration2``."""
    requested = str(configuration_name).strip()
    requested_parent = str(parent_configuration_name).strip()
    if not requested or not requested_parent:
        raise ValueError("configuration_name 和 parent_configuration_name 不能为空")
    if int(options) < 0:
        raise ValueError("options 不能为负数")
    names_before = _configuration_names(model)
    if _resolve_configuration_name(names_before, requested) is not None:
        raise FileExistsError(f"配置已存在: {requested}")
    parent_name = _resolve_configuration_name(names_before, requested_parent)
    if parent_name is None:
        raise LookupError(f"找不到父配置: {requested_parent}")
    active_before = _active_configuration_name(model)
    manager = get_com_member(model, "ConfigurationManager")
    created = manager.AddConfiguration2(
        requested, str(comment), str(alternate_name), int(options),
        parent_name, str(description), bool(rebuild),
    )
    if created is None:
        raise RuntimeError("AddConfiguration2 未返回派生配置")
    names_after = _configuration_names(model)
    actual_name = _resolve_configuration_name(names_after, requested)
    if actual_name is None:
        raise RuntimeError("派生配置未出现在配置清单中")
    child = get_com_member(model, "GetConfigurationByName", actual_name)
    derived = bool(get_com_member(child, "IsDerived"))
    parent = get_com_member(child, "GetParent") if derived else None
    parent_readback = str(get_com_member(parent, "Name")) if parent is not None else None
    rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild else True
    if restore_active and active_before:
        activate_configuration(model, active_before, rebuild=True, save=False)
    active_after = _active_configuration_name(model)
    restored = not restore_active or active_after == active_before
    return {
        "success": derived and parent_readback == parent_name and rebuild_success and restored,
        "configuration": actual_name,
        "parent": parent_readback,
        "derived": derived,
        "configurations_before": names_before,
        "configurations_after": names_after,
        "active_before": active_before,
        "active_after": active_after,
        "restored_active": restored,
        "rebuild_success": rebuild_success,
        "saved": False,
    }


def read_configuration_parameters(model, configuration_name: str) -> dict[str, Any]:
    """Read the native parameter matrix exposed by ``IConfiguration``.

    This is deliberately read-only.  SOLIDWORKS documents that values returned
    without a design table may be inaccurate, so callers must validate resolved
    dimensions, suppression states, and geometry before treating a row as an
    engineering result.
    """
    requested = str(configuration_name).strip()
    if not requested:
        raise ValueError("configuration_name 不能为空")
    available = _configuration_names(model)
    name = _resolve_configuration_name(available, requested)
    if name is None:
        raise LookupError(f"找不到配置: {requested}")
    configuration = get_com_member(model, "GetConfigurationByName", name)
    if configuration is None:
        raise RuntimeError(f"无法取得配置对象: {name}")

    reported_count = int(get_com_member(configuration, "GetParameterCount"))
    if reported_count < 0:
        raise RuntimeError(f"配置参数数量无效: {reported_count}")
    params = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
    values = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
    get_com_member(configuration, "GetParameters", params, values)
    names = tuple(str(item) for item in (params.value or ()))
    read_values = tuple(str(item) for item in (values.value or ()))
    if len(names) != len(read_values):
        raise RuntimeError(
            f"配置参数名和值数量不一致: {len(names)} != {len(read_values)}"
        )
    if reported_count != len(names):
        raise RuntimeError(
            f"配置参数数量回读不一致: reported={reported_count}, actual={len(names)}"
        )
    folded = [item.casefold() for item in names]
    if len(set(folded)) != len(folded):
        raise RuntimeError("配置参数名存在大小写不敏感重复项")

    parameters = dict(zip(names, read_values))
    categories = {
        "dimensions": {
            key: value for key, value in parameters.items() if not key.startswith("$")
        },
        "feature_states": {
            key: value for key, value in parameters.items()
            if key.upper().startswith("$STATE@")
        },
        "metadata": {
            key: value for key, value in parameters.items()
            if key.startswith("$") and not key.upper().startswith("$STATE@")
        },
    }
    has_design_table = bool(inspect_design_table(model)["exists"])
    limitations = [] if has_design_table else [
        "SOLIDWORKS 官方说明：未添加设计表时 GetParameters 输出值可能不准确",
        "尺寸、抑制状态和实体几何必须通过对应原生对象另行回读",
    ]
    return {
        "configuration": name,
        "reported_count": reported_count,
        "parameters": parameters,
        "categories": categories,
        "has_design_table": has_design_table,
        "source": "IConfiguration.GetParameters",
        "read_only": True,
        "review_required": not has_design_table,
        "limitations": limitations,
    }


def inspect_design_table(model) -> dict[str, Any]:
    """Inspect an existing native design table without opening Excel/OLE UI."""
    absent = {
        "exists": False,
        "title": "",
        "active": False,
        "total_rows": 0,
        "total_columns": 0,
        "visible_rows": 0,
        "visible_columns": 0,
        "start_row": None,
        "start_column": None,
    }
    extension_has_table = None
    try:
        extension = get_com_member(model, "Extension")
        extension_has_table = bool(get_com_member(extension, "HasDesignTable"))
    except Exception:
        pass
    if extension_has_table is False:
        return absent
    table = get_com_member(model, "GetDesignTable")
    if table is None:
        return absent
    result = {
        "exists": True,
        "title": str(get_com_member(table, "GetTitle") or ""),
        "active": bool(get_com_member(table, "IsActive")),
        "total_rows": int(get_com_member(table, "GetTotalRowCount")),
        "total_columns": int(get_com_member(table, "GetTotalColumnCount")),
        "visible_rows": int(get_com_member(table, "GetVisibleRowCount")),
        "visible_columns": int(get_com_member(table, "GetVisibleColumnCount")),
        "start_row": int(get_com_member(table, "GetStartRowNumber")),
        "start_column": int(get_com_member(table, "GetStartColumnNumber")),
    }
    if min(
        result["total_rows"], result["total_columns"],
        result["visible_rows"], result["visible_columns"],
        result["start_row"], result["start_column"],
    ) < 0:
        return absent
    return result
