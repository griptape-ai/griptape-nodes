import contextlib
import logging
from collections.abc import Iterator
from pathlib import Path

import torch  # type: ignore[reportMissingImports]
from accelerate import cpu_offload  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


def apply_cpu_offload_to_non_lora_modules(model: torch.nn.Module, device: torch.device) -> None:
    """Applies Accelerate's CPU offload to only the non-LoRA parts of a PEFT model."""
    offloaded_count = 0
    skipped_count = 0
    # for name, module in model.named_children():
    for name, module in model.named_modules():
        if len(list(module.children())) != 0:
            continue

        if "lora_" in name:
            skipped_count += 1
        else:
            cpu_offload(module, device)
            offloaded_count += 1

    logger.info("Applied CPU offload to %d non-LoRA modules, skipped %d LoRA modules.", offloaded_count, skipped_count)


def print_device_for_modules(model: torch.nn.Module) -> None:
    """Prints the device information for each module in the model."""
    count_by_device = {}
    # for name, module in model.named_children():
    for _name, module in model.named_modules():
        if len(list(module.children())) != 0:
            continue
        try:
            device = next(module.parameters()).device
        except Exception:
            device = "none"
        count_by_device[device] = count_by_device.get(device, 0) + 1
    for device_type, count in count_by_device.items():
        logger.info("Module count for device %s: %d", device_type, count)


def lora_modules_to(model: torch.nn.Module, device: torch.device, dtype: torch.dtype) -> None:
    """Moves only the LoRA modules of a PEFT model to the specified device and dtype."""
    for name, module in model.named_children():
        if len(list(module.children())) != 0:
            continue

        if "lora_" in name:
            module.to(device=device, dtype=dtype)


@contextlib.contextmanager
def gpu_vram_profiling(output_snapshot_html_path_str: str) -> Iterator[None]:
    """Context manager to profile GPU VRAM usage and generate a snapshot HTML report.

    This will only work if the system has a CUDA-capable GPU and the torch.cuda module is available.

    Args:
        output_snapshot_html_path_str (str): The path where the HTML snapshot report will be saved.
    """
    if output_snapshot_html_path_str and torch.cuda.is_available():
        logger.info("Starting cuda memory profiling")
        torch.cuda.memory._record_memory_history(max_entries=100000)

    try:
        yield
    finally:
        if output_snapshot_html_path_str and torch.cuda.is_available():
            try:
                snapshot_html_path = Path(output_snapshot_html_path_str)
                logger.info("Generating cuda memory profile html report at %s", snapshot_html_path)
                snapshot = torch.cuda.memory._snapshot()
                html_content = torch.cuda._memory_viz.trace_plot(snapshot)
                snapshot_html_path.write_text(html_content)
            except Exception:
                logger.exception("Failed to capture memory snapshot")

            # Stop recording memory snapshot history.
            logger.info("Stopping cuda memory profiling")
            torch.cuda.memory._record_memory_history(enabled=None)
