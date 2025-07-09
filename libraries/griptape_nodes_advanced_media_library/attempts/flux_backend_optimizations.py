#!/usr/bin/env python3
"""
Backend optimization tests for FluxKontext pipeline.
Tests compilation, memory backends, and system optimizations only.
Does NOT change inference parameters.
"""

import torch
import diffusers
import time
import gc
import warnings
from typing import Dict, Any, List
import os

warnings.filterwarnings("ignore")


def print_memory_stats():
    """Print current GPU memory usage."""
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"GPU Memory - Allocated: {allocated:.2f}GB, Reserved: {reserved:.2f}GB")


def benchmark_config(pipe, config_name: str) -> float:
    """Benchmark a specific configuration with fixed inference parameters."""
    print(f"\n--- {config_name} ---")

    # Clear cache before test
    torch.cuda.empty_cache()
    gc.collect()

    # Fixed inference parameters
    FIXED_PARAMS = {
        "prompt": "A beautiful mountain landscape with a lake",
        "num_inference_steps": 4,
        "guidance_scale": 1.0,
        "height": 1024,
        "width": 1024,
    }

    # Warmup
    print("Warming up...")
    with torch.no_grad():
        _ = pipe(
            prompt="warmup",
            num_inference_steps=4,
            guidance_scale=1.0,
            height=1024,
            width=1024,
        )

    torch.cuda.empty_cache()
    print_memory_stats()

    # Benchmark
    times = []
    for i in range(3):
        torch.cuda.synchronize()
        start_time = time.time()

        with torch.no_grad():
            _ = pipe(**FIXED_PARAMS)

        torch.cuda.synchronize()
        end_time = time.time()

        inference_time = end_time - start_time
        times.append(inference_time)
        print(f"Run {i + 1}: {inference_time:.2f}s")

        torch.cuda.empty_cache()

    avg_time = sum(times) / len(times)
    print(f"Average: {avg_time:.2f}s")
    return avg_time


def test_compilation_optimizations():
    """Test torch.compile optimizations."""
    print("=" * 60)
    print("TESTING TORCH.COMPILE OPTIMIZATIONS")
    print("=" * 60)

    results = {}

    # Baseline
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")

    results["baseline"] = benchmark_config(pipe, "Baseline")

    # Test different compile modes
    compile_modes = ["default", "reduce-overhead", "max-autotune"]

    for mode in compile_modes:
        try:
            print(f"\nCompiling transformer with mode: {mode}")
            # Reload pipeline to avoid compilation conflicts
            pipe = diffusers.FluxKontextPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-Kontext-dev",
                local_files_only=True,
                torch_dtype=torch.bfloat16,
            ).to("cuda")

            pipe.transformer = torch.compile(pipe.transformer, mode=mode)
            results[f"compiled_{mode}"] = benchmark_config(pipe, f"Compiled ({mode})")

        except Exception as e:
            print(f"Error with {mode}: {e}")

    # Test compiling VAE
    try:
        print("\nCompiling VAE...")
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        ).to("cuda")

        pipe.vae = torch.compile(pipe.vae, mode="max-autotune")
        results["compiled_vae"] = benchmark_config(pipe, "Compiled VAE")

    except Exception as e:
        print(f"Error compiling VAE: {e}")

    # Test compiling both
    try:
        print("\nCompiling both transformer and VAE...")
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        ).to("cuda")

        pipe.transformer = torch.compile(pipe.transformer, mode="max-autotune")
        pipe.vae = torch.compile(pipe.vae, mode="max-autotune")
        results["compiled_both"] = benchmark_config(pipe, "Compiled Both")

    except Exception as e:
        print(f"Error compiling both: {e}")

    return results


def test_memory_backends():
    """Test different memory management backends."""
    print("=" * 60)
    print("TESTING MEMORY BACKENDS")
    print("=" * 60)

    results = {}

    # Test CPU offloading
    try:
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        )
        pipe.enable_model_cpu_offload()
        results["cpu_offload"] = benchmark_config(pipe, "CPU Offload")
    except Exception as e:
        print(f"CPU offload error: {e}")

    # Test sequential CPU offloading
    try:
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        )
        pipe.enable_sequential_cpu_offload()
        results["sequential_cpu_offload"] = benchmark_config(pipe, "Sequential CPU Offload")
    except Exception as e:
        print(f"Sequential CPU offload error: {e}")

    # Test attention slicing
    try:
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        ).to("cuda")

        pipe.enable_attention_slicing()
        results["attention_slicing"] = benchmark_config(pipe, "Attention Slicing")
    except Exception as e:
        print(f"Attention slicing error: {e}")

    return results


def test_precision_backends():
    """Test different precision backends."""
    print("=" * 60)
    print("TESTING PRECISION BACKENDS")
    print("=" * 60)

    results = {}

    # Test different dtypes
    dtypes = [torch.float16, torch.bfloat16]

    for dtype in dtypes:
        try:
            pipe = diffusers.FluxKontextPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-Kontext-dev",
                local_files_only=True,
                torch_dtype=dtype,
            ).to("cuda")

            results[f"dtype_{str(dtype).split('.')[-1]}"] = benchmark_config(pipe, f"Dtype: {dtype}")

        except Exception as e:
            print(f"Error with {dtype}: {e}")

    return results


def test_autocast_backends():
    """Test different autocast backends."""
    print("=" * 60)
    print("TESTING AUTOCAST BACKENDS")
    print("=" * 60)

    results = {}

    # Base pipeline
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")

    # Test different autocast configurations
    autocast_configs = [
        {"enabled": False, "name": "no_autocast"},
        {"enabled": True, "dtype": torch.float16, "name": "autocast_fp16"},
        {"enabled": True, "dtype": torch.bfloat16, "name": "autocast_bf16"},
    ]

    for config in autocast_configs:
        try:

            def create_wrapper(autocast_enabled, autocast_dtype=None):
                def wrapper(**kwargs):
                    if autocast_enabled:
                        with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                            return pipe.__class__.__call__(pipe, **kwargs)
                    else:
                        return pipe.__class__.__call__(pipe, **kwargs)

                return wrapper

            # Temporarily replace the call method
            original_call = pipe.__call__
            pipe.__call__ = create_wrapper(config["enabled"], config.get("dtype"))

            results[config["name"]] = benchmark_config(pipe, config["name"].replace("_", " ").title())

        except Exception as e:
            print(f"Error with {config['name']}: {e}")
        finally:
            pipe.__call__ = original_call

    return results


def test_cuda_graph_optimization():
    """Test CUDA graph capture optimization."""
    print("=" * 60)
    print("TESTING CUDA GRAPH OPTIMIZATION")
    print("=" * 60)

    results = {}

    try:
        pipe = diffusers.FluxKontextPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        ).to("cuda")

        # Test with CUDA graphs (if supported)
        with torch.cuda.graph_capture_mode():
            results["cuda_graph"] = benchmark_config(pipe, "CUDA Graph")

    except Exception as e:
        print(f"CUDA graph not supported or error: {e}")

    return results


def test_environment_optimizations():
    """Test environment variable optimizations."""
    print("=" * 60)
    print("TESTING ENVIRONMENT OPTIMIZATIONS")
    print("=" * 60)

    results = {}

    # Test with different environment variables
    env_configs = [
        {"name": "default", "vars": {}},
        {"name": "cudnn_benchmark", "vars": {"CUDNN_BENCHMARK": "1"}},
        {"name": "pytorch_cuda_alloc", "vars": {"PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512"}},
        {"name": "omp_threads", "vars": {"OMP_NUM_THREADS": "1"}},
    ]

    for config in env_configs:
        try:
            # Set environment variables
            for key, value in config["vars"].items():
                os.environ[key] = value

            # Apply torch settings
            if "cudnn_benchmark" in config["name"]:
                torch.backends.cudnn.benchmark = True

            pipe = diffusers.FluxKontextPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-Kontext-dev",
                local_files_only=True,
                torch_dtype=torch.bfloat16,
            ).to("cuda")

            results[config["name"]] = benchmark_config(pipe, config["name"].replace("_", " ").title())

        except Exception as e:
            print(f"Error with {config['name']}: {e}")
        finally:
            # Reset environment
            for key in config["vars"]:
                if key in os.environ:
                    del os.environ[key]
            torch.backends.cudnn.benchmark = False

    return results


def main():
    print("Backend Optimization Tests for FluxKontext")
    print("=" * 60)
    print(f"CUDA Device: {torch.cuda.get_device_name()}")
    print(f"PyTorch Version: {torch.__version__}")
    print(f"Diffusers Version: {diffusers.__version__}")
    print("\nFixed inference parameters:")
    print("- Steps: 4")
    print("- Guidance: 1.0")
    print("- Size: 1024x1024")

    all_results = {}

    # Run test suites
    test_suites = [
        ("Precision Backends", test_precision_backends),
        ("Memory Backends", test_memory_backends),
        ("Autocast Backends", test_autocast_backends),
        ("Environment Optimizations", test_environment_optimizations),
        ("Compilation Optimizations", test_compilation_optimizations),
    ]

    for suite_name, test_func in test_suites:
        try:
            print(f"\n\nRunning {suite_name}...")
            results = test_func()
            all_results.update(results)
        except Exception as e:
            print(f"Error in {suite_name}: {e}")

    # Print final summary
    print("\n" + "=" * 80)
    print("FINAL RESULTS SUMMARY")
    print("=" * 80)

    if all_results:
        sorted_results = sorted(all_results.items(), key=lambda x: x[1])

        print(f"{'Configuration':<40} {'Time (s)':<10} {'Speedup':<10}")
        print("-" * 60)

        baseline_time = all_results.get("baseline", sorted_results[-1][1])

        for config, time_val in sorted_results:
            speedup = baseline_time / time_val
            print(f"{config:<40} {time_val:<10.2f} {speedup:<10.2f}x")

        print(f"\nFastest: {sorted_results[0][0]} - {sorted_results[0][1]:.2f}s")
        print(f"Best speedup: {baseline_time / sorted_results[0][1]:.2f}x")


if __name__ == "__main__":
    main()
