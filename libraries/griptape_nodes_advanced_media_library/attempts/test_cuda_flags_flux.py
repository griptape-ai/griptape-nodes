#!/usr/bin/env python3
"""
Test script for CUDA optimization flags on FluxKontext pipeline.
Tests various PyTorch CUDA backend flags to measure inference speed improvements.
"""

import torch
import diffusers
import time
import gc
from contextlib import contextmanager
from typing import Dict, Any, List, Tuple
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

def print_cuda_info():
    """Print CUDA device information."""
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA Device: {torch.cuda.get_device_name()}")
        print(f"CUDA Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print("-" * 60)

@contextmanager
def cuda_flags_context(flags: Dict[str, Any]):
    """Context manager to temporarily set CUDA flags."""
    # Store original values
    original_values = {}
    
    # Set new values
    for flag_path, value in flags.items():
        parts = flag_path.split('.')
        obj = torch.backends.cuda
        
        # Navigate to the parent object
        for part in parts[:-1]:
            obj = getattr(obj, part)
        
        # Store original value
        original_values[flag_path] = getattr(obj, parts[-1])
        
        # Set new value
        setattr(obj, parts[-1], value)
        print(f"Set {flag_path} = {value}")
    
    try:
        yield
    finally:
        # Restore original values
        for flag_path, original_value in original_values.items():
            parts = flag_path.split('.')
            obj = torch.backends.cuda
            
            for part in parts[:-1]:
                obj = getattr(obj, part)
            
            setattr(obj, parts[-1], original_value)

def load_pipeline():
    """Load the FluxKontext pipeline."""
    print("Loading FluxKontext pipeline...")
    pipe = diffusers.FluxKontextPipeline.from_pretrained(
        pretrained_model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
        local_files_only=True,
        torch_dtype=torch.bfloat16,
    )
    pipe = pipe.to("cuda")
    return pipe

def benchmark_inference(pipe, test_name: str, num_runs: int = 3) -> List[float]:
    """Benchmark inference time for multiple runs."""
    print(f"\nTesting: {test_name}")
    
    # Warm up
    print("Warming up...")
    with torch.no_grad():
        _ = pipe(
            prompt="A cat sitting on a table",
            num_inference_steps=4,
            guidance_scale=1.0,
            height=512,
            width=512,
        )
    
    # Clear cache
    torch.cuda.empty_cache()
    gc.collect()
    
    # Benchmark runs
    times = []
    for i in range(num_runs):
        print(f"Run {i+1}/{num_runs}...")
        
        torch.cuda.synchronize()
        start_time = time.time()
        
        with torch.no_grad():
            _ = pipe(
                prompt="A beautiful landscape with mountains and lakes",
                num_inference_steps=4,
                guidance_scale=1.0,
                height=512,
                width=512,
            )
        
        torch.cuda.synchronize()
        end_time = time.time()
        
        inference_time = end_time - start_time
        times.append(inference_time)
        print(f"  Time: {inference_time:.2f}s")
        
        # Clear cache between runs
        torch.cuda.empty_cache()
        gc.collect()
    
    avg_time = sum(times) / len(times)
    print(f"Average time: {avg_time:.2f}s")
    return times

def main():
    print("CUDA Optimization Flags Test for FluxKontext Pipeline")
    print("=" * 60)
    
    print_cuda_info()
    
    # Load pipeline once
    pipe = load_pipeline()
    
    # Test configurations
    test_configs = [
        {
            "name": "Baseline (Default Settings)",
            "flags": {}
        },
        {
            "name": "TF32 Enabled",
            "flags": {
                "matmul.allow_tf32": True
            }
        },
        {
            "name": "Flash Attention",
            "flags": {
                "enable_flash_sdp": True
            }
        },
        {
            "name": "Memory Efficient Attention",
            "flags": {
                "enable_mem_efficient_sdp": True
            }
        },
        {
            "name": "cuDNN Attention",
            "flags": {
                "enable_cudnn_sdp": True
            }
        },
        {
            "name": "All Attention Optimizations",
            "flags": {
                "enable_flash_sdp": True,
                "enable_mem_efficient_sdp": True,
                "enable_cudnn_sdp": True
            }
        },
        {
            "name": "Reduced Precision + TF32",
            "flags": {
                "matmul.allow_tf32": True,
                "matmul.allow_fp16_reduced_precision_reduction": True,
                "matmul.allow_bf16_reduced_precision_reduction": True
            }
        },
        {
            "name": "All Optimizations",
            "flags": {
                "matmul.allow_tf32": True,
                "matmul.allow_fp16_reduced_precision_reduction": True,
                "matmul.allow_bf16_reduced_precision_reduction": True,
                "enable_flash_sdp": True,
                "enable_mem_efficient_sdp": True,
                "enable_cudnn_sdp": True
            }
        }
    ]
    
    # Store results
    results = []
    
    # Run tests
    for config in test_configs:
        try:
            if config["flags"]:
                with cuda_flags_context(config["flags"]):
                    times = benchmark_inference(pipe, config["name"])
            else:
                times = benchmark_inference(pipe, config["name"])
            
            results.append({
                "name": config["name"],
                "times": times,
                "avg_time": sum(times) / len(times)
            })
            
        except Exception as e:
            print(f"Error testing {config['name']}: {str(e)}")
            results.append({
                "name": config["name"],
                "times": [],
                "avg_time": float('inf'),
                "error": str(e)
            })
    
    # Print summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    # Sort by average time
    valid_results = [r for r in results if r["avg_time"] != float('inf')]
    valid_results.sort(key=lambda x: x["avg_time"])
    
    if valid_results:
        baseline_time = next((r["avg_time"] for r in results if r["name"] == "Baseline (Default Settings)"), None)
        
        print(f"{'Configuration':<30} {'Avg Time (s)':<12} {'Speedup':<10}")
        print("-" * 60)
        
        for result in valid_results:
            speedup = f"{baseline_time/result['avg_time']:.2f}x" if baseline_time else "N/A"
            print(f"{result['name']:<30} {result['avg_time']:<12.2f} {speedup:<10}")
    
    # Print errors
    error_results = [r for r in results if r["avg_time"] == float('inf')]
    if error_results:
        print("\nERRORS:")
        for result in error_results:
            print(f"  {result['name']}: {result.get('error', 'Unknown error')}")
    
    print(f"\nBest configuration: {valid_results[0]['name']}")
    print(f"Best time: {valid_results[0]['avg_time']:.2f}s")
    
    if baseline_time:
        print(f"Speedup over baseline: {baseline_time/valid_results[0]['avg_time']:.2f}x")

if __name__ == "__main__":
    main()