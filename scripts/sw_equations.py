"""Native SolidWorks equation and global-variable helpers."""

from __future__ import annotations

import math

try:
    from .sw_connect import get_com_member
except ImportError:
    from sw_connect import get_com_member


def equation_manager(model):
    """Return the active document's native ``IEquationMgr``."""
    manager = get_com_member(model, "GetEquationMgr")
    if manager is None:
        raise RuntimeError("SolidWorks document has no equation manager")
    return manager


def equation_rows(model):
    """Read every native equation with evaluated value and state."""
    manager = equation_manager(model)
    count = int(get_com_member(manager, "GetCount"))
    disabled_count = int(get_com_member(manager, "GetDisabledEquationCount"))
    rows = []
    for index in range(count):
        value = float(get_com_member(manager, "Value", index))
        value_status = int(get_com_member(manager, "Status"))
        disabled_raw = bool(get_com_member(manager, "Disabled", index))
        rows.append({
            "index": index,
            "equation": str(get_com_member(manager, "Equation", index)),
            "value": value,
            "value_status": value_status,
            "global_variable": bool(get_com_member(manager, "GlobalVariable", index)),
            "disabled": False if disabled_count == 0 else disabled_raw,
            "configuration_option": int(get_com_member(manager, "GetConfigurationOption", index)),
        })
    return rows


def add_equation(model, equation, *, solve=True, index=-1):
    """Add one native equation in the current configuration and return its row."""
    equation = str(equation).strip()
    if not equation or "=" not in equation:
        raise ValueError("equation must be a non-empty assignment")
    manager = equation_manager(model)
    created_index = int(manager.Add2(int(index), equation, bool(solve)))
    if created_index < 0:
        raise RuntimeError(f"SolidWorks rejected equation: {equation}")
    return equation_rows(model)[created_index]


def add_global_variable(model, name, expression, *, solve=True):
    """Add a quoted SolidWorks global variable assignment."""
    name, expression = str(name).strip(), str(expression).strip()
    if not name or '"' in name or "=" in name:
        raise ValueError("global-variable name cannot be empty or contain quote/equal")
    if not expression:
        raise ValueError("global-variable expression cannot be empty")
    row = add_equation(model, f'"{name}" = {expression}', solve=solve)
    if not row["global_variable"]:
        raise RuntimeError("SolidWorks did not classify the assignment as a global variable")
    return row


def add_dimension_equation(model, dimension_full_name, expression, *, solve=True):
    """Drive one full dimension name (for example ``D1@Boss-Extrude1``)."""
    dimension_full_name = str(dimension_full_name).strip()
    expression = str(expression).strip()
    if not dimension_full_name or '"' in dimension_full_name:
        raise ValueError("dimension_full_name is invalid")
    if not expression:
        raise ValueError("dimension expression cannot be empty")
    row = add_equation(
        model, f'"{dimension_full_name}" = {expression}', solve=solve
    )
    if row["global_variable"]:
        raise RuntimeError("SolidWorks classified the dimension equation as a global variable")
    return row


def evaluate_equations(model):
    """Evaluate all equations, rebuild, and return status plus current rows."""
    manager = equation_manager(model)
    evaluate_status = int(get_com_member(manager, "EvaluateAll"))
    rebuild = bool(model.ForceRebuild3(False))
    return {
        "evaluate_return": evaluate_status,
        "evaluate_return_is_documented_ambiguous": evaluate_status == -1,
        "rebuild": rebuild,
        "equations": equation_rows(model),
    }


def global_variable_value(model, name):
    """Return the raw evaluated value in the equation manager's document units."""
    target = f'"{str(name).strip()}"'
    for row in equation_rows(model):
        left = row["equation"].split("=", 1)[0].strip()
        if row["global_variable"] and left == target:
            value = float(row["value"])
            if not math.isfinite(value):
                raise RuntimeError(f"global variable {name} evaluated to a non-finite value")
            return value
    raise KeyError(f"global variable not found: {name}")
