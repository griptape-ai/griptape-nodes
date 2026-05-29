"""Per-platform project path mapping shared by `projects_to_register` and `parent_project_path`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from griptape_nodes.common.project_templates.directory import _active_platform_key


class PerPlatformProjectPath(BaseModel):
    """Per-platform mapping for a project YAML path.

    Used by `projects_to_register` (engine config) and `parent_project_path`
    (project template) to express a single logical project that lives at
    different filesystem paths on different operating systems. Mirrors the
    shape of `PerPlatformPathMacro`, but is a separate class because the
    semantics (a project file path vs. a directory path macro) are
    independent and may evolve separately.

    At least one of `linux`, `darwin`, `windows`, or `default` must be set.
    `default` is consulted when the active platform's key is absent. Field
    names match the keys used in `PerPlatformPathMacro` so admins learn one
    pattern.
    """

    model_config = ConfigDict(extra="forbid")

    linux: str | None = Field(default=None, description="Project path used on Linux")
    darwin: str | None = Field(default=None, description="Project path used on macOS")
    windows: str | None = Field(default=None, description="Project path used on Windows")
    default: str | None = Field(
        default=None, description="Fallback project path when the active platform's key is unset"
    )

    @model_validator(mode="after")
    def _at_least_one_key(self) -> PerPlatformProjectPath:
        if self.linux is None and self.darwin is None and self.windows is None and self.default is None:
            msg = "PerPlatformProjectPath requires at least one of 'linux', 'darwin', 'windows', or 'default'"
            raise ValueError(msg)
        return self

    def select(self) -> str | None:
        """Return the project path for the active platform, falling back to `default`."""
        active = _active_platform_key()
        if active == "linux" and self.linux is not None:
            return self.linux
        if active == "darwin" and self.darwin is not None:
            return self.darwin
        if active == "windows" and self.windows is not None:
            return self.windows
        return self.default


def select_project_path(value: str | PerPlatformProjectPath | None) -> str | None:
    """Reduce a per-platform path union to a single string for the active platform.

    - `None` returns `None` (no path declared).
    - A plain string is passed through unchanged.
    - A `PerPlatformProjectPath` returns its `.select()` value, which may be
      `None` when no key matches the active platform and `default` is unset
      (callers are expected to skip-with-warning in that case).
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.select()
