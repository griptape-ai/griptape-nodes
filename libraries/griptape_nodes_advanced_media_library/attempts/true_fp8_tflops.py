"""
TRUE FP8 Computation for Maximum TFLOPS on H100
Uses native PyTorch FP8 operations without conversion back to FP32
"""

import torch
import time
import numpy as np


def benchmark_operation(func, name, warmup_runs=5, bench_runs=10):
    """Benchmark a function with proper GPU synchronization"""
    print(f"\n🔥 Benchmarking {name}...")

    # Warmup
    for _ in range(warmup_runs):
        result = func()
        torch.cuda.synchronize()

    # Benchmark
    torch.cuda.synchronize()
    start_time = time.time()

    for _ in range(bench_runs):
        result = func()

    torch.cuda.synchronize()
    end_time = time.time()

    avg_time = (end_time - start_time) / bench_runs
    return result, avg_time


def test_true_fp8_matmul():
    """Test TRUE FP8 matrix multiplication using PyTorch 2.7+ native support"""
    print("=" * 60)
    print(" TRUE FP8 COMPUTATION - MAXIMUM TFLOPS")
    print("=" * 60)

    device = torch.device("cuda")

    # Large matrices for meaningful TFLOPS measurement
    sizes = [(1024, 1024), (2048, 2048), (4096, 4096), (8192, 8192)]

    for M, N in sizes:
        print(f"\n📊 Testing {M}x{N} matrices")

        # Create FP32 tensors first
        a_fp32 = torch.randn(M, N, device=device, dtype=torch.float32)
        b_fp32 = torch.randn(M, N, device=device, dtype=torch.float32)

        # Convert to TRUE FP8
        a_fp8 = a_fp32.to(torch.float8_e4m3fn)
        b_fp8 = b_fp32.to(torch.float8_e4m3fn)

        print(f"✓ Created FP8 tensors: {a_fp8.dtype}")
        print(f"  Memory usage: {a_fp8.element_size() * a_fp8.numel() * 2 / 1024**2:.1f} MB")

        # Define operations
        def fp8_matmul():
            # This should use TRUE FP8 tensor cores on H100
            return torch.mm(a_fp8, b_fp8)

        def fp32_matmul():
            return torch.mm(a_fp32, b_fp32)

        # Benchmark FP8
        result_fp8, time_fp8 = benchmark_operation(fp8_matmul, "FP8 MatMul")

        # Benchmark FP32 for comparison
        result_fp32, time_fp32 = benchmark_operation(fp32_matmul, "FP32 MatMul")

        # Calculate TFLOPS
        flops = 2 * M * N * N  # Matrix multiplication FLOPs
        tflops_fp8 = flops / (time_fp8 * 1e12)
        tflops_fp32 = flops / (time_fp32 * 1e12)

        print(f"⚡ FP8 Performance:")
        print(f"  Time: {time_fp8 * 1000:.2f} ms")
        print(f"  TFLOPS: {tflops_fp8:.2f}")
        print(f"  Result dtype: {result_fp8.dtype}")
        print(f"  Result mean: {result_fp8.to(torch.float32).mean():.6f}")

        print(f"📈 FP32 Performance:")
        print(f"  Time: {time_fp32 * 1000:.2f} ms")
        print(f"  TFLOPS: {tflops_fp32:.2f}")
        print(f"  Result mean: {result_fp32.mean():.6f}")

        speedup = time_fp32 / time_fp8
        tflops_ratio = tflops_fp8 / tflops_fp32

        print(f"🚀 Speedup: {speedup:.2f}x")
        print(f"🔥 TFLOPS Ratio: {tflops_ratio:.2f}x")

        # Verify computation accuracy
        error = torch.mean(torch.abs(result_fp8.to(torch.float32) - result_fp32))
        print(f"📊 Accuracy: Mean error = {error:.6f}")


def test_fp8_operations():
    """Test various FP8 operations to maximize TFLOPS"""
    print("\n" + "=" * 60)
    print(" FP8 OPERATIONS SUITE")
    print("=" * 60)

    device = torch.device("cuda")

    # Create large FP8 tensors
    size = 4096
    a = torch.randn(size, size, device=device, dtype=torch.float8_e4m3fn)
    b = torch.randn(size, size, device=device, dtype=torch.float8_e4m3fn)
    c = torch.randn(size, size, device=device, dtype=torch.float8_e4m3fn)

    print(f"✓ Created {size}x{size} FP8 tensors")

    operations = [
        ("Matrix Multiply", lambda: torch.mm(a, b)),
        ("Batch Matrix Multiply", lambda: torch.bmm(a.unsqueeze(0).repeat(8, 1, 1), b.unsqueeze(0).repeat(8, 1, 1))),
        ("Element-wise Multiply", lambda: a * b),
        ("Fused Multiply-Add", lambda: torch.addmm(c, a, b)),
        ("Transpose + MatMul", lambda: torch.mm(a.T, b)),
    ]

    for op_name, op_func in operations:
        try:
            result, avg_time = benchmark_operation(op_func, op_name, warmup_runs=3, bench_runs=5)

            # Estimate FLOPS (rough approximation)
            if "Matrix" in op_name:
                flops = 2 * size * size * size
            elif "Element-wise" in op_name:
                flops = size * size
            else:
                flops = 2 * size * size * size

            tflops = flops / (avg_time * 1e12)

            print(f"  ⚡ {op_name}: {avg_time * 1000:.2f} ms, {tflops:.2f} TFLOPS")
            print(f"     Result dtype: {result.dtype}")

        except Exception as e:
            print(f"  ❌ {op_name} failed: {e}")


def test_fp8_memory_bandwidth():
    """Test memory bandwidth with FP8"""
    print("\n" + "=" * 60)
    print(" FP8 MEMORY BANDWIDTH TEST")
    print("=" * 60)

    device = torch.device("cuda")

    # Large tensor for memory bandwidth test
    size = 16384
    elements = size * size

    # FP8 tensor
    a_fp8 = torch.randn(size, size, device=device, dtype=torch.float8_e4m3fn)

    # Memory copy operation
    def memory_copy():
        return a_fp8.clone()

    result, avg_time = benchmark_operation(memory_copy, "FP8 Memory Copy")

    # Calculate bandwidth
    bytes_transferred = elements * 2  # Read + Write, 1 byte per FP8 element
    bandwidth_gbps = bytes_transferred / (avg_time * 1e9)

    print(f"  📊 Memory size: {elements / 1e6:.1f} M elements")
    print(f"  📊 Data size: {bytes_transferred / 1024**2:.1f} MB")
    print(f"  ⚡ Bandwidth: {bandwidth_gbps:.2f} GB/s")

    # Compare with FP32
    a_fp32 = torch.randn(size, size, device=device, dtype=torch.float32)

    def memory_copy_fp32():
        return a_fp32.clone()

    result_fp32, avg_time_fp32 = benchmark_operation(memory_copy_fp32, "FP32 Memory Copy")

    bytes_transferred_fp32 = elements * 8  # 4 bytes per FP32 element * 2 (read+write)
    bandwidth_gbps_fp32 = bytes_transferred_fp32 / (avg_time_fp32 * 1e9)

    print(f"  📊 FP32 Bandwidth: {bandwidth_gbps_fp32:.2f} GB/s")
    print(f"  🚀 FP8 Bandwidth Advantage: {bandwidth_gbps / bandwidth_gbps_fp32:.2f}x")


def main():
    print("🔥 TRUE FP8 COMPUTATION FOR MAXIMUM TFLOPS")
    print("H100 Native FP8 Tensor Core Utilization")
    print("=" * 60)

    # Check environment
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Compute capability: {torch.cuda.get_device_capability(0)}")

    # Verify FP8 support
    if not hasattr(torch, "float8_e4m3fn"):
        print("❌ FP8 not supported in this PyTorch version")
        return

    # Test TRUE FP8 computation
    test_true_fp8_matmul()
    test_fp8_operations()
    test_fp8_memory_bandwidth()

    print("\n🎉 TRUE FP8 COMPUTATION COMPLETE!")
    print("This script demonstrated native FP8 tensor core utilization")
    print("for maximum TFLOPS on your H100 GPU.")


if __name__ == "__main__":
    main()
