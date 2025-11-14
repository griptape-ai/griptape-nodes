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


def get_available_cuda_devices() -> list[int]:
    """Get list of available CUDA device indices."""
    if not torch.cuda.is_available():
        return []

    return list(range(torch.cuda.device_count()))


def get_cuda_device_info(device_id: int) -> dict[str, str | int]:
    """Get information about a specific CUDA device."""
    if not torch.cuda.is_available():
        return {}

    if device_id >= torch.cuda.device_count():
        return {}

    props = torch.cuda.get_device_properties(device_id)
    return {
        "name": props.name,
        "total_memory": props.total_memory,
        "total_memory_human": to_human_readable_size(props.total_memory),
        "major": props.major,
        "minor": props.minor,
        "multi_processor_count": props.multi_processor_count,
    }


def get_cuda_devices_by_free_memory() -> list[tuple[int, int]]:
    """Get CUDA devices sorted by free memory (descending).

    Returns:
        List of tuples (device_id, free_memory_bytes) sorted by free memory descending.
    """
    if not torch.cuda.is_available():
        return []

    device_count = torch.cuda.device_count()
    devices_with_memory = []

    for device_id in range(device_count):
        props = torch.cuda.get_device_properties(device_id)
        total_memory = props.total_memory
        allocated_memory = torch.cuda.memory_allocated(device_id)
        free_memory = total_memory - allocated_memory
        devices_with_memory.append((device_id, free_memory))

    devices_with_memory.sort(key=lambda x: x[1], reverse=True)
    return devices_with_memory


def create_device_map_for_pipeline(component_names: list[str], num_gpus: int | None = None) -> dict[str, int | str]:
    """Create a device_map for distributing pipeline components across GPUs.

    Args:
        component_names: List of component names to distribute (e.g., ['vae', 'text_encoder', 'transformer'])
        num_gpus: Number of GPUs to use. If None, uses all available GPUs.

    Returns:
        Dictionary mapping component names to device IDs (e.g., {'vae': 0, 'transformer': 1})
    """
    if not torch.cuda.is_available():
        return dict.fromkeys(component_names, "cpu")

    available_gpus = torch.cuda.device_count()
    gpus_to_use = num_gpus if num_gpus is not None else available_gpus
    gpus_to_use = min(gpus_to_use, available_gpus)

    if gpus_to_use <= 0:
        return dict.fromkeys(component_names, "cpu")

    device_map = {}
    for idx, component_name in enumerate(component_names):
        device_id = idx % gpus_to_use
        device_map[component_name] = device_id

    return device_map


def get_devices(*, quiet: bool = False, num_gpus: int | None = None) -> list[torch.device]:  # noqa: C901 PLR0911 PLR0912 PLR0915
    """Gets available torch devices using heuristics.

    Args:
        quiet: If True, suppress logging output
        num_gpus: Number of GPUs to use. If None, uses all available GPUs.

    Returns:
        List of torch devices. For multi-GPU systems, returns multiple cuda devices.
        For single device systems, returns a single-item list.
    """
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
            return [device]  # noqa: TRY300
        except ImportError:
            if not quiet:
                logger.info("TPU environment detected but torch-xla not installed, skipping TPU.")

    # Mac branch
    if system == "Darwin":
        if machine == "arm64":
            if torch.backends.mps.is_available():
                if not quiet:
                    logger.info("Detected macOS with Apple Silicon (arm64), using MPS device.")
                return [torch.device("mps")]
            if not quiet:
                logger.info("Detected macOS with Apple Silicon (arm64), but MPS unavailable, using CPU.")
            return [torch.device("cpu")]
        if not quiet:
            logger.info("Detected macOS with Intel architecture (x86_64), using CPU.")
        return [torch.device("cpu")]

    # Windows branch
    if system == "Windows":
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            requested_gpus = num_gpus if num_gpus is not None else device_count
            requested_gpus = min(requested_gpus, device_count)

            devices = [torch.device(f"cuda:{device_id}") for device_id in range(requested_gpus)]

            if not quiet:
                if len(devices) > 1:
                    device_names = [torch.cuda.get_device_name(i) for i in range(len(devices))]
                    logger.info("Detected Windows with CUDA support, using %s GPUs: %s", len(devices), device_names)
                else:
                    device_name = torch.cuda.get_device_name(0)
                    logger.info("Detected Windows with CUDA support, using CUDA device: %s.", device_name)
            return devices

        try:
            import torch_directml  # pyright: ignore[reportMissingImports]

            device = torch_directml.device()
            if not quiet:
                logger.info("Detected Windows without CUDA, using DirectML device.")
            return [device]  # noqa: TRY300
        except ImportError:
            if not quiet:
                logger.info("Detected Windows without CUDA or DirectML, using CPU.")
        return [torch.device("cpu")]

    # Linux branch
    if system == "Linux":
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            requested_gpus = num_gpus if num_gpus is not None else device_count
            requested_gpus = min(requested_gpus, device_count)

            devices = [torch.device(f"cuda:{device_id}") for device_id in range(requested_gpus)]

            if not quiet:
                if len(devices) > 1:
                    device_names = [torch.cuda.get_device_name(i) for i in range(len(devices))]
                    logger.info("Detected Linux with CUDA support, using %s GPUs: %s", len(devices), device_names)
                else:
                    device_name = torch.cuda.get_device_name(0)
                    logger.info("Detected Linux with CUDA support, using CUDA device: %s.", device_name)
            return devices

        if not quiet:
            logger.info("Detected Linux without CUDA support, using CPU.")
        return [torch.device("cpu")]

    # Unknown OS fallback
    if not quiet:
        logger.info("Unknown system '%s', using CPU.", system)
    return [torch.device("cpu")]


def get_best_device(*, quiet: bool = False) -> torch.device:
    """Gets the best single torch device using heuristics.

    This is a compatibility wrapper around get_devices() that returns a single device.
    For multi-GPU support, use get_devices() instead.

    Args:
        quiet: If True, suppress logging output

    Returns:
        A single torch device (the first/best available device)
    """
    devices = get_devices(quiet=quiet, num_gpus=1)
    return devices[0]


def get_free_cuda_memory(device_id: int = 0) -> int:
    """Get free memory on a specific CUDA device.

    Args:
        device_id: CUDA device ID (default: 0)

    Returns:
        Free memory in bytes
    """
    if not torch.cuda.is_available():
        return 0

    if device_id >= torch.cuda.device_count():
        return 0

    total_memory = torch.cuda.get_device_properties(device_id).total_memory
    free_memory = total_memory - torch.cuda.memory_allocated(device_id)
    return free_memory


def get_total_free_cuda_memory() -> int:
    """Get total free memory across all CUDA devices.

    Returns:
        Total free memory in bytes across all GPUs
    """
    if not torch.cuda.is_available():
        return 0

    total_free = 0
    for device_id in range(torch.cuda.device_count()):
        total_free += get_free_cuda_memory(device_id)

    return total_free


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
