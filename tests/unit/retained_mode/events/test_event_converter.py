"""Tests for event_converter structure/unstructure hooks."""

from typing import Any

import pytest
from griptape.artifacts import ImageUrlArtifact, TextArtifact, UrlArtifact

from griptape_nodes.files import write_tracker
from griptape_nodes.retained_mode.events.base_events import EventRequest
from griptape_nodes.retained_mode.events.event_converter import (
    _is_json_primitive_union,
    converter,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest


class TestIsJsonPrimitiveUnion:
    """Test the _is_json_primitive_union predicate."""

    def test_matches_union_of_json_primitives(self) -> None:
        assert _is_json_primitive_union(str | int | float | bool | dict | list | None) is True

    def test_matches_partial_union(self) -> None:
        assert _is_json_primitive_union(dict | list | None) is True

    def test_matches_two_member_union(self) -> None:
        assert _is_json_primitive_union(dict | list) is True

    def test_rejects_non_union(self) -> None:
        assert _is_json_primitive_union(str) is False

    def test_rejects_union_with_non_primitive(self) -> None:
        assert _is_json_primitive_union(str | bytes) is False


class TestJsonPrimitiveUnionStructuring:
    """Test that the converter structures JSON-primitive Union types correctly."""

    @pytest.fixture
    def union_type(self) -> Any:
        return str | int | float | bool | dict | list | None

    def test_structure_str(self, union_type: type) -> None:
        assert converter.structure("hello", union_type) == "hello"

    def test_structure_int(self, union_type: type) -> None:
        value = 42
        assert converter.structure(value, union_type) == value

    def test_structure_float(self, union_type: type) -> None:
        value = 3.14
        assert converter.structure(value, union_type) == value

    def test_structure_bool(self, union_type: type) -> None:
        assert converter.structure(True, union_type) is True

    def test_structure_none(self, union_type: type) -> None:
        assert converter.structure(None, union_type) is None

    def test_structure_list(self, union_type: type) -> None:
        assert converter.structure([1, 2, 3], union_type) == [1, 2, 3]

    def test_structure_dict(self, union_type: type) -> None:
        assert converter.structure({"key": "value"}, union_type) == {"key": "value"}

    def test_structure_nested_dict(self, union_type: type) -> None:
        value = {"outer": {"inner": [1, 2, 3]}}
        assert converter.structure(value, union_type) == value


class TestSetParameterValueRequestStructuring:
    """Test that SetParameterValueRequest structures correctly with complex values."""

    def test_structure_with_dict_value(self) -> None:
        data = {
            "node_name": "Load Image",
            "parameter_name": "image",
            "value": {"url": "http://example.com/image.jpg", "width": 100},
        }
        result = converter.structure(data, SetParameterValueRequest)

        assert result.node_name == "Load Image"
        assert result.parameter_name == "image"
        assert result.value == {"url": "http://example.com/image.jpg", "width": 100}

    def test_structure_with_list_value(self) -> None:
        data = {
            "node_name": "MyNode",
            "parameter_name": "items",
            "value": [1, 2, 3],
        }
        result = converter.structure(data, SetParameterValueRequest)

        assert result.value == [1, 2, 3]

    def test_structure_with_string_value(self) -> None:
        data = {
            "node_name": "MyNode",
            "parameter_name": "name",
            "value": "hello",
        }
        result = converter.structure(data, SetParameterValueRequest)

        assert result.value == "hello"

    def test_structure_with_none_value(self) -> None:
        data = {
            "node_name": "MyNode",
            "parameter_name": "name",
            "value": None,
        }
        result = converter.structure(data, SetParameterValueRequest)

        assert result.value is None

    def test_from_dict_with_image_artifact_value(self) -> None:
        """Reproduce the exact payload that triggered the original bug."""
        data = {
            "event_type": "EventRequest",
            "request_type": "SetParameterValueRequest",
            "request_id": "bd1743f3-7508-429f-bad1-55cd47e9e181",
            "response_topic": "sessions/abc123/response",
            "request": {
                "node_name": "Load Image",
                "parameter_name": "image",
                "value": {
                    "value": "http://localhost:8124/workspace/inputs/IMG_0798.jpeg",
                    "width": 3024,
                    "height": 4032,
                    "name": "IMG_0798.jpeg",
                    "type": "ImageUrlArtifact",
                    "meta": {
                        "created_at": "2026-04-14T20:12:28.745Z",
                        "content_hash": "",
                        "size_bytes": 7996029,
                        "format": "JPEG",
                    },
                },
            },
        }
        event = EventRequest.from_dict(data)

        assert isinstance(event.request, SetParameterValueRequest)
        assert event.request.node_name == "Load Image"
        assert event.request.parameter_name == "image"
        assert isinstance(event.request.value, dict)
        assert event.request.value["type"] == "ImageUrlArtifact"
        expected_width = 3024
        assert event.request.value["width"] == expected_width


class TestUrlArtifactMetaStamping:
    """Tests for the cattrs UrlArtifact ``meta.created_at`` stamping pipeline.

    The engine records each write's mtime into ``write_tracker``; the cattrs
    unstructure hook reads it to refresh the frontend preview cache when a
    node overwrites a file at the same path (issue #4663).
    """

    @pytest.fixture(autouse=True)
    def _clear_tracker(self) -> None:
        write_tracker.clear()

    def test_local_path_with_recorded_write_gets_stamp(self) -> None:
        write_tracker.record("/var/data/foo.png", 1700000000123456789)
        out = converter.unstructure(ImageUrlArtifact("/var/data/foo.png"))
        assert (out.get("meta") or {}).get("created_at")

    def test_unwritten_path_not_stamped(self) -> None:
        out = converter.unstructure(ImageUrlArtifact("/var/data/never-written.png"))
        assert not (out.get("meta") or {}).get("created_at")

    def test_remote_url_not_stamped(self) -> None:
        # Remote URLs are never recorded, so even if a tracker entry exists for
        # something else, a remote artifact must not receive a stamp.
        write_tracker.record("/var/data/foo.png", 1700000000000000000)
        out = converter.unstructure(ImageUrlArtifact("https://example.com/x.png"))
        assert not (out.get("meta") or {}).get("created_at")

    def test_existing_created_at_preserved(self) -> None:
        write_tracker.record("/var/data/foo.png", 1700000000000000000)
        existing = "2020-01-01T00:00:00+00:00"
        out = converter.unstructure(ImageUrlArtifact("/var/data/foo.png", meta={"created_at": existing}))
        assert out["meta"]["created_at"] == existing

    def test_text_artifact_unaffected(self) -> None:
        write_tracker.record("hello", 1700000000000000000)
        out = converter.unstructure(TextArtifact("hello"))
        assert not (out.get("meta") or {}).get("created_at")

    def test_url_artifact_subclass_stamped(self) -> None:
        # Surrogate for ThreeDUrlArtifact / GLTFUrlArtifact / SplatUrlArtifact:
        # any UrlArtifact subclass must participate.
        class _LocalUrl(UrlArtifact):
            pass

        write_tracker.record("/var/data/model.glb", 1700000000000000000)
        out = converter.unstructure(_LocalUrl("/var/data/model.glb"))
        assert (out.get("meta") or {}).get("created_at")

    def test_overwrite_produces_distinct_token(self) -> None:
        write_tracker.record("/var/data/foo.png", 1700000000000000000)
        first = converter.unstructure(ImageUrlArtifact("/var/data/foo.png"))
        write_tracker.record("/var/data/foo.png", 1700000000999999999)
        second = converter.unstructure(ImageUrlArtifact("/var/data/foo.png"))
        assert first["meta"]["created_at"] != second["meta"]["created_at"]
