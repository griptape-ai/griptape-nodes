import logging
import random
from collections.abc import Callable
from typing import Any

import numpy as np
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pad_mirror  # type: ignore[reportMissingImports]

from diffusers_nodes_library.utils.math_utils import (  # type: ignore[reportMissingImports]
    next_multiple_ge,  # type: ignore[reportMissingImports]
)

type PositionList = list[tuple[int, int]]
type PositionGrid = list[list[tuple[int, int]]]

DEBUG = False

logger = logging.getLogger("diffusers_nodes_library")


class TilingImageProcessor:
    def __init__(
        self,
        pipe: Callable[..., Any],
        tile_size: int,
        tile_overlap: int,
        tile_strategy: str,
    ) -> None:
        self.pipe = pipe
        self.tile_size = tile_size
        self.tile_overlap = tile_overlap
        self.tile_strategy = tile_strategy

    def get_tile_positions(self, image: Image) -> PositionList:
        tile_size = self.tile_size
        tile_overlap = self.tile_overlap
        tile_strategy = self.tile_strategy
        width, height = image.size

        grid = []  # row major order (rows are contiguous)
        # This is stupid, but I actually want to add some unit tests for this.
        for y in range(0, height - tile_overlap, tile_size - tile_overlap):
            # Appending a row
            grid.append([])
            for x in range(0, width - tile_overlap, tile_size - tile_overlap):
                grid[-1].append((x, y))

        match tile_strategy:
            case "linear":
                positions = self._linear_strategy(grid)
            case "chess":
                positions = self._chess_strategy(grid)
            case "random":
                positions = self._random_strategy(grid)
            case "inward":
                positions = self._inward_spiral_strategy(grid)
            case "outward":
                positions = self._outward_spiral_strategy(grid)
            case _:
                raise NotImplementedError
        return positions

    def _linear_strategy(self, grid: PositionGrid) -> PositionList:
        rows = len(grid)
        cols = len(grid[0]) if rows > 0 else 0
        cells = []
        for i in range(rows):
            for j in range(cols):
                cells.append(grid[i][j])  # noqa: PERF401
        return cells

    def _chess_strategy(self, grid: PositionGrid) -> PositionList:
        rows = len(grid)
        cols = len(grid[0]) if rows > 0 else 0
        even_cells = []
        odd_cells = []
        for i in range(rows):
            for j in range(cols):
                if (i + j) % 2 == 0:
                    even_cells.append(grid[i][j])
                else:
                    odd_cells.append(grid[i][j])
        return even_cells + odd_cells

    def _random_strategy(self, grid: PositionGrid) -> PositionList:
        positions = self._linear_strategy(grid)
        random.shuffle(positions)
        return positions

    def _inward_spiral_strategy(self, grid: PositionGrid) -> PositionList:
        result = []
        if not grid or not grid[0]:
            return result

        top, bottom = 0, len(grid) - 1
        left, right = 0, len(grid[0]) - 1

        while top <= bottom and left <= right:
            # Traverse top row from left to right
            for j in range(left, right + 1):
                result.append(grid[top][j])  # noqa: PERF401
            top += 1

            # Traverse right column from top to bottom
            for i in range(top, bottom + 1):
                result.append(grid[i][right])  # noqa: PERF401
            right -= 1

            if top <= bottom:
                # Traverse bottom row from right to left
                for j in range(right, left - 1, -1):
                    result.append(grid[bottom][j])  # noqa: PERF401
                bottom -= 1

            if left <= right:
                # Traverse left column from bottom to top
                for i in range(bottom, top - 1, -1):
                    result.append(grid[i][left])  # noqa: PERF401
                left += 1

        return result

    def _outward_spiral_strategy(self, grid: PositionGrid) -> PositionList:
        return list(reversed(self._inward_spiral_strategy(grid)))

    def get_num_tiles(self, image: Image) -> int:
        """Returns the number of tiles required for a given image."""
        return len(self.get_tile_positions(image))

    def process(
        self,
        image: Image,
        output_scale: float = 1.0,
        callback_on_tile_end: Any = None,
    ) -> Image:
        """Process an image in tiles with a given model/pipeline/function (self.pipe).

        Args:
            image: image to process given the model/pipeline/function (self.pipe)
            output_scale: The inherent scale factor for the model's output w.r.t. its input.
                For example 4.0 if the model outputs an image that has dimensions
                that are four times the input dimensions.
            pipe_kwargs: Forwarded to the model/pipeline/function
            callback_on_tile_end: Callback to call after each tile.

        Returns:
            a new image - the size of which depends on the the given model/pipeline/function and its inherent output_scale factor
        """
        tile_size = self.tile_size
        width, height = image.size
        result_height, result_width = int(height * output_scale), int(width * output_scale)
        self.result_np = np.zeros((result_height, result_width, 3), dtype=np.float32)
        self.weight_np = np.zeros((result_height, result_width), dtype=np.float32)

        positions = self.get_tile_positions(image)

        def result_to_pil(result_np: np.ndarray, weight_np: np.ndarray) -> Image:
            image_np = result_np / np.maximum(weight_np[..., None], 1e-5)
            output_image_pil = PIL.Image.fromarray(np.clip(image_np, 0, 255).astype(np.uint8))
            return output_image_pil

        # Use a mirrored image to ensure that the tile sizes can be uniform
        # an proportional. This is important for some models (e.g. Flux) where
        # image dimensions must be multiples of 16. Constraints like this lead
        # us toward either resizing the image (non-proportionally) or filling
        # the space with something reasonable. I think the mirror approach
        # is the most compelling, so I'm going with it. Would be nice to make
        # it configurable though.
        #
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/850
        #
        # Many models assume that the tile_size is smaller than the input image.
        # We can either change the tile size or pad the image to fit it.
        # We should pad the image instead of the former. The reason is, is that
        # the tile size will have implications for model compatibility, some
        # models only accept an input of a specific size.
        # Ideally I would choose the tile size in a model compatible way if
        # possible, but that logic should ideally be done by the caller who
        # has that information (using the pre/post process steps mentioned
        # previously.)
        #
        # TL;DR Make sure that the mirrored image is at least as big as the tile.
        padded_size = (next_multiple_ge(width, tile_size), next_multiple_ge(height, tile_size))
        padded_image = pad_mirror(image, padded_size)

        for i, (x, y) in enumerate(positions, start=1):
            logger.info("tile %d of %d", i, len(positions))
            # Determine the tile region within image boundaries
            # Remember that we are assuming a padded image, so
            # we can exceed the original image bounds.
            tile_right = x + tile_size
            tile_bottom = y + tile_size
            tile_box = (x, y, tile_right, tile_bottom)
            tile = padded_image.crop(tile_box)

            def blend_tile(  # noqa: PLR0913
                processed_tile: Image,
                i: int = i,
                x: int = x,
                y: int = y,
                tile: Image = tile,
                tile_right: int = tile_right,
                tile_bottom: int = tile_bottom,
            ) -> tuple[np.ndarray, np.ndarray]:
                # Crop out the padding to recover the original tile
                processed_tile_right = min(self.tile_size, width - x) * output_scale
                processed_tile_bottom = min(self.tile_size, height - y) * output_scale
                processed_tile_box = (0, 0, processed_tile_right, processed_tile_bottom)
                processed_cropped_tile = processed_tile.crop(processed_tile_box)

                logger.info("tile input size: %s", tile.size)
                logger.info("tile output size: %s", processed_tile.size)

                tile_np = np.array(processed_cropped_tile).astype(np.float32)
                oh, ow = tile_np.shape[:2]
                ox, oy = int(x * output_scale), int(y * output_scale)

                # Create local weight mask
                is_left = ox == 0
                is_top = oy == 0
                is_right = tile_right == width
                is_bottom = tile_bottom == height

                weight_mask = create_weight_mask((ow, oh), self.tile_overlap, (is_left, is_top, is_right, is_bottom))

                if DEBUG:
                    # Saves an individual tile with a heatmap overlay to visualize the
                    # weight mask.
                    debug_tile = visualize_weight_mask(processed_cropped_tile, weight_mask)
                    debug_tile.save(f"weight_mask_tile_{i}.png")

                # Blend into result
                new_result_np = self.result_np.copy()
                new_weight_np = self.weight_np.copy()

                new_result_np[oy : oy + oh, ox : ox + ow] += tile_np * weight_mask[..., None]
                new_weight_np[oy : oy + oh, ox : ox + ow] += weight_mask

                return (new_result_np, new_weight_np)

            def get_preview_image_with_partial_tile(partial_processed_tile: Image) -> Image:
                partial_result_np, partial_weight_np = blend_tile(partial_processed_tile)
                partial_result = result_to_pil(partial_result_np, partial_weight_np)
                return partial_result

            # Process the tile
            processed_tile = self.pipe(tile, get_preview_image_with_partial_tile)
            self.result_np, self.weight_np = blend_tile(processed_tile)

            if callback_on_tile_end:
                callback_on_tile_end(i, result_to_pil(self.result_np, self.weight_np))

        return result_to_pil(self.result_np, self.weight_np)


def create_weight_mask(size: tuple[int, int], overlap: int, is_edge: tuple[bool, bool, bool, bool]) -> np.ndarray:
    """Create a 2D blending mask using 1D linear ramps, accounting for image edges.

    Args:
        size (tuple): (width, height) of the tile.
        overlap (int): Overlap in pixels.
        is_edge (tuple): (left, top, right, bottom) — True if tile touches that image edge.

    Returns:
        np.ndarray: 2D blending mask (height, width) in [0.0, 1.0]
    """
    width, height = size
    left, top, right, bottom = is_edge

    if overlap == 0:
        return np.ones((height, width))

    # Clamp overlap to avoid overflow
    #
    # Long explanation of "why the +1"
    # Add one because we are using linespace with the start value of 1,
    # a weight of 1 should not be used if is actually overlapping cause
    # you'd only see one of the tiles and that's not really overlapping is it?
    # That means that the start pixel that gets the start value from linspace
    # technically isn't part of the overlap, thus we need to expand the "overlap"
    # region by 1.
    # Alternatively, you  could consider adding an endpoint for 0 to make it symmetric
    # but then you'd not be able to handle certain values of overlap (e.g. when it equals
    # exactly 1, ideally you'd have 0.5 weight on one tile and 0.5 weight on the other in
    # the overlapping region.
    ox = min(overlap, width // 2) + 1
    oy = min(overlap, height // 2) + 1

    # Horizontal ramp
    ramp_x = np.ones(width, dtype=np.float32)
    if not left:
        ramp_x[:ox] = np.flip(np.linspace(1, 0, ox, endpoint=False))
    if not right:
        ramp_x[-ox:] = np.linspace(1, 0, ox, endpoint=False)

    # Vertical ramp
    ramp_y = np.ones(height, dtype=np.float32)
    if not top:
        ramp_y[:oy] = np.flip(np.linspace(1, 0, oy, endpoint=False))
    if not bottom:
        ramp_y[-oy:] = np.linspace(1, 0, oy, endpoint=False)

    return np.outer(ramp_y, ramp_x)


# Useful for debugging the tiles.
def visualize_weight_mask(tile: Image, weight_mask: np.ndarray) -> Image:
    """Overlay a weight mask onto a tile for debugging.

    Args:
        tile (PIL.Image): Original tile image.
        weight_mask (np.ndarray): 2D blending weight mask in [0, 1].

    Returns:
        Image: Tile with weight mask overlay.
    """
    tile_rgba = tile.convert("RGBA")
    r = (weight_mask * 255).astype(np.uint8)
    g = ((1 - weight_mask) * 255).astype(np.uint8)
    b = np.zeros_like(r)
    heat = np.stack([r, g, b], axis=-1)
    heatmap = PIL.Image.fromarray(heat, mode="RGB").convert("RGBA")
    return PIL.Image.blend(tile_rgba, heatmap, alpha=0.5)


def apply_random_tint(tile_np: np.ndarray) -> np.ndarray:
    """Applies a random color tint to a tile. Useful for debugging."""
    r = random.uniform(0.6, 1.0)  # noqa: S311
    g = random.uniform(0.6, 1.0)  # noqa: S311
    b = random.uniform(0.6, 1.0)  # noqa: S311
    tint = np.array([r, g, b], dtype=np.float32)
    return np.clip(tile_np * tint, 0, 255)
