"""Validators that aren't about one file: a list's length, and limits picked by another parameter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.input_checks import check_count
from griptape_nodes.exe_types.validators.base import MediaInfo, PreRunValidator

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from griptape_nodes.exe_types.node_error import NodeError
    from griptape_nodes.exe_types.node_types import BaseNode

__all__ = ["ByParameter", "MaxCount"]


@dataclass(frozen=True)
class MaxCount(PreRunValidator):
    """The most items a list parameter accepts.

    Args:
        maximum: The most items accepted.
        noun: The plural of what is counted, such as "images", for the message.
    """

    checks_whole_list = True

    maximum: int
    noun: str = "items"

    def check(self, value: Any, *, subject: str, media: MediaInfo, docs_url: str | None) -> NodeError | None:  # noqa: ARG002
        return check_count(len(value), maximum=self.maximum, parameter=subject, noun=self.noun, docs_url=docs_url)


@dataclass(frozen=True, init=False)
class ByParameter(PreRunValidator):
    """Limits that depend on another parameter's value, such as the selected model.

    At the node's turn, the validators listed for the other parameter's current value apply, or
    `default` for a value not listed. The lists hold plain validators: one `ByParameter` can't pick
    another.

    ```python
    ByParameter(
        "model",
        {"pro": [SideRange(min=300), MaxFileSize(10 * MB)]},
        default=[SideRange(min=512)],
    )
    ```

    Args:
        parameter: The name of the parameter whose value picks the limits.
        choices: The validators for each value of that parameter.
        default: The validators for any other value.

    Raises:
        TypeError: If a list holds another `ByParameter`.
    """

    parameter: str
    # Pairs rather than a dict, so the validator stays frozen and hashable.
    choices: tuple[tuple[str, tuple[PreRunValidator, ...]], ...]
    default: tuple[PreRunValidator, ...]

    def __init__(
        self,
        parameter: str,
        choices: Mapping[str, Sequence[PreRunValidator]],
        *,
        default: Sequence[PreRunValidator] = (),
    ) -> None:
        frozen_choices = tuple((value, tuple(validators)) for value, validators in choices.items())
        frozen_default = tuple(default)
        for _, validators in (*frozen_choices, ("", frozen_default)):
            for validator in validators:
                if isinstance(validator, ByParameter):
                    msg = (
                        f"Attempted to pick validators by parameter '{parameter}'. Failed because one of its "
                        f"lists holds another ByParameter, on '{validator.parameter}'; list plain validators."
                    )
                    raise TypeError(msg)
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "choices", frozen_choices)
        object.__setattr__(self, "default", frozen_default)

    def check(self, value: Any, *, subject: str, media: MediaInfo, docs_url: str | None) -> NodeError | None:  # noqa: ARG002
        # The engine runs the validators `selected` picks; this one has nothing of its own to check.
        return None

    def selected(self, node: BaseNode) -> Sequence[PreRunValidator]:
        """The validators listed for the other parameter's current value, or `default`."""
        current = node.get_parameter_value(self.parameter)
        for value, validators in self.choices:
            if current == value:
                return validators
        return self.default

    def candidates(self) -> Sequence[PreRunValidator]:
        """Every validator this can pick, from every list."""
        everything: list[PreRunValidator] = []
        for _, validators in self.choices:
            everything.extend(validators)
        everything.extend(self.default)
        return everything
