"""Tests for a compact DescribeNodeTypeRequest: parameter specs, metadata-only fallbacks, and the spec cache."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeDeprecationMetadata,
    NodeMetadata,
)
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.library_events import (
    DescribeNodeTypeRequest,
    DescribeNodeTypeResultFailure,
    DescribeNodeTypeResultSuccess,
    NodeTypeParameterSpec,
    RegisterSandboxNodeFromSourceRequest,
    RegisterSandboxNodeFromSourceResultSuccess,
    ReloadAllLibrariesRequest,
    UnloadLibraryFromRegistryRequest,
    UnloadLibraryFromRegistryResultSuccess,
)
from griptape_nodes.retained_mode.managers.library.node_type_specs import NOTE_ELLIPSIS, NOTE_MAX_CHARS
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.traits.multi_options import MultiOptions
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from griptape_nodes.retained_mode.engine import Engine

LIBRARY_NAME = "describe-node-type-compact-test-library"
OTHER_LIBRARY_NAME = "describe-node-type-compact-other-library"
LONG_TOOLTIP = "The prompt sent to the model. " * 20


class _CompactProbe(BaseNode):
    """A node type with one parameter of each kind a compact spec distinguishes."""

    constructed: ClassVar[int] = 0

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name=name, metadata=metadata)
        type(self).constructed += 1

        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                input_types=["str"],
                output_type="str",
                default_value="hello",
                tooltip=LONG_TOOLTIP,
                ui_options={"display_name": "Prompt", "multiline": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="style",
                type="str",
                default_value="photo",
                tooltip="Picture style",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=["photo", "sketch", "anime"])},
            )
        )
        self.add_parameter(
            Parameter(
                name="tags",
                type="list",
                default_value=[],
                tooltip="Tags to apply",
                allowed_modes={ParameterMode.PROPERTY},
                traits={MultiOptions(choices=["red", "blue"])},
            )
        )
        self.add_parameter(
            Parameter(
                name="legacy_mode",
                type="str",
                default_value="fast",
                tooltip="Speed preset",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"simple_dropdown": ["fast", "slow"]},
            )
        )
        self.add_parameter(
            ParameterList(
                name="images",
                input_types=["ImageArtifact"],
                type="ImageArtifact",
                tooltip="Images to combine",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="image",
                type="ImageArtifact",
                input_types=["ImageArtifact"],
                tooltip="  Deprecated. Use images.",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                output_type="str",
                tooltip="Result",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )


class _RaisingProbe(BaseNode):
    """Stand-in for node types whose __init__ performs failing I/O (auth, network, disk)."""

    constructed: ClassVar[int] = 0

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name=name, metadata=metadata)
        type(self).constructed += 1
        msg = "simulated I/O failure"
        raise RuntimeError(msg)


class _ReplacementProbe(BaseNode):
    """The code a reload or re-registration puts under the name `_CompactProbe` was registered as."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name=name, metadata=metadata)
        self.add_parameter(Parameter(name="replacement_only", type="int", default_value=1, tooltip="New parameter"))


def _schema(name: str) -> LibrarySchema:
    return LibrarySchema(
        name=name,
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=LibraryMetadata(
            author="test",
            description="describe node type compact test library",
            library_version="1.0.0",
            engine_version="1.0.0",
            tags=[],
        ),
        categories=[],
        nodes=[],
    )


def _metadata(*, deprecated: bool = False) -> NodeMetadata:
    deprecation = None
    if deprecated:
        deprecation = NodeDeprecationMetadata(deprecation_message="Use another node.")
    return NodeMetadata(
        category="test/category",
        description="Probe node used by compact DescribeNodeType tests",
        display_name="Probe",
        deprecation=deprecation,
    )


def _register_library(
    name: str = LIBRARY_NAME,
    node_class: type[BaseNode] = _CompactProbe,
    *,
    node_type_name: str | None = None,
    deprecated: bool = False,
) -> None:
    library = LibraryRegistry.generate_new_library(library_data=_schema(name))
    if node_type_name is None:
        library.register_new_node_type(node_class, _metadata(deprecated=deprecated))
        return
    library.register_lazy_node_type(node_type_name, _metadata(deprecated=deprecated), loader=lambda: node_class)


def _describe_result(
    engine: Engine, node_type: str, library: str | None = None
) -> DescribeNodeTypeResultSuccess | DescribeNodeTypeResultFailure:
    result = engine.library_manager.catalog.describe_node_type_request(
        DescribeNodeTypeRequest(node_type=node_type, library=library, compact=True)
    )
    assert isinstance(result, (DescribeNodeTypeResultSuccess, DescribeNodeTypeResultFailure))
    return result


def _describe(engine: Engine, node_type: str, library: str | None = None) -> DescribeNodeTypeResultSuccess:
    result = _describe_result(engine, node_type, library)
    assert isinstance(result, DescribeNodeTypeResultSuccess), result.result_details
    return result


def _specs(result: DescribeNodeTypeResultSuccess) -> list[NodeTypeParameterSpec]:
    assert result.parameters == []
    assert result.parameter_specs is not None
    return result.parameter_specs


def _specs_by_name(result: DescribeNodeTypeResultSuccess) -> dict[str, NodeTypeParameterSpec]:
    return {param.name: param for param in _specs(result)}


def _parameter_names(result: DescribeNodeTypeResultSuccess) -> list[str]:
    return [param.name for param in _specs(result)]


def _warnings(result: DescribeNodeTypeResultSuccess | DescribeNodeTypeResultFailure) -> list[str]:
    assert isinstance(result.result_details, ResultDetails)
    return [detail.message for detail in result.result_details.result_details if detail.level == logging.WARNING]


@pytest.fixture(autouse=True)
def _clean_registry_and_counters() -> Generator[None, None, None]:
    """LibraryRegistry is process-global, so each test starts and ends with it empty."""
    LibraryRegistry._clear()
    _CompactProbe.constructed = 0
    _RaisingProbe.constructed = 0
    yield
    LibraryRegistry._clear()


class TestDescribeNodeTypeCompactSpec:
    """A compact request returns the fields a client plans with."""

    def test_node_level_fields(self, engine: Engine) -> None:
        _register_library(deprecated=True)

        result = _describe(engine, _CompactProbe.__name__)

        assert result.node_type == _CompactProbe.__name__
        assert result.library == LIBRARY_NAME
        assert result.metadata.description == "Probe node used by compact DescribeNodeType tests"
        assert result.metadata.category == "test/category"
        assert result.metadata.deprecation is not None
        assert _parameter_names(result) == ["prompt", "style", "tags", "legacy_mode", "images", "image", "output"]
        assert result.result_details == ResultDetails(
            message=f"Successfully described node type '{_CompactProbe.__name__}' in Library '{LIBRARY_NAME}'.",
            level=logging.DEBUG,
        )

    def test_parameter_fields(self, engine: Engine) -> None:
        _register_library()

        by_name = _specs_by_name(_describe(engine, _CompactProbe.__name__))

        prompt = by_name["prompt"]
        assert prompt.type == "str"
        assert prompt.input_types == ["str"]
        assert prompt.output_type == "str"
        assert prompt.modes == ["input", "property", "output"]
        assert prompt.default == "hello"
        assert prompt.options is None
        assert prompt.multi_input is False
        assert prompt.deprecated is False

        output = by_name["output"]
        assert output.modes == ["output"]
        assert output.default is None

    def test_options_come_from_dropdown_and_multi_select_choices(self, engine: Engine) -> None:
        _register_library()

        by_name = _specs_by_name(_describe(engine, _CompactProbe.__name__))

        assert by_name["style"].options == ["photo", "sketch", "anime"]
        assert by_name["style"].modes == ["property"]
        assert by_name["tags"].options == ["red", "blue"]
        # Written straight into ui_options, with no Options trait attached.
        assert by_name["legacy_mode"].options == ["fast", "slow"]

    def test_parameter_list_is_multi_input(self, engine: Engine) -> None:
        _register_library()

        by_name = _specs_by_name(_describe(engine, _CompactProbe.__name__))

        assert by_name["images"].multi_input is True
        assert by_name["images"].modes == ["input"]
        assert by_name["image"].multi_input is False

    def test_tooltip_starting_with_deprecated_marks_the_parameter(self, engine: Engine) -> None:
        _register_library()

        by_name = _specs_by_name(_describe(engine, _CompactProbe.__name__))

        assert by_name["image"].deprecated is True
        assert by_name["image"].note == "Deprecated. Use images."
        assert [name for name, param in by_name.items() if param.deprecated] == ["image"]

    def test_note_is_the_tooltip_cut_at_a_word(self, engine: Engine) -> None:
        _register_library()

        by_name = _specs_by_name(_describe(engine, _CompactProbe.__name__))

        note = by_name["prompt"].note
        assert note is not None
        assert len(note) <= NOTE_MAX_CHARS
        assert note.endswith(NOTE_ELLIPSIS)
        assert note.startswith("The prompt sent to the model. The prompt sent")
        # Cut between words, not inside one.
        assert note.removesuffix(NOTE_ELLIPSIS).split(" ")[-1] in {"The", "prompt", "sent", "to", "the", "model"}
        assert by_name["style"].note == "Picture style"

    def test_leaves_out_tooltips_and_ui_options(self, engine: Engine) -> None:
        _register_library()

        for param in _specs(_describe(engine, _CompactProbe.__name__)):
            assert not hasattr(param, "tooltip")
            assert not hasattr(param, "ui_options")

    def test_full_request_is_unchanged(self, engine: Engine) -> None:
        """Without `compact`, the request returns full descriptions and no parameter specs."""
        _register_library()

        result = engine.library_manager.catalog.describe_node_type_request(
            DescribeNodeTypeRequest(node_type=_CompactProbe.__name__, library=LIBRARY_NAME)
        )

        assert isinstance(result, DescribeNodeTypeResultSuccess)
        assert result.parameter_specs is None
        by_name = {param.name: param for param in result.parameters}
        assert by_name["prompt"].tooltip == LONG_TOOLTIP
        assert by_name["prompt"].ui_options == {"display_name": "Prompt", "multiline": True}
        assert result.result_details == ResultDetails(
            message=f"Successfully described node type '{_CompactProbe.__name__}' in Library '{LIBRARY_NAME}'.",
            level=logging.DEBUG,
        )

    def test_full_request_probes_every_time(self, engine: Engine) -> None:
        """Only compact requests are cached, so a full request re-reads machine-dependent choices."""
        _register_library()
        _describe(engine, _CompactProbe.__name__)

        for _ in range(2):
            engine.library_manager.catalog.describe_node_type_request(
                DescribeNodeTypeRequest(node_type=_CompactProbe.__name__)
            )

        assert _CompactProbe.constructed == 3  # noqa: PLR2004


class TestDescribeNodeTypeCompactFailures:
    """A compact request fails, or falls back to library metadata, as a full request does."""

    def test_unknown_node_type_fails(self, engine: Engine) -> None:
        _register_library()

        result = _describe_result(engine, "NotARealNode")

        assert isinstance(result, DescribeNodeTypeResultFailure)
        assert result.result_details == ResultDetails(
            message=(
                "Attempted to describe node type 'NotARealNode'. Failed when looking up its library because: "
                "No node type 'NotARealNode' could be found in any of the libraries registered."
            ),
            level=logging.ERROR,
        )

    def test_raising_node_type_keeps_its_metadata_as_a_full_request_does(self, engine: Engine) -> None:
        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))
        library.register_new_node_type(_RaisingProbe, _metadata())

        compact = _describe(engine, _RaisingProbe.__name__)
        full = engine.library_manager.catalog.describe_node_type_request(
            DescribeNodeTypeRequest(node_type=_RaisingProbe.__name__)
        )

        assert isinstance(full, DescribeNodeTypeResultSuccess)
        assert compact.library == LIBRARY_NAME
        assert compact.metadata == full.metadata
        assert compact.metadata.category == "test/category"
        assert compact.parameter_specs == []
        assert full.parameter_specs is None
        assert compact.parameters == full.parameters == []
        assert _warnings(compact) == _warnings(full)
        assert _warnings(compact) == ["Parameter probe failed because: RuntimeError: simulated I/O failure"]

    def test_module_that_fails_to_import_keeps_its_metadata(self, engine: Engine) -> None:
        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))

        def broken_loader() -> type[BaseNode]:
            msg = "No module named 'missing_dependency'"
            raise ImportError(msg)

        library.register_lazy_node_type("BrokenNode", _metadata(), loader=broken_loader)

        result = _describe(engine, "BrokenNode", library=LIBRARY_NAME)

        assert result.parameter_specs == []
        assert result.metadata.category == "test/category"
        assert _warnings(result) == ["Node module failed to import: ImportError: No module named 'missing_dependency'"]

    def test_default_that_cannot_be_copied_keeps_its_metadata(self, engine: Engine) -> None:
        class _UncopyableDefaultProbe(BaseNode):
            constructed: ClassVar[int] = 0

            def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
                super().__init__(name=name, metadata=metadata)
                type(self).constructed += 1
                self.add_parameter(
                    Parameter(name="client", type="any", default_value=threading.Lock(), tooltip="Shared client")
                )

        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))
        library.register_new_node_type(_UncopyableDefaultProbe, _metadata())

        for _ in range(2):
            result = _describe(engine, _UncopyableDefaultProbe.__name__)
            assert result.parameter_specs == []
            [warning] = _warnings(result)
            assert warning.startswith("Parameter read failed because: TypeError: ")

        # Not cached, so a later request tries again.
        assert _UncopyableDefaultProbe.constructed == 2  # noqa: PLR2004

    def test_node_type_in_two_libraries_needs_the_library_named(self, engine: Engine) -> None:
        _register_library(LIBRARY_NAME)
        _register_library(OTHER_LIBRARY_NAME, _ReplacementProbe, node_type_name=_CompactProbe.__name__)

        ambiguous = _describe_result(engine, _CompactProbe.__name__)
        assert isinstance(ambiguous, DescribeNodeTypeResultFailure)
        assert "In order to disambiguate, specify the library" in str(ambiguous.result_details)

        named = _describe(engine, _CompactProbe.__name__, library=OTHER_LIBRARY_NAME)
        assert named.library == OTHER_LIBRARY_NAME
        assert _parameter_names(named) == ["replacement_only"]


class TestDescribeNodeTypeCompactCache:
    """Compact specs are built once per node type and dropped whenever registrations change."""

    def test_second_call_does_not_create_the_node_again(self, engine: Engine) -> None:
        _register_library()

        first = _describe(engine, _CompactProbe.__name__)
        second = _describe(engine, _CompactProbe.__name__)

        assert _CompactProbe.constructed == 1
        assert _specs(second) == _specs(first)

    def test_caller_changing_a_spec_does_not_change_later_results(self, engine: Engine) -> None:
        _register_library()

        first = _specs(_describe(engine, _CompactProbe.__name__))
        first[0].default = "changed by caller"
        first.clear()

        second = _specs(_describe(engine, _CompactProbe.__name__))

        assert second[0].default == "hello"
        assert _CompactProbe.constructed == 1

    def test_failures_are_not_cached(self, engine: Engine) -> None:
        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))
        library.register_new_node_type(_RaisingProbe, _metadata())

        _describe(engine, _RaisingProbe.__name__)
        _describe(engine, _RaisingProbe.__name__)

        assert _RaisingProbe.constructed == 2  # noqa: PLR2004

    def test_node_type_that_stops_raising_is_described_in_full(self, engine: Engine) -> None:
        """A node needing credentials at construction gets its parameters once they are set."""

        class _NeedsKeyProbe(BaseNode):
            api_key: ClassVar[str | None] = None

            def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
                super().__init__(name=name, metadata=metadata)
                if type(self).api_key is None:
                    msg = "Missing credentials"
                    raise RuntimeError(msg)
                self.add_parameter(Parameter(name="prompt", type="str", default_value="", tooltip="Prompt"))

        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))
        library.register_new_node_type(_NeedsKeyProbe, _metadata())

        without_key = _describe(engine, _NeedsKeyProbe.__name__)
        _NeedsKeyProbe.api_key = "set"
        with_key = _describe(engine, _NeedsKeyProbe.__name__)

        assert _warnings(without_key) == ["Parameter probe failed because: RuntimeError: Missing credentials"]
        assert _warnings(with_key) == []
        assert _parameter_names(with_key) == ["prompt"]

    def test_unload_drops_the_cached_spec(self, engine: Engine) -> None:
        _register_library()
        _describe(engine, _CompactProbe.__name__)

        unload = engine.library_manager.registration.unload_library_from_registry_request(
            UnloadLibraryFromRegistryRequest(library_name=LIBRARY_NAME)
        )
        assert isinstance(unload, UnloadLibraryFromRegistryResultSuccess), unload.result_details

        after_unload = _describe_result(engine, _CompactProbe.__name__, library=LIBRARY_NAME)
        assert isinstance(after_unload, DescribeNodeTypeResultFailure)

        # Registered again under the same names with different code: the new code is described.
        _register_library(LIBRARY_NAME, _ReplacementProbe, node_type_name=_CompactProbe.__name__)
        reloaded = _describe(engine, _CompactProbe.__name__, library=LIBRARY_NAME)
        assert _parameter_names(reloaded) == ["replacement_only"]

    @pytest.mark.asyncio
    async def test_reload_all_libraries_drops_the_cached_spec(self, engine: Engine) -> None:
        library_manager = engine.library_manager
        _register_library()
        assert "prompt" in _parameter_names(_describe(engine, _CompactProbe.__name__))

        async def reregister_with_new_code(*_args: object, **_kwargs: object) -> list[str]:
            _register_library(LIBRARY_NAME, _ReplacementProbe, node_type_name=_CompactProbe.__name__)
            return []

        with (
            patch.object(library_manager, "load_all_libraries_from_config", side_effect=reregister_with_new_code),
            patch.object(library_manager.workers, "maybe_start_workers_for_existing_session", AsyncMock()),
        ):
            await library_manager._run_reload_libraries(ReloadAllLibrariesRequest())

        assert _parameter_names(_describe(engine, _CompactProbe.__name__)) == ["replacement_only"]

    def test_replacing_one_node_type_drops_the_cached_spec(self, engine: Engine) -> None:
        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))
        library.register_new_node_type(_CompactProbe, _metadata())
        _describe(engine, _CompactProbe.__name__)

        library.unregister_node_type(_CompactProbe.__name__)
        library.register_lazy_node_type(_CompactProbe.__name__, _metadata(), loader=lambda: _ReplacementProbe)

        assert _parameter_names(_describe(engine, _CompactProbe.__name__)) == ["replacement_only"]

    def test_registering_another_library_drops_the_cached_spec(self, engine: Engine) -> None:
        """A new library can make a node type ambiguous, so its unqualified lookup has to be redone."""
        _register_library()
        _describe(engine, _CompactProbe.__name__)

        _register_library(OTHER_LIBRARY_NAME, _ReplacementProbe, node_type_name=_CompactProbe.__name__)

        assert isinstance(_describe_result(engine, _CompactProbe.__name__), DescribeNodeTypeResultFailure)
        assert _CompactProbe.constructed == 1

    def test_spec_built_across_a_registration_change_is_not_kept(self, engine: Engine) -> None:
        """A node whose creation changes registrations leaves nothing cached that may describe stale code."""
        library = LibraryRegistry.generate_new_library(library_data=_schema(LIBRARY_NAME))

        class _RegisteringProbe(BaseNode):
            constructed: ClassVar[int] = 0

            def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
                super().__init__(name=name, metadata=metadata)
                type(self).constructed += 1
                if not library.has_node_type(_ReplacementProbe.__name__):
                    library.register_new_node_type(_ReplacementProbe, _metadata())

        library.register_new_node_type(_RegisteringProbe, _metadata())

        _describe(engine, _RegisteringProbe.__name__)
        _describe(engine, _RegisteringProbe.__name__)

        assert _RegisteringProbe.constructed == 2  # noqa: PLR2004


class TestDescribeNodeTypeCompactSandboxReregistration:
    """Registering a sandbox node again from edited source describes the edited code."""

    _FILE_NAME = "describe_sandbox_node.py"
    _SOURCE_TEMPLATE = (
        "from griptape_nodes.exe_types.core_types import Parameter\n"
        "from griptape_nodes.exe_types.node_types import BaseNode\n"
        "\n"
        "class DescribeSandboxNode(BaseNode):\n"
        "    def __init__(self, name, metadata=None):\n"
        "        super().__init__(name=name, metadata=metadata)\n"
        "        self.add_parameter(Parameter(name='{parameter}', type='str', tooltip='Sandbox parameter'))\n"
        "\n"
        "    def process(self) -> None:\n"
        "        return None\n"
    )

    @pytest.fixture
    def sandbox_dir(self, engine: Engine, tmp_path: Path) -> Generator[Path, None, None]:
        """A temp sandbox directory and an empty Sandbox Library, as engine startup would create."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        schema = _schema(LibraryManager.SANDBOX_LIBRARY_NAME)
        schema.categories = [
            {
                LibraryManager.SANDBOX_CATEGORY_NAME: CategoryDefinition(
                    title="Sandbox", description="test", color="#000", icon="Folder"
                )
            }
        ]
        LibraryRegistry.generate_new_library(library_data=schema)
        with patch.object(engine.library_manager.sandbox, "get_sandbox_directory", return_value=sandbox_dir):
            yield sandbox_dir

    def _register(self, engine: Engine, source_file: Path, parameter: str) -> None:
        source_file.write_text(self._SOURCE_TEMPLATE.format(parameter=parameter))
        result = engine.library_manager.sandbox.register_sandbox_node_from_source_request(
            RegisterSandboxNodeFromSourceRequest(file_path=str(source_file), replace_if_exists=True)
        )
        assert isinstance(result, RegisterSandboxNodeFromSourceResultSuccess), result.result_details

    def test_reregistered_sandbox_node_is_described_again(self, engine: Engine, sandbox_dir: Path) -> None:
        source_file = sandbox_dir / self._FILE_NAME

        self._register(engine, source_file, "first_version")
        first = _describe(engine, "DescribeSandboxNode")
        assert _parameter_names(first) == ["first_version"]

        self._register(engine, source_file, "second_version")
        second = _describe(engine, "DescribeSandboxNode")
        assert _parameter_names(second) == ["second_version"]
