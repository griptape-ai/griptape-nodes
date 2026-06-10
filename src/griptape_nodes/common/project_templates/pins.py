"""Engine and library version pins for a project template.

A project may declare the engine version it requires and the libraries (with
versions) it runs against, making the project the source of truth for its
runtime: an engine mismatch blocks the load, and declared libraries are
provisioned to match when the project is activated.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LibraryPin(BaseModel):
    """A single library a project pins to a version and install source.

    A pin must carry enough to *install* the library, not just identify it:
    a `git_url` (the engine's `url@ref` convention, shared with
    `libraries_to_download`) and/or a PyPI `requirement_specifier`. At least
    one source is required.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Library name, matching the library's manifest `name`")
    version: str | None = Field(
        default=None,
        description="PEP 440 version specifier the installed library must satisfy (e.g. '>=1.2,<2'). None pins by source only.",
    )
    git_url: str | None = Field(
        default=None,
        description=(
            "Git source in the engine's `url@ref` form (same as `libraries_to_download`): "
            "a full URL or `user/repo` shorthand, with an optional `@branch|tag|commit` suffix "
            "(e.g. 'griptape-ai/griptape-nodes-library-standard@v2.0')."
        ),
    )
    requirement_specifier: str | None = Field(
        default=None,
        description="PyPI requirement specifier used to install the library into its own venv (e.g. 'my-lib==2.0').",
    )

    @model_validator(mode="after")
    def _at_least_one_source(self) -> Self:
        if self.git_url is None and self.requirement_specifier is None:
            msg = f"LibraryPin '{self.name}' requires at least one of 'git_url' or 'requirement_specifier'"
            raise ValueError(msg)
        return self


class VersionPins(BaseModel):
    """Engine and library version pins declared by a project template."""

    model_config = ConfigDict(extra="forbid")

    engine_version: str | None = Field(
        default=None,
        description="PEP 440 version specifier the running engine must satisfy (e.g. '>=0.5,<0.6'). A mismatch blocks the load.",
    )
    libraries: list[LibraryPin] = Field(
        default_factory=list,
        description="Libraries to provision to their pinned versions when the project is activated.",
    )
