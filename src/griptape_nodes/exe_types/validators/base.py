"""What a pre-run validator is, and what the engine reads for it.

A parameter declares `pre_run_validators=`; the engine runs them at the node's turn, just before
`validate_before_node_run`. Each validator says which readings it needs (`needs`). The engine reads
the union of those once per value and hands the same `MediaInfo` to every validator on the
parameter, so a validator never opens the file itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.input_checks import AudioProbe, ImageInfo, VideoProbe
    from griptape_nodes.exe_types.node_error import NodeError
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.utils.media_values import MediaKind

__all__ = ["MediaInfo", "MediaNeed", "NodeValidator", "PreRunValidator", "media_kind_of"]


class MediaNeed(StrEnum):
    """A reading of a media value that a validator needs."""

    SIZE = "size"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# The reading each media kind's parameter gets for a validator that needs a frame, a format or a length.
_NEED_FOR_KIND: dict[MediaKind, MediaNeed] = {
    "image": MediaNeed.IMAGE,
    "video": MediaNeed.VIDEO,
    "audio": MediaNeed.AUDIO,
}

# The artifact type names a parameter declares for each kind of media.
_KIND_FOR_TYPE: dict[str, MediaKind] = {
    "imageurlartifact": "image",
    "imageartifact": "image",
    "videourlartifact": "video",
    "videoartifact": "video",
    "audiourlartifact": "audio",
    "audioartifact": "audio",
}


@dataclass(frozen=True)
class MediaInfo:
    """What the engine read from one media value: only the readings its validators asked for.

    Each part is None when it wasn't asked for, or couldn't be read locally (a remote URL, a format
    nothing here opens, ffprobe missing or out of time). A validator skips a reading that is None.
    """

    size_bytes: int | None = None
    image: ImageInfo | None = None
    video: VideoProbe | None = None
    audio: AudioProbe | None = None

    @property
    def frame(self) -> ImageInfo | None:
        """The image's pixel size, or the video's frame as stored (turned upright)."""
        if self.image is not None:
            return self.image
        if self.video is not None:
            return self.video.info
        return None

    @property
    def display_frame(self) -> ImageInfo | None:
        """A video frame's shape as it plays when its pixels aren't square, or None."""
        if self.video is None:
            return None
        return self.video.display_info

    @property
    def mime_type(self) -> str | None:
        """The format read from the file: the image's, the video's container or the audio's container."""
        if self.image is not None:
            return self.image.mime_type
        if self.video is not None:
            return self.video.mime_type
        if self.audio is not None:
            return self.audio.mime_type
        return None


class PreRunValidator(ABC):
    """A limit on one input, checked at the node's turn, before it runs.

    Subclasses declare `needs`, the readings `check` uses. A validator on a list parameter checks
    each item, unless it sets `checks_whole_list`, in which case it gets the whole list.
    """

    # The readings `check` uses. A media reading (image, video or audio) is read for the kind the
    # parameter holds; a validator that names none the parameter's kind matches can't go on it.
    needs: ClassVar[frozenset[MediaNeed]] = frozenset()
    # True for a validator that judges a list parameter as a whole, such as how many items it holds.
    checks_whole_list: ClassVar[bool] = False

    @abstractmethod
    def check(self, value: Any, *, subject: str, media: MediaInfo, docs_url: str | None) -> NodeError | None:
        """An error when `value` breaks this limit, or None when it is within it or couldn't be read.

        Args:
            value: The parameter's value; for a list, one item, or the whole list with `checks_whole_list`.
            subject: The start of the message naming the input, such as "Image 2 in 'reference images'".
                With `checks_whole_list`, the parameter's name as the UI shows it.
            media: The readings `needs` asked for, read once for this value.
            docs_url: The node's page documenting its input limits, from `BaseNode.input_limits_url`.
        """

    def selected(self, node: BaseNode) -> Sequence[PreRunValidator]:  # noqa: ARG002
        """The validators that apply on `node` now. A validator is itself; `ByParameter` picks a list."""
        return (self,)

    def candidates(self) -> Sequence[PreRunValidator]:
        """Every validator `selected` can return, so a parameter can refuse one that can't go on it."""
        return (self,)


class NodeValidator(ABC):
    """A rule across several of a node's inputs, declared in the node's `node_validators`.

    Runs after every parameter's validators, at the node's turn.
    """

    @abstractmethod
    def check(
        self, node: BaseNode, *, media: Mapping[str, Sequence[MediaInfo]], docs_url: str | None
    ) -> list[NodeError]:
        """Every error the node's inputs break this rule with, or an empty list.

        Args:
            node: The node about to run.
            media: What the parameter validators read, by parameter name: one `MediaInfo` for a single
                input, one per item, in order, for a list. A parameter none of them read is absent;
                a reader called directly reuses this pass's readings, so reading again costs nothing.
            docs_url: The node's page documenting its input limits, from `BaseNode.input_limits_url`.
        """


def media_kind_of(parameter: Parameter) -> MediaKind | None:
    """The kind of media a parameter holds, or a list parameter's items hold, from its declared type."""
    type_name = parameter.type.strip().lower()
    if type_name.startswith("list[") and type_name.endswith("]"):
        type_name = type_name.removeprefix("list[").removesuffix("]")
    return _KIND_FOR_TYPE.get(type_name)


def holds_list(parameter: Parameter) -> bool:
    """Whether a parameter's value is a list, whose items its validators check one by one."""
    return parameter.type.strip().lower().startswith("list[")


def needs_for_kind(validators: Iterable[PreRunValidator], kind: MediaKind | None) -> frozenset[MediaNeed]:
    """The readings to take of one value for these validators, on a parameter holding `kind`."""
    needs: set[MediaNeed] = set()
    for validator in validators:
        if MediaNeed.SIZE in validator.needs:
            needs.add(MediaNeed.SIZE)
        if kind is not None and _NEED_FOR_KIND[kind] in validator.needs:
            needs.add(_NEED_FOR_KIND[kind])
    return frozenset(needs)

