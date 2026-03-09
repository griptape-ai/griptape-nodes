"""Tests for the list_config Parameter feature.

list_config allows a single typed Parameter to accept either a scalar value or a list,
with configurable cardinality constraints (min_items, max_items) and three modes:
  - "single": scalar only (default behavior, no change)
  - "list":   list[T] only
  - "any":    accepts both scalar T and list[T]; single-item lists are auto-normalized
              to their scalar element at value-set time
"""

import pytest
from griptape.artifacts import ImageUrlArtifact, VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo

from .mocks import MockNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node_with_param(param: Parameter, node_name: str = "node") -> MockNode:
    """Return a MockNode with the given parameter already added."""
    node = MockNode(name=node_name)
    node.add_parameter(param)
    return node


# ---------------------------------------------------------------------------
# Base Parameter — input_types augmentation
# ---------------------------------------------------------------------------


class TestParameterListConfigInputTypes:
    """input_types property reflects list_config.mode correctly."""

    def test_no_list_config_unchanged(self) -> None:
        param = Parameter(name="x", input_types=["str"], type="str", output_type="str", tooltip="t")
        assert param.input_types == ["str"]

    def test_mode_single_unchanged(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "single"},
        )
        assert param.input_types == ["str"]

    def test_mode_any_appends_list_variant(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any"},
        )
        assert param.input_types == ["str", "list[str]"]

    def test_mode_list_replaces_with_list_variant(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "list"},
        )
        assert param.input_types == ["list[str]"]

    def test_mode_any_no_duplicate_list_variant(self) -> None:
        """If list[T] is already in input_types it should not be duplicated."""
        param = Parameter(
            name="x",
            input_types=["str", "list[str]"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any"},
        )
        assert param.input_types.count("list[str]") == 1


# ---------------------------------------------------------------------------
# Base Parameter — serialization
# ---------------------------------------------------------------------------


class TestParameterListConfigSerialization:
    """list_config is present in to_dict output so the frontend receives it."""

    def test_to_dict_contains_list_config(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any", "max_items": 5},
        )
        ui_options = param.to_dict()["ui_options"]
        assert ui_options["list_config"] == {"mode": "any", "max_items": 5}

    def test_to_dict_no_list_config_key_when_not_set(self) -> None:
        param = Parameter(name="x", input_types=["str"], type="str", output_type="str", tooltip="t")
        ui_options = param.to_dict()["ui_options"]
        assert "list_config" not in ui_options


# ---------------------------------------------------------------------------
# Base Parameter — auto-normalize converter (mode="any")
# ---------------------------------------------------------------------------


class TestParameterListConfigAutoNormalize:
    """Single-item lists are unwrapped to scalars; multi-item lists are kept; scalars are unchanged."""

    def test_single_item_list_normalized_to_scalar(self) -> None:
        param = Parameter(
            name="x", input_types=["str"], type="str", output_type="str", tooltip="t", list_config={"mode": "any"}
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", ["hello"])
        assert node.get_parameter_value("x") == "hello"

    def test_multi_item_list_stays_list(self) -> None:
        param = Parameter(
            name="x", input_types=["str"], type="str", output_type="str", tooltip="t", list_config={"mode": "any"}
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", ["a", "b"])
        result = node.get_parameter_value("x")
        assert result == ["a", "b"]

    def test_scalar_value_unchanged(self) -> None:
        param = Parameter(
            name="x", input_types=["str"], type="str", output_type="str", tooltip="t", list_config={"mode": "any"}
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", "hello")
        assert node.get_parameter_value("x") == "hello"

    def test_mode_list_no_auto_normalize(self) -> None:
        """mode='list' does not unwrap single-item lists."""
        param = Parameter(
            name="x", input_types=["str"], type="str", output_type="str", tooltip="t", list_config={"mode": "list"}
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", ["hello"])
        result = node.get_parameter_value("x")
        assert result == ["hello"]


# ---------------------------------------------------------------------------
# Base Parameter — cardinality validators
# ---------------------------------------------------------------------------


class TestParameterListConfigValidators:
    """max_items and min_items are enforced via set_parameter_value."""

    def test_max_items_exceeded_raises(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any", "max_items": 2},
        )
        node = _make_node_with_param(param)
        with pytest.raises(ValueError, match="at most 2 items"):
            node.set_parameter_value("x", ["a", "b", "c"])

    def test_max_items_at_limit_accepted(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any", "max_items": 2},
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", ["a", "b"])
        assert node.get_parameter_value("x") == ["a", "b"]

    def test_min_items_not_met_raises(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "list", "min_items": 2},
        )
        node = _make_node_with_param(param)
        with pytest.raises(ValueError, match="at least 2 items"):
            node.set_parameter_value("x", ["a"])

    def test_min_items_met_accepted(self) -> None:
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "list", "min_items": 2},
        )
        node = _make_node_with_param(param)
        node.set_parameter_value("x", ["a", "b"])
        assert node.get_parameter_value("x") == ["a", "b"]

    def test_scalar_bypasses_max_items_validator(self) -> None:
        """Cardinality validators only apply to list values."""
        param = Parameter(
            name="x",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="t",
            list_config={"mode": "any", "max_items": 1},
        )
        node = _make_node_with_param(param)
        # A bare scalar should not trigger max_items
        node.set_parameter_value("x", "hello")
        assert node.get_parameter_value("x") == "hello"


# ---------------------------------------------------------------------------
# ParameterImage — list_config integration
# ---------------------------------------------------------------------------


class TestParameterImageListConfig:
    """ParameterImage correctly exposes and passes through list_config."""

    def test_no_list_config_input_types_unchanged(self) -> None:
        p = ParameterImage(name="img")
        assert p.input_types == ["any"]

    def test_mode_any_accept_any_true_includes_list_any(self) -> None:
        p = ParameterImage(name="img", list_config={"mode": "any"})
        assert "list[any]" in p.input_types

    def test_mode_any_accept_any_false_correct_types(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "any"})
        assert p.input_types == ["ImageUrlArtifact", "list[ImageUrlArtifact]"]

    def test_mode_list_accept_any_false_correct_types(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "list"})
        assert p.input_types == ["list[ImageUrlArtifact]"]

    def test_to_dict_carries_list_config(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "list"})
        assert p.to_dict()["ui_options"]["list_config"]["mode"] == "list"

    def test_auto_normalize_single_item_list(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "any"})
        node = _make_node_with_param(p)
        img = ImageUrlArtifact("http://example.com/a.jpg")
        node.set_parameter_value("img", [img])
        assert not isinstance(node.get_parameter_value("img"), list)

    def test_auto_normalize_multi_item_list_stays_list(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "any"})
        node = _make_node_with_param(p)
        img1 = ImageUrlArtifact("http://example.com/a.jpg")
        img2 = ImageUrlArtifact("http://example.com/b.jpg")
        node.set_parameter_value("img", [img1, img2])
        result = node.get_parameter_value("img")
        assert result == [img1, img2]

    def test_max_items_enforced(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "any", "max_items": 2})
        node = _make_node_with_param(p)
        img = ImageUrlArtifact("http://example.com/a.jpg")
        with pytest.raises(ValueError, match="at most 2 items"):
            node.set_parameter_value("img", [img, img, img])

    def test_scalar_value_unchanged(self) -> None:
        p = ParameterImage(name="img", accept_any=False, list_config={"mode": "any"})
        node = _make_node_with_param(p)
        img = ImageUrlArtifact("http://example.com/a.jpg")
        node.set_parameter_value("img", img)
        assert node.get_parameter_value("img") is img


# ---------------------------------------------------------------------------
# ParameterVideo — list_config integration
# ---------------------------------------------------------------------------


class TestParameterVideoListConfig:
    """ParameterVideo correctly exposes and passes through list_config."""

    def test_no_list_config_input_types_unchanged(self) -> None:
        p = ParameterVideo(name="vid")
        assert p.input_types == ["any"]

    def test_mode_any_accept_any_false_correct_types(self) -> None:
        p = ParameterVideo(name="vid", accept_any=False, list_config={"mode": "any"})
        assert p.input_types == ["VideoUrlArtifact", "list[VideoUrlArtifact]"]

    def test_mode_list_accept_any_false_correct_types(self) -> None:
        p = ParameterVideo(name="vid", accept_any=False, list_config={"mode": "list"})
        assert p.input_types == ["list[VideoUrlArtifact]"]

    def test_auto_normalize_single_item_list(self) -> None:
        p = ParameterVideo(name="vid", accept_any=False, list_config={"mode": "any"})
        node = _make_node_with_param(p)
        vid = VideoUrlArtifact("http://example.com/a.mp4")
        node.set_parameter_value("vid", [vid])
        assert not isinstance(node.get_parameter_value("vid"), list)
