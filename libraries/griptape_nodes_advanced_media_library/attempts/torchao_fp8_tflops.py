"""
Native FP8 Computation using TorchAO for Maximum TFLOPS
Uses PyTorch's official FP8 implementation via TorchAO
"""

import torch
import time
import sys


def check_torchao():
    """Check if TorchAO is available and install if needed"""
    try:
        import torchao

        print(f"✓ TorchAO version: {torchao.__version__}")
        return True
    except ImportError:
        print("❌ TorchAO not found. Installing...")
        try:
            import subprocess

            subprocess.check_call([sys.executable, "-m", "pip", "install", "torchao"])
            import torchao

            print(f"✓ TorchAO installed: {torchao.__version__}")
            return True
        except Exception as e:
            print(f"❌ Failed to install TorchAO: {e}")
            return False


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


def test_torchao_fp8():
    """Test TorchAO FP8 quantization and computation"""
    print("=" * 60)
    print(" TORCHAO FP8 NATIVE COMPUTATION")
    print("=" * 60)

    try:
        from torchao.quantization import quantize_, float8_weight_only
        from torchao.quantization.quant_api import _replace_with_custom_fn_if_matches_filter

        device = torch.device("cuda")

        # Create a model to quantize
        class SimpleModel(torch.nn.Module):
            def __init__(self, size):
                super().__init__()
                self.linear1 = torch.nn.Linear(size, size)
                self.linear2 = torch.nn.Linear(size, size)
                self.linear3 = torch.nn.Linear(size, size)

            def forward(self, x):
                x = self.linear1(x)
                x = torch.relu(x)
                x = self.linear2(x)
                x = torch.relu(x)
                x = self.linear3(x)
                return x

        sizes = [1024, 2048, 4096]

        for size in sizes:
            print(f"\n📊 Testing {size}x{size} model")

            # Create model
            model = SimpleModel(size).to(device)
            input_tensor = torch.randn(32, size, device=device)

            # Quantize to FP8
            print("🔧 Quantizing model to FP8...")
            quantized_model = quantize_(model, float8_weight_only())

            # Benchmark original model
            def fp32_forward():
                return model(input_tensor)

            def fp8_forward():
                return quantized_model(input_tensor)

            # Warmup and benchmark
            print("⚡ Benchmarking FP32 model...")
            result_fp32, time_fp32 = benchmark_operation(fp32_forward, "FP32 Model")

            print("⚡ Benchmarking FP8 model...")
            result_fp8, time_fp8 = benchmark_operation(fp8_forward, "FP8 Model")

            # Calculate performance metrics
            # Rough FLOPS estimate for 3 linear layers
            flops = 3 * 32 * size * size * 2  # batch_size * input_size * output_size * 2 (mul+add)
            tflops_fp32 = flops / (time_fp32 * 1e12)
            tflops_fp8 = flops / (time_fp8 * 1e12)

            speedup = time_fp32 / time_fp8

            print(f"📈 Results for {size}x{size}:")
            print(f"  FP32: {time_fp32 * 1000:.2f} ms, {tflops_fp32:.2f} TFLOPS")
            print(f"  FP8:  {time_fp8 * 1000:.2f} ms, {tflops_fp8:.2f} TFLOPS")
            print(f"  🚀 Speedup: {speedup:.2f}x")
            print(f"  🔥 TFLOPS Ratio: {tflops_fp8 / tflops_fp32:.2f}x")

            # Check accuracy
            error = torch.mean(torch.abs(result_fp32 - result_fp8))
            print(f"  📊 Mean Error: {error:.6f}")

    except ImportError as e:
        print(f"❌ TorchAO import error: {e}")
        return False
    except Exception as e:
        print(f"❌ TorchAO FP8 test failed: {e}")
        return False

    return True


def test_torchao_fp8_advanced():
    """Test advanced TorchAO FP8 features"""
    print("\n" + "=" * 60)
    print(" TORCHAO FP8 ADVANCED FEATURES")
    print("=" * 60)

    try:
        from torchao.quantization import quantize_, float8_dynamic_activation_float8_weight

        device = torch.device("cuda")

        # Create larger model for better FP8 utilization
        class LargeModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = torch.nn.Sequential(
                    torch.nn.Linear(4096, 4096),
                    torch.nn.ReLU(),
                    torch.nn.Linear(4096, 4096),
                    torch.nn.ReLU(),
                    torch.nn.Linear(4096, 4096),
                    torch.nn.ReLU(),
                    torch.nn.Linear(4096, 4096),
                    torch.nn.ReLU(),
                    torch.nn.Linear(4096, 1024),
                )

            def forward(self, x):
                return self.layers(x)

        print("🔧 Creating large model...")
        model = LargeModel().to(device)
        input_tensor = torch.randn(64, 4096, device=device)

        # Test different FP8 quantization schemes
        quantization_schemes = [
            ("FP8 Weight Only", float8_weight_only()),
            ("FP8 Dynamic Act + Weight", float8_dynamic_activation_float8_weight()),
        ]

        # Baseline FP32
        def fp32_forward():
            return model(input_tensor)

        result_fp32, time_fp32 = benchmark_operation(fp32_forward, "FP32 Baseline")

        # Test each quantization scheme
        for scheme_name, quantization_config in quantization_schemes:
            try:
                print(f"\n🔧 Testing {scheme_name}...")
                quantized_model = quantize_(model, quantization_config)

                def quantized_forward():
                    return quantized_model(input_tensor)

                result_quant, time_quant = benchmark_operation(quantized_forward, scheme_name)

                speedup = time_fp32 / time_quant

                # Rough FLOPS calculation
                flops = 64 * (4096 * 4096 + 4096 * 4096 + 4096 * 4096 + 4096 * 4096 + 4096 * 1024) * 2
                tflops_fp32 = flops / (time_fp32 * 1e12)
                tflops_quant = flops / (time_quant * 1e12)

                print(f"  ⚡ {scheme_name}:")
                print(f"    Time: {time_quant * 1000:.2f} ms")
                print(f"    TFLOPS: {tflops_quant:.2f}")
                print(f"    Speedup: {speedup:.2f}x")
                print(f"    TFLOPS Ratio: {tflops_quant / tflops_fp32:.2f}x")

                # Check accuracy
                error = torch.mean(torch.abs(result_fp32 - result_quant))
                print(f"    Accuracy: {error:.6f}")

            except Exception as e:
                print(f"  ❌ {scheme_name} failed: {e}")

    except Exception as e:
        print(f"❌ Advanced FP8 test failed: {e}")


def test_torchao_fp8_compile():
    """Test TorchAO FP8 with torch.compile for maximum performance"""
    print("\n" + "=" * 60)
    print(" TORCHAO FP8 + TORCH.COMPILE")
    print("=" * 60)

    try:
        from torchao.quantization import quantize_, float8_weight_only

        device = torch.device("cuda")

        # Create model
        class OptimizedModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear1 = torch.nn.Linear(4096, 4096)
                self.linear2 = torch.nn.Linear(4096, 4096)
                self.linear3 = torch.nn.Linear(4096, 4096)

            def forward(self, x):
                x = torch.relu(self.linear1(x))
                x = torch.relu(self.linear2(x))
                x = self.linear3(x)
                return x

        model = OptimizedModel().to(device)
        input_tensor = torch.randn(128, 4096, device=device)

        # Create different versions
        model_fp32 = model
        model_fp8 = quantize_(model, float8_weight_only())
        model_fp8_compiled = torch.compile(model_fp8)

        models = [
            ("FP32 Baseline", model_fp32),
            ("FP8 Quantized", model_fp8),
            ("FP8 + Compiled", model_fp8_compiled),
        ]

        results = []
        for name, test_model in models:

            def forward():
                return test_model(input_tensor)

            result, avg_time = benchmark_operation(forward, name)
            results.append((name, result, avg_time))

        # Compare results
        print(f"\n📊 Performance Comparison:")
        baseline_time = results[0][2]

        for name, result, avg_time in results:
            speedup = baseline_time / avg_time
            flops = 128 * 4096 * 4096 * 3 * 2  # Rough estimate
            tflops = flops / (avg_time * 1e12)

            print(f"  {name}:")
            print(f"    Time: {avg_time * 1000:.2f} ms")
            print(f"    TFLOPS: {tflops:.2f}")
            print(f"    Speedup: {speedup:.2f}x")

    except Exception as e:
        print(f"❌ Compile test failed: {e}")


def main():
    print("🔥 TORCHAO FP8 NATIVE COMPUTATION")
    print("Maximum TFLOPS with PyTorch's Official FP8 Implementation")
    print("=" * 60)

    # Check environment
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Compute capability: {torch.cuda.get_device_capability(0)}")

    # Check TorchAO availability
    if not check_torchao():
        print("❌ Cannot proceed without TorchAO")
        return

    # Run tests
    test_torchao_fp8()
    test_torchao_fp8_advanced()
    test_torchao_fp8_compile()

    print("\n🎉 TORCHAO FP8 TESTING COMPLETE!")
    print("This demonstrated native FP8 computation using PyTorch's official")
    print("quantization library for maximum TFLOPS on H100.")


if __name__ == "__main__":
    main()
