import logging
import os
import platform
import sys

import diffusers  # type: ignore[reportMissingImports]
import psutil  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn.functional  # type: ignore[reportMissingImports]

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
    return to_human_readable_size(model.get_memory_footprint())


def print_flux_pipeline_memory_footprint(pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline) -> None:
    """Print pipeline memory footprint."""
    transformer_bytes = pipe.transformer.get_memory_footprint()
    text_encoder_bytes = pipe.text_encoder.get_memory_footprint()
    text_encoder_2_bytes = pipe.text_encoder_2.get_memory_footprint()
    # pipe.tokenizer and pipe.tokenizer_2 aren't models?
    # pipe.scheduler is not a model
    vae_bytes = pipe.vae.get_memory_footprint()

    component_bytes = [
        transformer_bytes,
        text_encoder_bytes,
        text_encoder_2_bytes,
        vae_bytes,
    ]
    total_bytes = sum(component_bytes)
    max_bytes = max(component_bytes)

    logger.info("Transformer: %s", to_human_readable_size(transformer_bytes))
    logger.info("Text encoder: %s", to_human_readable_size(text_encoder_bytes))
    logger.info("Text encoder 2: %s", to_human_readable_size(text_encoder_2_bytes))
    logger.info("VAE: %s", to_human_readable_size(vae_bytes))
    logger.info("-" * 30)

    logger.info("Total: %s", to_human_readable_size(total_bytes))
    logger.info("Max: %s", to_human_readable_size(max_bytes))
    logger.info("")


def optimize_flux_pipeline_memory_footprint(pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)

        if hasattr(pipe, "transformer"):
            # This fp8 layerwise caching is important for lower VRAM
            # gpus (say 25GB or lower). Not important if not on a gpu.
            # We only do this for the transformer, because its the biggest.
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
            logger.info("Enabling fp8 layerwise caching for transformer")
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
        # Sequential cpu offload only makes sense for gpus (VRAM <-> RAM).
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae"):
        logger.info("Enabling vae slicing")
        pipe.vae.enable_slicing()

    logger.info("Final memory footprint:")
    print_flux_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        # You must move the pipeline models to MPS if available to
        # use it (otherwise you'll get the CPU).
        logger.info("Transferring model to MPS/GPU (slow because big)")
        logger.info("Sorry bout the lack of a progress bar.")
        pipe.to(device)
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/847

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)
        pass


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


def should_enable_attention_slicing(device: torch.device) -> bool:  # noqa: PLR0911
    """Decide whether to enable attention slicing based on the device and platform."""
    system = platform.system()

    # Special logic for macOS
    if system == "Darwin":
        if device.type != "mps":
            logger.info("macOS detected with device %s, not MPS — enabling attention slicing.", device.type)
            return True
        # Check system RAM
        total_ram_gb = psutil.virtual_memory().total / 1e9
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
        total_mem = torch.cuda.get_device_properties(device).total_memory
        if total_mem < 8 * 1024**3:  # 8 GB
            logger.info("CUDA device has %.1f GB memory, enabling attention slicing.", total_mem / 1e9)
            return True
        logger.info("CUDA device has %.1f GB memory, attention slicing not needed.", total_mem / 1e9)
        return False

    # Unknown device
    logger.info("Unknown device type %s, enabling attention slicing as precaution.", device)
    return True
