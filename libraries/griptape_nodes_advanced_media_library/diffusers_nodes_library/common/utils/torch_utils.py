import logging
import os
import platform
import sys

import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


def to_human_readable_size(size_in_bytes: float) -> str:
    """Convert a memory size in bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if size_in_bytes < 1024:  # noqa: PLR2004
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024
    return f"{size_in_bytes:.2f} EB"


def human_readable_memory_footprint(model: torch.nn.Module) -> str:
    """Return a human-readable memory footprint."""
    return to_human_readable_size(model.get_memory_footprint())  # type: ignore[reportAttributeAccessIssue]


def get_model_memory(model: torch.nn.Module | None) -> int:
    """Calculate accurate memory footprint by examining all parameters and buffers."""
    if model is None:
        return 0

    total_bytes = 0

    # Calculate parameter memory
    for param in model.parameters():
        total_bytes += param.numel() * param.element_size()

    # Calculate buffer memory (batch norm stats, etc.)
    for buffer in model.buffers():
        total_bytes += buffer.numel() * buffer.element_size()

    return total_bytes


def get_bytes_by_component(pipe: DiffusionPipeline, component_names: list[str]) -> dict[str, int]:
    """Get bytes by component for a DiffusionPipeline."""
    bytes_by_component = {}
    for name in component_names:
        if hasattr(pipe, name):
            component = getattr(pipe, name)
            bytes_by_component[name] = get_model_memory(component)
        else:
            logger.warning("Pipeline does not have component %s", name)
            bytes_by_component[name] = None
    return bytes_by_component


def get_total_memory_footprint(pipe: DiffusionPipeline, component_names: list[str]) -> int:
    """Get total memory footprint of a DiffusionPipeline."""
    bytes_by_component = get_bytes_by_component(pipe, component_names)
    total_bytes = sum(bytes_ for bytes_ in bytes_by_component.values() if bytes_ is not None)
    return total_bytes


def get_max_memory_footprint(pipe: DiffusionPipeline, component_names: list[str]) -> int:
    """Get max memory footprint of a DiffusionPipeline."""
    bytes_by_component = get_bytes_by_component(pipe, component_names)
    max_bytes = max((bytes_ for bytes_ in bytes_by_component.values() if bytes_ is not None), default=0)
    return max_bytes


def print_pipeline_memory_footprint(pipe: DiffusionPipeline, component_names: list[str]) -> None:
    """Print pipeline memory footprint by measuring actual tensor sizes."""
    bytes_by_component = get_bytes_by_component(pipe, component_names)
    component_bytes = [bytes_by_component[name] for name in component_names if bytes_by_component[name] is not None]
    total_bytes = sum(component_bytes)
    max_bytes = max(component_bytes, default=0)

    for name, bytes_ in bytes_by_component.items():
        if bytes_ is None:
            continue
        logger.info("%s: %s", name, to_human_readable_size(bytes_))
    logger.info("-" * 30)
    logger.info("Total: %s", to_human_readable_size(total_bytes))
    logger.info("Max: %s", to_human_readable_size(max_bytes))
    logger.info("")


def get_best_device(*, quiet: bool = False) -> torch.device:  # noqa: C901 PLR0911 PLR0912
    """Gets the best torch device using heuristics."""
    system = platform.system()
    machine = platform.machine().lower()
    python_version = sys.version.split()[0]

    if not quiet:
        logger.info("Detected system: %s, machine: %s, Python: %s", system, machine, python_version)

    # TPU detection (Colab etc.)
    if "COLAB_TPU_ADDR" in os.environ:
        try:
            import torch_xla.core.xla_model as xm  # pyright: ignore[reportMissingImports]

            device = xm.xla_device()
            if not quiet:
                logger.info("Detected TPU environment, using XLA device.")
            return device  # noqa: TRY300
        except ImportError:
            if not quiet:
                logger.info("TPU environment detected but torch-xla not installed, skipping TPU.")

    # Mac branch
    if system == "Darwin":
        if machine == "arm64":
            if torch.backends.mps.is_available():
                if not quiet:
                    logger.info("Detected macOS with Apple Silicon (arm64), using MPS device.")
                return torch.device("mps")
            if not quiet:
                logger.info("Detected macOS with Apple Silicon (arm64), but MPS unavailable, using CPU.")
            return torch.device("cpu")
        if not quiet:
            logger.info("Detected macOS with Intel architecture (x86_64), using CPU.")
        return torch.device("cpu")

    # Windows branch
    if system == "Windows":
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            if not quiet:
                logger.info("Detected Windows with CUDA support, using CUDA device: %s.", device_name)
            return torch.device("cuda")
        try:
            import torch_directml  # pyright: ignore[reportMissingImports]

            device = torch_directml.device()
            if not quiet:
                logger.info("Detected Windows without CUDA, using DirectML device.")
            return device  # noqa: TRY300
        except ImportError:
            if not quiet:
                logger.info("Detected Windows without CUDA or DirectML, using CPU.")
        return torch.device("cpu")

    # Linux branch
    if system == "Linux":
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            if not quiet:
                logger.info("Detected Linux with CUDA support, using CUDA device: %s.", device_name)
            return torch.device("cuda")
        if not quiet:
            logger.info("Detected Linux without CUDA support, using CPU.")
        return torch.device("cpu")

    # Unknown OS fallback
    if not quiet:
        logger.info("Unknown system '%s', using CPU.", system)
    return torch.device("cpu")


def get_free_cuda_memory() -> int:
    """Get free memory on the current CUDA device."""
    if not torch.cuda.is_available():
        return 0

    device = torch.device("cuda")
    total_memory = torch.cuda.get_device_properties(device).total_memory
    free_memory = total_memory - torch.cuda.memory_allocated(device)
    return free_memory


def should_enable_attention_slicing(device: torch.device) -> bool:  # noqa: PLR0911
    """Decide whether to enable attention slicing based on the device and platform."""
    system = platform.system()

    # Special logic for macOS
    if system == "Darwin":
        if device.type != "mps":
            logger.info("macOS detected with device %s, not MPS — enabling attention slicing.", device.type)
            return True
        # Check system RAM
        total_ram_gb = torch.mps.recommended_max_memory() - torch.mps.current_allocated_memory()
        if total_ram_gb < 64:  # noqa: PLR2004
            logger.info("macOS detected with MPS device and %.1f GB RAM — enabling attention slicing.", total_ram_gb)
            return True
        logger.info("macOS detected with MPS device and %.1f GB RAM — attention slicing not needed.", total_ram_gb)
        return False

    # Other platforms
    if device.type in ["cpu", "mps"]:
        logger.info("Device %s is memory-limited (CPU or MPS), enabling attention slicing.", device)
        return True

    if device.type == "cuda":
        total_mem = get_free_cuda_memory()
        if total_mem < 8 * 1024**3:  # 8 GB
            logger.info("CUDA device has %s memory, enabling attention slicing.", to_human_readable_size(total_mem))
            return True
        logger.info("CUDA device has %s memory, attention slicing not needed.", to_human_readable_size(total_mem))
        return False

    # Unknown device
    logger.info("Unknown device type %s, enabling attention slicing as precaution.", device)
    return True
