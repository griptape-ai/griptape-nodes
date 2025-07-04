from collections.abc import Iterator
import torch
import diffusers
import logging
import time
import contextlib



from diffusers_nodes_library.common.utils.logging_utils import seconds_to_human_readable
from diffusers_nodes_library.pipelines.flux.flux_kontext_pipeline_memory_footprint import (
    FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES,
    _log_memory_info,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("diffusers_nodes_library")

@contextlib.contextmanager
def time_then_print(label: str) -> Iterator[None]:
    start = time.perf_counter()
    yield
    seconds = time.perf_counter() - start
    human_readable_duration = seconds_to_human_readable(seconds)
    print(f"{label} took {human_readable_duration}")


def benchmark_function(func, n=10, verbose=True):
    """
    Benchmark a function by running it `n` times and reporting timing statistics.

    Parameters:
        func (callable): The function to run and benchmark. Should take no arguments.
        n (int): Number of times to run the function.
        verbose (bool): Whether to print individual timings and summary.

    Returns:
        dict: A dictionary containing avg, p0 (min), p50 (median), and p100 (max) timings.
    """
    times = []
    for i in range(n):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        duration = end - start
        times.append(duration)
        if verbose:
            print(f"Inference step {i + 1}/{n} took {duration:.4f} seconds")

    sorted_times = sorted(times)
    avg_time = sum(times) / n
    p0_time = sorted_times[0]
    p50_time = sorted_times[n // 2]
    p100_time = sorted_times[-1]

    if verbose:
        print(f"\nAvg time: {avg_time:.4f} seconds")
        print(f"P0 time: {p0_time:.4f} seconds")
        print(f"P50 time: {p50_time:.4f} seconds")
        print(f"P100 time: {p100_time:.4f} seconds")

    return {
        "avg": avg_time,
        "p0": p0_time,
        "p50": p50_time,
        "p100": p100_time,
        "all": times
    }

def pipe_info_after_from_pretrained(**kwargs):
    print(kwargs or "NONE", "-" * 80)
    logger.info("Loading pipeline via from_pretrained with kwargs: %s", kwargs or "NONE")

    with time_then_print("from_pretrained"):
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            pretrained_model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            **kwargs,
        )
        print("\n")

    logger.info("pipe: dtype=%s, device=%s", pipe.dtype, pipe.device)
    logger.info("dtypes and device of pipeline components:")
    for name in FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES:
        component = getattr(pipe, name, None)
        if component is not None:
            logger.info(f"  - {name}: dtype={component.dtype}, device={component.device}")
    device = torch.device("cuda")
    _log_memory_info(pipe, device)
    print("  ")

    del pipe
    torch.cuda.empty_cache()


def load_model(
        from_pretrained_kwargs={},
        pipe_to_kwargs=None,
        torch__dynamo_config_cache_size_limit=None,
        pipe_transformer_compile_repeated_blocks_kwargs=None,
        enable_xformers_memory_efficient_attention=False,
):
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        pretrained_model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        **from_pretrained_kwargs,
    )
    if pipe_to_kwargs is not None:
        pipe.to(**pipe_to_kwargs)

    if torch__dynamo_config_cache_size_limit is not None:
        print(f"{torch._dynamo.config.cache_size_limit=}")
        torch._dynamo.config.cache_size_limit = torch__dynamo_config_cache_size_limit
        print(f"{torch._dynamo.config.cache_size_limit=}")

    # torch._inductor.config.conv_1x1_as_mm = True
    # torch._inductor.config.coordinate_descent_tuning = True
    # torch._inductor.config.epilogue_fusion = False
    # torch._inductor.config.coordinate_descent_check_all_directions = True
    
    # # This works, does help? shrug
    # logger.info("Enabling max-autotune for VAE")
    # pipe.vae = torch.compile(pipe.vae, mode="max-autotune", fullgraph=True)

    # # This works, first inference took 3.63 minutes, second took 1.67 seconds.
    # logger.info("Enabling max-autotune for transformer")
    # pipe.transformer = torch.compile(pipe.transformer, mode="max-autotune", fullgraph=True)

    if pipe_transformer_compile_repeated_blocks_kwargs is not None:
        pipe.transformer.compile_repeated_blocks(**pipe_transformer_compile_repeated_blocks_kwargs)

    if enable_xformers_memory_efficient_attention:
        pipe.enable_xformers_memory_efficient_attention()

    return pipe


def benchmark_inference(pipe):
    def infer():
        return pipe(prompt="A beautiful landscape", num_inference_steps=1, generator=torch.manual_seed(42)).images[0]

    with time_then_print("First Inference"):
        image = infer()
    image.save("test_image_1st_inference.png")

    benchmark_function(infer, n=10, verbose=True)


def main():
    # pipe_info_after_from_pretrained()
    # # Doc: https://github.com/huggingface/diffusers/issues/11432#issuecomment-2834765455
    # pipe_info_after_from_pretrained(torch_dtype="auto")  # auto derived dtype from model weights
    # pipe_info_after_from_pretrained(torch_dtype=torch.float64)
    # pipe_info_after_from_pretrained(torch_dtype=torch.float32)
    # pipe_info_after_from_pretrained(torch_dtype=torch.float16)
    # pipe_info_after_from_pretrained(torch_dtype=torch.bfloat16)
    # pipe_info_after_from_pretrained(torch_dtype=torch.float8_e4m3fn)
    # pipe_info_after_from_pretrained(torch_dtype=torch.float8_e5m2)

    # # First inference: ~30 seconds
    # # Second inference: ~0.4 seconds
    # pipe = load_model(
    #     from_pretrained_kwargs={"torch_dtype": torch.bfloat16},
    #     pipe_to_kwargs={"device": "cuda"},
    #     torch__dynamo_config_cache_size_limit=128,
    #     pipe_transformer_compile_repeated_blocks_kwargs={"fullgraph": True},
    # )
    # benchmark_inference(pipe)


    # First inference: ~1.23 seconds
    # Second inference: ~0.5 seconds
    pipe = load_model(
        from_pretrained_kwargs={"torch_dtype": torch.bfloat16},
        pipe_to_kwargs={"device": "cuda"},
    )
    benchmark_inference(pipe)

    pipe = load_model(
        from_pretrained_kwargs={"torch_dtype": torch.bfloat16},
        pipe_to_kwargs={"device": "cuda"},
        enable_xformers_memory_efficient_attention=True,
    )
    pipe.enable_xformers_memory_efficient_attention()
    benchmark_inference(pipe)

# xformers
# https://github.com/facebookresearch/xformers
# uv pip install install -U xformers --index-url https://download.pytorch.org/whl/cu128
# XXX xformers doesn't work on windows

# ONNX
# uv pip install onnx onnxruntime-gpu optimum[onnxruntime]
# uv run optimum-cli export onnx --model "black-forest-labs/FLUX.1-Kontext-dev" flux_kontext_onnx
if __name__ == "__main__":
    main()


