import torch
import time
from fp8_ops import FP8ElementwiseOps, FP8Activations, FP8Normalization


def benchmark_elementwise_ops(device="cuda", num_runs=100, tensor_size=(1024, 1024)):
    """Benchmark FP8 element-wise operations vs standard implementations."""

    print(f"Benchmarking FP8 element-wise operations on {device}")
    print(f"Tensor size: {tensor_size}, Runs: {num_runs}")
    print("=" * 60)

    # Create test tensors
    a = torch.randn(tensor_size, dtype=torch.bfloat16, device=device)
    b = torch.randn(tensor_size, dtype=torch.bfloat16, device=device)
    c = torch.randn(tensor_size, dtype=torch.bfloat16, device=device)

    # Warm up GPU
    for _ in range(10):
        _ = a + b
        _ = a * b

    torch.cuda.synchronize()

    results = {}

    # Benchmark Addition
    print("Testing Addition (a + b):")

    # Standard addition
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = a + b
    torch.cuda.synchronize()
    standard_add_time = time.time() - start

    # FP8 addition
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8ElementwiseOps.add(a, b)
    torch.cuda.synchronize()
    fp8_add_time = time.time() - start

    add_speedup = standard_add_time / fp8_add_time
    results["add"] = {"standard": standard_add_time, "fp8": fp8_add_time, "speedup": add_speedup}
    print(f"  Standard: {standard_add_time:.4f}s, FP8: {fp8_add_time:.4f}s, Speedup: {add_speedup:.2f}x")

    # Benchmark Multiplication
    print("Testing Multiplication (a * b):")

    # Standard multiplication
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = a * b
    torch.cuda.synchronize()
    standard_mul_time = time.time() - start

    # FP8 multiplication
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8ElementwiseOps.mul(a, b)
    torch.cuda.synchronize()
    fp8_mul_time = time.time() - start

    mul_speedup = standard_mul_time / fp8_mul_time
    results["mul"] = {"standard": standard_mul_time, "fp8": fp8_mul_time, "speedup": mul_speedup}
    print(f"  Standard: {standard_mul_time:.4f}s, FP8: {fp8_mul_time:.4f}s, Speedup: {mul_speedup:.2f}x")

    # Benchmark Fused Multiply-Add
    print("Testing Fused Multiply-Add (a * b + c):")

    # Standard fused multiply-add
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = a * b + c
    torch.cuda.synchronize()
    standard_fma_time = time.time() - start

    # FP8 fused multiply-add
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8ElementwiseOps.fused_mul_add(a, b, c)
    torch.cuda.synchronize()
    fp8_fma_time = time.time() - start

    fma_speedup = standard_fma_time / fp8_fma_time
    results["fma"] = {"standard": standard_fma_time, "fp8": fp8_fma_time, "speedup": fma_speedup}
    print(f"  Standard: {standard_fma_time:.4f}s, FP8: {fp8_fma_time:.4f}s, Speedup: {fma_speedup:.2f}x")

    # Benchmark GELU activation
    print("Testing GELU Activation:")

    # Standard GELU
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = torch.nn.functional.gelu(a, approximate="tanh")
    torch.cuda.synchronize()
    standard_gelu_time = time.time() - start

    # FP8 GELU
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8Activations.gelu(a, approximate="tanh")
    torch.cuda.synchronize()
    fp8_gelu_time = time.time() - start

    gelu_speedup = standard_gelu_time / fp8_gelu_time
    results["gelu"] = {"standard": standard_gelu_time, "fp8": fp8_gelu_time, "speedup": gelu_speedup}
    print(f"  Standard: {standard_gelu_time:.4f}s, FP8: {fp8_gelu_time:.4f}s, Speedup: {gelu_speedup:.2f}x")

    # Benchmark SiLU activation
    print("Testing SiLU Activation:")

    # Standard SiLU
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = torch.nn.functional.silu(a)
    torch.cuda.synchronize()
    standard_silu_time = time.time() - start

    # FP8 SiLU
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8Activations.silu(a)
    torch.cuda.synchronize()
    fp8_silu_time = time.time() - start

    silu_speedup = standard_silu_time / fp8_silu_time
    results["silu"] = {"standard": standard_silu_time, "fp8": fp8_silu_time, "speedup": silu_speedup}
    print(f"  Standard: {standard_silu_time:.4f}s, FP8: {fp8_silu_time:.4f}s, Speedup: {silu_speedup:.2f}x")

    # Benchmark Layer Normalization
    print("Testing Layer Normalization:")

    layer_norm_shape = tensor_size[-1]
    weight = torch.randn(layer_norm_shape, dtype=torch.bfloat16, device=device)
    bias = torch.randn(layer_norm_shape, dtype=torch.bfloat16, device=device)

    # Standard LayerNorm
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = torch.nn.functional.layer_norm(a, (layer_norm_shape,), weight, bias)
    torch.cuda.synchronize()
    standard_ln_time = time.time() - start

    # FP8 LayerNorm
    torch.cuda.synchronize()
    start = time.time()
    for _ in range(num_runs):
        result = FP8Normalization.layer_norm(a, (layer_norm_shape,), weight, bias)
    torch.cuda.synchronize()
    fp8_ln_time = time.time() - start

    ln_speedup = standard_ln_time / fp8_ln_time
    results["layer_norm"] = {"standard": standard_ln_time, "fp8": fp8_ln_time, "speedup": ln_speedup}
    print(f"  Standard: {standard_ln_time:.4f}s, FP8: {fp8_ln_time:.4f}s, Speedup: {ln_speedup:.2f}x")

    print("=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    print(f"{'Operation':<20} {'Standard (s)':<12} {'FP8 (s)':<12} {'Speedup':<10}")
    print("-" * 60)

    for op_name, op_results in results.items():
        print(
            f"{op_name:<20} {op_results['standard']:<12.4f} {op_results['fp8']:<12.4f} {op_results['speedup']:<10.2f}x"
        )

    return results


def benchmark_memory_usage(device="cuda", tensor_size=(1024, 1024)):
    """Benchmark memory usage of FP8 vs standard operations."""

    print(f"\nMemory Usage Comparison:")
    print("=" * 40)

    # Create test tensors
    a = torch.randn(tensor_size, dtype=torch.bfloat16, device=device)
    b = torch.randn(tensor_size, dtype=torch.bfloat16, device=device)

    # Measure memory for standard operations
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    result_std = a + b
    std_memory = torch.cuda.max_memory_allocated()

    # Measure memory for FP8 operations
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    result_fp8 = FP8ElementwiseOps.add(a, b)
    fp8_memory = torch.cuda.max_memory_allocated()

    print(f"Standard operation memory: {std_memory / 1024**2:.2f} MB")
    print(f"FP8 operation memory: {fp8_memory / 1024**2:.2f} MB")
    print(f"Memory reduction: {(std_memory - fp8_memory) / std_memory * 100:.1f}%")

    # Verify results are similar
    diff = torch.abs(result_std - result_fp8).max()
    print(f"Max difference between results: {diff:.6f}")


if __name__ == "__main__":
    if torch.cuda.is_available():
        # Test different tensor sizes
        sizes = [
            (512, 512),
            (1024, 1024),
            (2048, 2048),
            (4096, 1024),  # Common in transformers
        ]

        for size in sizes:
            print(f"\n{'=' * 80}")
            print(f"TENSOR SIZE: {size}")
            print(f"{'=' * 80}")

            results = benchmark_elementwise_ops(tensor_size=size)
            benchmark_memory_usage(tensor_size=size)

            # Check if any operation showed significant speedup
            significant_speedups = [op for op, res in results.items() if res["speedup"] > 1.1]
            if significant_speedups:
                print(f"\nOperations with >10% speedup: {significant_speedups}")
    else:
        print("CUDA not available. Skipping benchmarks.")
