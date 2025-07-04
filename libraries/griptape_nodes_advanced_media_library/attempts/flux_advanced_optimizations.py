#!/usr/bin/env python3
"""
Advanced optimization tests for FluxKontext pipeline.
Tests compilation, memory optimizations, and inference parameters.
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

def benchmark_config(pipe, config_name: str, **kwargs) -> float:
    """Benchmark a specific configuration."""
    print(f"\n--- {config_name} ---")
    
    # Clear cache before test
    torch.cuda.empty_cache()
    gc.collect()
    
    # Warmup
    print("Warming up...")
    with torch.no_grad():
        _ = pipe(
            prompt="warmup",
            num_inference_steps=1,
            guidance_scale=1.0,
            height=512,
            width=512,
            **kwargs
        )
    
    torch.cuda.empty_cache()
    print_memory_stats()
    
    # Benchmark
    times = []
    for i in range(3):
        torch.cuda.synchronize()
        start_time = time.time()
        
        with torch.no_grad():
            _ = pipe(
                prompt="A beautiful mountain landscape with a lake",
                num_inference_steps=4,
                guidance_scale=1.0,
                height=1024,
                width=1024,
                **kwargs
            )
        
        torch.cuda.synchronize()
        end_time = time.time()
        
        inference_time = end_time - start_time
        times.append(inference_time)
        print(f"Run {i+1}: {inference_time:.2f}s")
        
        torch.cuda.empty_cache()
    
    avg_time = sum(times) / len(times)
    print(f"Average: {avg_time:.2f}s")
    return avg_time

def test_compilation_optimizations():
    """Test torch.compile optimizations."""
    print("=" * 60)
    print("TESTING TORCH.COMPILE OPTIMIZATIONS")
    print("=" * 60)
    
    # Load base pipeline
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")
    
    results = {}
    
    # Test baseline
    results["baseline"] = benchmark_config(pipe, "Baseline")
    
    # Test compiled transformer
    print("\nCompiling transformer...")
    pipe.transformer = torch.compile(pipe.transformer, mode="max-autotune")
    results["compiled_transformer"] = benchmark_config(pipe, "Compiled Transformer")
    
    # Test different compile modes
    compile_modes = ["default", "reduce-overhead", "max-autotune"]
    for mode in compile_modes:
        try:
            print(f"\nTesting compile mode: {mode}")
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
    
    return results

def test_memory_optimizations():
    """Test memory optimization techniques."""
    print("=" * 60)
    print("TESTING MEMORY OPTIMIZATIONS")
    print("=" * 60)
    
    results = {}
    
    # Test CPU offloading
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    )
    
    pipe.enable_model_cpu_offload()
    results["cpu_offload"] = benchmark_config(pipe, "CPU Offload")
    
    # Test sequential CPU offloading
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    )
    
    pipe.enable_sequential_cpu_offload()
    results["sequential_cpu_offload"] = benchmark_config(pipe, "Sequential CPU Offload")
    
    # Test attention slicing
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")
    
    try:
        pipe.enable_attention_slicing()
        results["attention_slicing"] = benchmark_config(pipe, "Attention Slicing")
    except Exception as e:
        print(f"Attention slicing not supported: {e}")
    
    return results

def test_precision_optimizations():
    """Test different precision settings."""
    print("=" * 60)
    print("TESTING PRECISION OPTIMIZATIONS")
    print("=" * 60)
    
    results = {}
    
    # Test different dtypes
    dtypes = [torch.float16, torch.bfloat16, torch.float32]
    
    for dtype in dtypes:
        try:
            pipe = diffusers.FluxKontextPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-Kontext-dev",
                local_files_only=True,
                torch_dtype=dtype,
            ).to("cuda")
            
            results[f"dtype_{dtype}"] = benchmark_config(pipe, f"Dtype: {dtype}")
            
        except Exception as e:
            print(f"Error with {dtype}: {e}")
    
    return results

def test_inference_parameters():
    """Test different inference parameters."""
    print("=" * 60)
    print("TESTING INFERENCE PARAMETERS")
    print("=" * 60)
    
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")
    
    results = {}
    
    # Test different step counts
    step_counts = [1, 2, 4, 8]
    for steps in step_counts:
        results[f"steps_{steps}"] = benchmark_config(
            pipe, f"{steps} Steps", num_inference_steps=steps
        )
    
    # Test different guidance scales
    guidance_scales = [0.0, 1.0, 3.5, 7.0]
    for scale in guidance_scales:
        results[f"guidance_{scale}"] = benchmark_config(
            pipe, f"Guidance {scale}", guidance_scale=scale
        )
    
    return results

def test_autocast_optimizations():
    """Test autocast optimizations."""
    print("=" * 60)
    print("TESTING AUTOCAST OPTIMIZATIONS")
    print("=" * 60)
    
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    ).to("cuda")
    
    results = {}
    
    # Test with autocast disabled
    results["no_autocast"] = benchmark_config(pipe, "No Autocast")
    
    # Test with different autocast dtypes
    autocast_dtypes = [torch.float16, torch.bfloat16]
    
    for dtype in autocast_dtypes:
        def autocast_wrapper(**kwargs):
            with torch.autocast(device_type='cuda', dtype=dtype):
                return pipe(**kwargs)
        
        # Temporarily replace the call method
        original_call = pipe.__call__
        pipe.__call__ = autocast_wrapper
        
        try:
            results[f"autocast_{dtype}"] = benchmark_config(pipe, f"Autocast {dtype}")
        finally:
            pipe.__call__ = original_call
    
    return results

def main():
    print("Advanced FluxKontext Optimization Tests")
    print("=" * 60)
    print(f"CUDA Device: {torch.cuda.get_device_name()}")
    print(f"PyTorch Version: {torch.__version__}")
    print(f"Diffusers Version: {diffusers.__version__}")
    
    all_results = {}
    
    # Run all test suites
    test_suites = [
        ("Inference Parameters", test_inference_parameters),
        ("Precision Optimizations", test_precision_optimizations),
        ("Memory Optimizations", test_memory_optimizations),
        ("Autocast Optimizations", test_autocast_optimizations),
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
        
        print(f"{'Configuration':<40} {'Time (s)':<10}")
        print("-" * 50)
        
        for config, time_val in sorted_results:
            print(f"{config:<40} {time_val:<10.2f}")
        
        print(f"\nFastest: {sorted_results[0][0]} - {sorted_results[0][1]:.2f}s")
        
        if len(sorted_results) > 1:
            baseline_time = all_results.get("baseline", sorted_results[-1][1])
            speedup = baseline_time / sorted_results[0][1]
            print(f"Speedup: {speedup:.2f}x")

if __name__ == "__main__":
    main()