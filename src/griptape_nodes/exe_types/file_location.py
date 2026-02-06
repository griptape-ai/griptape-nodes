"""FileLocation class for encapsulating file paths with save policies."""

from dataclasses import dataclass
from typing import Any

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import GetPathForMacroRequest, GetPathForMacroResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@dataclass(frozen=True)
class FileLocation:
    """Encapsulates a file path with save policies and macro template for deferred resolution.

    Stores the macro template and base variables instead of a pre-resolved path. This allows
    resolution at save-time with additional variables like {index} for multi-image generation.

    Attributes:
        macro_template: Macro template string (e.g., "{outputs}/{workflow_name}_{file_name_base}.{file_extension}")
        base_variables: Variables for macro resolution (e.g., {"file_name_base": "output", "file_extension": "png"})
        existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)
        create_parent_dirs: Whether to create intermediate directories
    """

    macro_template: str
    base_variables: dict[str, str | int]
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    create_parent_dirs: bool = True

    def save(
        self,
        data: bytes,
        index: int = 0,
        *,
        use_direct_save: bool = True,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Save data by resolving macro template at save-time with optional index.

        Args:
            data: Binary data to save
            index: Index for multi-image generation (0 for single image)
            use_direct_save: Whether to save directly without cloud storage
            skip_metadata_injection: Whether to skip metadata injection

        Returns:
            URL of the saved file for UI display

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails or macro resolution fails
        """
        # Merge index into variables (only if index > 0 for backward compatibility)
        variables = self.base_variables.copy()
        if index > 0:
            variables["index"] = index

        # Resolve macro with ProjectManager
        parsed_macro = ParsedMacro(self.macro_template)
        resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
        result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

        if not isinstance(result, GetPathForMacroResultSuccess):
            error_msg = f"Failed to resolve macro template '{self.macro_template}' with variables {variables}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        # Extract filename from resolved absolute path
        file_name = result.absolute_path.name

        # Save via StaticFilesManager
        return GriptapeNodes.StaticFilesManager().save_static_file(
            data=data,
            file_name=file_name,
            existing_file_policy=self.existing_file_policy,
            use_direct_save=use_direct_save,
            skip_metadata_injection=skip_metadata_injection,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize FileLocation for workflow save.

        Returns:
            Dictionary with macro_template, base_variables, existing_file_policy, create_parent_dirs
        """
        return {
            "macro_template": self.macro_template,
            "base_variables": self.base_variables,
            "existing_file_policy": self.existing_file_policy.value,
            "create_parent_dirs": self.create_parent_dirs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileLocation":
        """Deserialize FileLocation from workflow load with backward compatibility.

        Args:
            data: Dictionary with serialized FileLocation data

        Returns:
            FileLocation instance
        """
        # Backward compatibility: convert old format (resolved_path) to new format (macro_template + variables)
        if "resolved_path" in data and "macro_template" not in data:
            # Old format: just use the resolved path as a literal template
            resolved_path = data["resolved_path"]
            return cls(
                macro_template=resolved_path,
                base_variables={},
                existing_file_policy=ExistingFilePolicy(data["existing_file_policy"]),
                create_parent_dirs=data.get("create_parent_dirs", True),
            )

        # New format
        return cls(
            macro_template=data["macro_template"],
            base_variables=data["base_variables"],
            existing_file_policy=ExistingFilePolicy(data["existing_file_policy"]),
            create_parent_dirs=data.get("create_parent_dirs", True),
        )

    def __str__(self) -> str:
        """Return resolved path for string conversion (resolves macro with base variables)."""
        parsed_macro = ParsedMacro(self.macro_template)
        resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=self.base_variables)
        result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

        if isinstance(result, GetPathForMacroResultSuccess):
            return str(result.absolute_path)

        # Fallback: return the template itself if resolution fails
        return self.macro_template
