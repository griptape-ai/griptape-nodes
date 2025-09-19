import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,
    get_total_memory_footprint,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
    to_human_readable_size,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.diptych_flux_fill_pipeline_parameters import (
    DiptychFluxFillPipelineParameters,
)
from diffusers_nodes_library.pipelines.flux.flux_fill_pipeline_parameters import (
    FluxFillPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.flux_pipeline_parameters import FluxPipelineParameters

logger = logging.getLogger("diffusers_nodes_library")


FLUX_PIPELINE_COMPONENT_NAMES = [
    "vae",
    "text_encoder",
    "text_encoder_2",
    "transformer",
    "controlnet",
]


def print_flux_pipeline_memory_footprint(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
) -> None:
    """Print memory footprint for the main sub-modules of Flux pipelines."""
    print_pipeline_memory_footprint(pipe, FLUX_PIPELINE_COMPONENT_NAMES)


def _check_cuda_memory_sufficient(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline, device: torch.device
) -> bool:
    """Check if CUDA device has sufficient memory for the pipeline."""
    model_memory = get_total_memory_footprint(pipe, FLUX_PIPELINE_COMPONENT_NAMES)
    total_memory = torch.cuda.get_device_properties(device).total_memory
    free_memory = total_memory - torch.cuda.memory_allocated(device)
    return model_memory <= free_memory


def _check_mps_memory_sufficient(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
) -> bool:
    """Check if MPS device has sufficient memory for the pipeline."""
    model_memory = get_total_memory_footprint(pipe, FLUX_PIPELINE_COMPONENT_NAMES)
    recommended_max_memory = torch.mps.recommended_max_memory()
    free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
    return model_memory <= free_memory


def _log_memory_info(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline, device: torch.device
) -> None:
    """Log memory information for the device."""
    model_memory = get_total_memory_footprint(pipe, FLUX_PIPELINE_COMPONENT_NAMES)

    if device.type == "cuda":
        total_memory = torch.cuda.get_device_properties(device).total_memory
        free_memory = total_memory - torch.cuda.memory_allocated(device)
        logger.info("Total memory on %s: %s", device, to_human_readable_size(total_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
    elif device.type == "mps":
        recommended_max_memory = torch.mps.recommended_max_memory()
        free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
        logger.info("Recommended max memory on %s: %s", device, to_human_readable_size(recommended_max_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))

    logger.info("Require memory for Flux Pipeline: %s", to_human_readable_size(model_memory))


def _quantize_flux_pipeline(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
    quantization_mode: str,
    device: torch.device,
) -> None:
    """Uses optimum.quanto to quantize the pipeline components."""
    from optimum.quanto import freeze, qfloat8, qint4, qint8, quantize  # type: ignore[reportMissingImports]

    logger.info("Applying quantization: %s", quantization_mode)
    _log_memory_info(pipe, device)
    quant_map = {"fp8": qfloat8, "int8": qint8, "int4": qint4}
    quant_type = quant_map[quantization_mode]
    if hasattr(pipe, "transformer") and pipe.transformer is not None:
        logger.debug("Quantizing transformer with %s", quantization_mode)
        quantize(pipe.transformer, weights=quant_type, exclude=["proj_out"])
        logger.debug("Freezing transformer")
        freeze(pipe.transformer)
        logger.debug("Quantizing completed for transformer.")
    if hasattr(pipe, "text_encoder") and pipe.text_encoder is not None:
        logger.debug("Quantizing text_encoder with %s", quantization_mode)
        quantize(pipe.text_encoder, weights=quant_type)
        logger.debug("Freezing text_encoder")
        freeze(pipe.text_encoder)
        logger.debug("Quantizing completed for text_encoder.")
    if hasattr(pipe, "text_encoder_2") and pipe.text_encoder_2 is not None:
        logger.debug("Quantizing text_encoder_2 with %s", quantization_mode)
        quantize(pipe.text_encoder_2, weights=quant_type)
        logger.debug("Freezing text_encoder_2")
        freeze(pipe.text_encoder_2)
        logger.debug("Quantizing completed for text_encoder_2.")

    logger.info("Quantization complete.")


def _optimize_flux_pipeline(  # noqa: C901
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
    quantization_mode: str,
    device: torch.device,
) -> None:
    """Optimize pipeline memory footprint with incremental VRAM checking."""
    if device.type == "cuda":
        _log_memory_info(pipe, device)

        if hasattr(pipe, "enable_vae_slicing"):
            logger.info("Enabling vae slicing")
            pipe.enable_vae_slicing()
        elif hasattr(pipe, "vae"):
            logger.info("Enabling vae slicing")
            pipe.vae.enable_slicing()

        if _check_cuda_memory_sufficient(pipe, device):
            logger.info("Sufficient memory. Moving pipeline to %s", device)
            pipe.to(device)
            return

        if quantization_mode == "none":
            logger.warning("Insufficient memory. Enabling fp8 layerwise caching for transformer")
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
            _log_memory_info(pipe, device)
            if _check_cuda_memory_sufficient(pipe, device):
                logger.info("Sufficient memory after fp8 optimization. Moving pipeline to %s", device)
                pipe.to(device)
                return

            if hasattr(pipe, "enable_model_cpu_offload"):
                logger.info("Insufficient memory. Enabling model cpu offload")
                pipe.enable_model_cpu_offload()
                _log_memory_info(pipe, device)
                if _check_cuda_memory_sufficient(pipe, device):
                    logger.info("Sufficient memory after model cpu offload")
                    return

        # Final check after all optimizations
        if not _check_cuda_memory_sufficient(pipe, device):
            logger.warning("Memory may still be insufficient after all optimizations, but will try anyway")

        # Intentionally not calling pipe.to(device) here because sequential_cpu_offload
        # manages device placement automatically

    elif device.type == "mps":
        _log_memory_info(pipe, device)

        if _check_mps_memory_sufficient(pipe):
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
            return

        logger.warning("Insufficient memory on %s for Pipeline.", device)
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()

        # Final check after VAE slicing
        if not _check_mps_memory_sufficient(pipe):
            logger.warning("Memory may still be insufficient after optimizations, but will try anyway")

        # Intentionally not calling pipe.to(device) here when memory is insufficient
        # to avoid potential OOM errors
    return


def new_optimize_flux_pipeline(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
    pipe_params: FluxPipelineParameters | FluxFillPipelineParameters | DiptychFluxFillPipelineParameters,
) -> None:
    """Optimize pipeline performance and memory."""
    device = get_best_device()

    quantization_mode = pipe_params.get_quantization_mode()
    if quantization_mode != "none":
        _quantize_flux_pipeline(pipe, quantization_mode, device)

    if pipe_params.get_skip_memory_check():
        logger.info("Skipping memory checks. Moving pipeline to %s", device)
        pipe.to(device)
    else:
        _optimize_flux_pipeline(pipe, quantization_mode, device)

    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        if hasattr(torch.backends.cuda, "sdp_kernel"):
            torch.backends.cuda.sdp_kernel()
    except Exception:
        logger.debug("sdp_kernel not supported, continuing without")


@cache
def optimize_flux_pipeline(
    pipe: diffusers.FluxPipeline | diffusers.FluxImg2ImgPipeline | diffusers.AmusedPipeline,
    pipe_params: FluxPipelineParameters | FluxFillPipelineParameters | DiptychFluxFillPipelineParameters,
) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    logger.debug("Using legacy memory footprint optimization, ignoring pipe_params: %s", pipe_params)

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
        logger.info("Transferring model to MPS/GPU - may take minutes")
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
