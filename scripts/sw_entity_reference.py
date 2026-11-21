"""SolidWorks 语义实体引用。

把特征名、实体类型和几何签名组合成可审计引用，逐步减少对 Face1/Edge1
和屏幕坐标的依赖。模块不猜测 COM API；调用方负责提供候选实体的元数据。
"""
from __future__ import annotations

import hashlib
import json
import numbers
import base64
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

import pythoncom
from win32com.client import VARIANT


@dataclass(frozen=True)
class SemanticEntityReference:
    """@brief 可序列化的语义实体引用。"""

    entity_type: str
    feature_name: str | None = None
    geometry_signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """@brief 转为任务证据 JSON。"""
        return asdict(self)


@dataclass(frozen=True)
class PersistentEntityReference:
    """Serializable SolidWorks persistent-reference byte payload."""

    data_base64: str
    byte_count: int

    def to_bytes(self) -> bytes:
        data = base64.b64decode(self.data_base64.encode("ascii"), validate=True)
        if len(data) != self.byte_count:
            raise ValueError("persistent-reference byte count mismatch")
        return data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_persistent_reference(model: Any, entity: Any) -> PersistentEntityReference:
    """Capture a native ``GetPersistReference3`` payload for one entity."""
    if entity is None:
        raise ValueError("entity cannot be None")
    raw = model.Extension.GetPersistReference3(entity)
    data = bytes(raw or ())
    if not data:
        raise RuntimeError("SolidWorks returned an empty persistent reference")
    return PersistentEntityReference(
        data_base64=base64.b64encode(data).decode("ascii"),
        byte_count=len(data),
    )


def resolve_persistent_reference(model: Any, reference: PersistentEntityReference | Mapping[str, Any]):
    """Resolve a native persistent reference and return object plus error code."""
    if not isinstance(reference, PersistentEntityReference):
        reference = PersistentEntityReference(
            data_base64=str(reference["data_base64"]),
            byte_count=int(reference["byte_count"]),
        )
    payload = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1, tuple(reference.to_bytes()))
    error = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    result = model.Extension.GetObjectByPersistReference3(payload, error)
    if isinstance(result, tuple) and len(result) == 2:
        entity, returned_error = result
        error_code = int(returned_error)
    else:
        entity, error_code = result, int(error.value)
    if entity is None:
        raise RuntimeError(f"persistent reference did not resolve (error={error_code})")
    return {"entity": entity, "error_code": error_code}


def geometry_signature(values: Any, precision: int = 6) -> str:
    """@brief 对几何摘要做稳定哈希，避免把屏幕坐标写入任务。"""

    def normalize(value: Any) -> Any:
        if isinstance(value, numbers.Real) and not isinstance(value, bool):
            return round(float(value), precision)
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): normalize(value[key]) for key in sorted(value, key=str)}
        return value

    canonical = json.dumps(normalize(values), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def reference_from_metadata(entity_type: str, feature_name: str | None = None, geometry: Any = None) -> SemanticEntityReference:
    """@brief 从特征名、类型和几何摘要创建引用。"""
    return SemanticEntityReference(
        entity_type=str(entity_type),
        feature_name=str(feature_name) if feature_name else None,
        geometry_signature=geometry_signature(geometry) if geometry is not None else None,
    )


def resolve_semantic_reference(
    reference: SemanticEntityReference,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """@brief 按类型、特征名和几何签名解析候选实体。"""
    scored: list[tuple[int, Mapping[str, Any]]] = []
    for candidate in candidates:
        score = 0
        if str(candidate.get("entity_type", candidate.get("type", ""))) == reference.entity_type:
            score += 4
        if reference.feature_name and candidate.get("feature_name", candidate.get("name")) == reference.feature_name:
            score += 3
        if reference.geometry_signature and candidate.get("geometry_signature") == reference.geometry_signature:
            score += 5
        if score:
            scored.append((score, candidate))
    if not scored:
        return {"status": "not_found", "reference": reference.to_dict(), "candidates": []}
    best_score = max(score for score, _ in scored)
    best = [candidate for score, candidate in scored if score == best_score]
    if len(best) != 1:
        return {"status": "ambiguous", "score": best_score, "reference": reference.to_dict(), "candidates": [dict(item) for item in best]}
    return {"status": "resolved", "score": best_score, "reference": reference.to_dict(), "entity": dict(best[0])}
