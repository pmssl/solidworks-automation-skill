"""Validate extrusion inputs before the wrapper changes SolidWorks selection."""

import pytest

from scripts.sw_part import ExtrudeEnd, extrude_feature


@pytest.mark.parametrize(
    "condition, params",
    [
        ("unknown", {}),
        ("blind", {}),
        ("blind", {"distance": float("nan")}),
        ("up_to_next", {"reference": object()}),
        ("up_to_surface", {}),
        ("offset_from_surface", {"reference": object()}),
        ("offset_from_surface", {"distance": 0.003}),
        ("through_all", {"reverse_offset": True}),
    ],
)
def test_rejects_invalid_extrusion_end(condition, params):
    with pytest.raises(ValueError):
        ExtrudeEnd(condition, **params)


def test_midplane_cannot_be_combined_with_a_second_direction():
    with pytest.raises(ValueError, match="midplane"):
        extrude_feature(
            None, "Profile", ExtrudeEnd("blind", 0.005),
            direction2=ExtrudeEnd("midplane", 0.01),
        )


def test_through_all_requires_a_cut():
    with pytest.raises(ValueError, match="cut=True"):
        extrude_feature(None, "Profile", ExtrudeEnd("through_all"))
