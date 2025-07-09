"""
FluxKontextPipeline with Native PyTorch FP8 - NO COMPILATION!
Pure FP8 acceleration using PyTorch native support, no torch.compile
"""

import os
import time
import warnings
from typing import Optional, Dict, Any
import gc

import torch
import torch.nn as nn

try:
    from diffusers import FluxKontextPipeline
    from diffusers.utils import logging

    HAS_DIFFUSERS = True
except ImportError:
    HAS_DIFFUSERS = False
    raise ImportError("Please install diffusers from main branch")

# Configure logging
logging.set_verbosity_error()
warnings.filterwarnings("ignore", category=UserWarning)


def has_native_fp8():
    """Check if PyTorch has native FP8 support"""
    return hasattr(torch, "float8_e4m3fn") and hasattr(torch, "float8_e5m2") and torch.cuda.is_available()


class SimpleFP8Linear(nn.Module):
    """Simple FP8 Linear layer - no compilation, just pure FP8"""

    def __init__(self, in_features: int, out_features: int, bias: bool = True, device=None):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features

        # Use FP8 if available
        self.use_fp8 = has_native_fp8()
        weight_dtype = torch.float8_e4m3fn if self.use_fp8 else torch.bfloat16

        self.weight = nn.Parameter(torch.empty(out_features, in_features, dtype=weight_dtype, device=device))

        if bias:
            self.bias = nn.Parameter(torch.empty(out_features, dtype=torch.bfloat16, device=device))
        else:
            self.register_parameter("bias", None)

    def forward(self, x):
        """Simple forward pass - no compilation tricks"""
        if self.use_fp8:
            # Convert FP8 to bf16 for computation
            weight_bf16 = self.weight.to(torch.bfloat16)
            return torch.nn.functional.linear(x, weight_bf16, self.bias)
        else:
            return torch.nn.functional.linear(x, self.weight, self.bias)


class SimpleFP8Pipeline:
    """FluxKontextPipeline with simple FP8 - NO COMPILATION"""

    def __init__(self, model_id: str = "black-forest-labs/FLUX.1-Kontext-dev", use_fp8: bool = True):
        self.model_id = model_id
        self.use_fp8 = use_fp8 and has_native_fp8()
        self.pipeline = None

        self._setup_environment()

    def _setup_environment(self):
        """Setup environment - NO COMPILATION"""
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name()
            print(f"GPU: {device_name}")

            if "H100" in device_name:
                print("✓ H100 detected - perfect for FP8!")

            torch.cuda.empty_cache()

            # Basic optimizations only
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

            print(f"CUDA Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

        # Check FP8 support
        if self.use_fp8:
            if has_native_fp8():
                print("✓ Native FP8 support available!")
            else:
                print("⚠ No native FP8, using bfloat16")
                self.use_fp8 = False

    def _convert_to_fp8_simple(self, model):
        """Convert to FP8 - simple, no compilation"""
        if not self.use_fp8:
            print("Using bfloat16 (FP8 not available)")
            return model.to(torch.bfloat16)

        print("Converting to FP8 layers (no compilation)...")
        converted_count = 0

        def replace_linear(module):
            nonlocal converted_count

            for child_name, child in list(module.named_children()):
                if isinstance(child, nn.Linear):
                    # Simple FP8 replacement
                    fp8_layer = SimpleFP8Linear(
                        child.in_features, child.out_features, bias=child.bias is not None, device=child.weight.device
                    )

                    # Copy weights to FP8
                    with torch.no_grad():
                        if self.use_fp8:
                            fp8_layer.weight.data = child.weight.data.to(torch.float8_e4m3fn)
                        else:
                            fp8_layer.weight.data = child.weight.data.to(torch.bfloat16)

                        if child.bias is not None:
                            fp8_layer.bias.data = child.bias.data.to(torch.bfloat16)

                    setattr(module, child_name, fp8_layer)
                    converted_count += 1

                else:
                    replace_linear(child)

        replace_linear(model)
        print(f"✓ Converted {converted_count} layers to {'FP8' if self.use_fp8 else 'bfloat16'}")

        return model

    def load_pipeline(self):
        """Load pipeline with FP8 - NO COMPILATION"""
        dtype_str = "FP8" if self.use_fp8 else "bfloat16"
        print(f"Loading FluxKontextPipeline with {dtype_str} (NO COMPILATION)...")

        # Memory tracking
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            memory_before = torch.cuda.memory_allocated() / 1024**3
            print(f"GPU Memory before: {memory_before:.2f} GB")

        start_time = time.time()

        # Load pipeline
        self.pipeline = FluxKontextPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
        )

        # Move to CUDA
        if torch.cuda.is_available():
            print("Moving pipeline to CUDA...")
            self.pipeline = self.pipeline.to("cuda")

        # Convert transformer to FP8 - NO COMPILATION
        if hasattr(self.pipeline, "transformer"):
            print("Converting transformer to FP8...")
            self.pipeline.transformer = self._convert_to_fp8_simple(self.pipeline.transformer)

        # Basic optimizations only
        self.pipeline.enable_attention_slicing()

        # NO TORCH.COMPILE AT ALL!
        print("✓ No compilation - pure FP8 acceleration only")

        load_time = time.time() - start_time
        print(f"Pipeline loaded in {load_time:.2f}s")

        # Memory after loading
        if torch.cuda.is_available():
            memory_after = torch.cuda.memory_allocated() / 1024**3
            model_memory = memory_after - memory_before
            print(f"GPU Memory after: {memory_after:.2f} GB")
            print(f"Model memory usage: {model_memory:.2f} GB")

        return model_memory if torch.cuda.is_available() else 0

    def generate_pure_fp8(
        self, prompt: str, num_inference_steps: int = 20, height: int = 1024, width: int = 1024
    ) -> Dict[str, Any]:
        """Generate with pure FP8 - NO COMPILATION"""

        if self.pipeline is None:
            raise ValueError("Pipeline not loaded!")

        # Clear cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

        dtype_str = "FP8" if self.use_fp8 else "bfloat16"
        print(f"\\nGenerating with pure {dtype_str} (no compilation)...")
        start_time = time.time()

        # Pure generation - no autocast, no compilation
        with torch.no_grad():
            result = self.pipeline(
                prompt=prompt, num_inference_steps=num_inference_steps, height=height, width=width, guidance_scale=2.5
            )

        generation_time = time.time() - start_time

        # Memory stats
        if torch.cuda.is_available():
            memory_peak = torch.cuda.max_memory_allocated() / 1024**3
            memory_current = torch.cuda.memory_allocated() / 1024**3
        else:
            memory_peak = memory_current = 0

        print(f"✓ Generation completed in {generation_time:.2f}s")
        print(f"Memory peak: {memory_peak:.2f} GB")

        return {
            "image": result.images[0],
            "generation_time": generation_time,
            "memory_peak_gb": memory_peak,
            "memory_current_gb": memory_current,
            "fp8_enabled": self.use_fp8,
        }

    def benchmark_pure_fp8(self, num_runs: int = 3):
        """Benchmark pure FP8 vs bf16 - NO COMPILATION"""

        prompt = "A futuristic city at sunset with flying cars"

        print(f"\\n{'=' * 60}")
        print("PURE FP8 BENCHMARK (NO COMPILATION)")
        print(f"{'=' * 60}")
        print(f"Mode: {'FP8' if self.use_fp8 else 'bfloat16'}")
        print("Compilation: DISABLED")

        # Warmup
        print("\\nWarmup run...")
        self.generate_pure_fp8(prompt, num_inference_steps=10)

        # Benchmark runs
        times = []
        for i in range(num_runs):
            print(f"\\nRun {i + 1}/{num_runs}:")

            result = self.generate_pure_fp8(prompt=prompt, num_inference_steps=20, height=1024, width=1024)

            times.append(result["generation_time"])

            if i == 0:
                result["image"].save(f"pure_fp8_output.png")
                print("✓ Saved pure_fp8_output.png")

        # Results
        avg_time = sum(times) / len(times)
        min_time = min(times)

        print(f"\\n{'=' * 60}")
        print("PURE FP8 RESULTS")
        print(f"{'=' * 60}")
        print(f"Average time: {avg_time:.2f}s")
        print(f"Best time: {min_time:.2f}s")
        print(f"All times: {[f'{t:.2f}s' for t in times]}")

        return {"average_time": avg_time, "min_time": min_time, "all_times": times, "fp8_enabled": self.use_fp8}


def test_fp8_vs_bf16():
    """Test FP8 vs bf16 without any compilation"""

    print("🚀 Testing Pure FP8 vs bfloat16 (NO COMPILATION)")
    print(f"PyTorch version: {torch.__version__}")
    print(f"Native FP8 support: {has_native_fp8()}")

    configs = [{"name": "FP8", "use_fp8": True}, {"name": "bfloat16", "use_fp8": False}]

    results = {}

    for config in configs:
        print(f"\\n{'=' * 80}")
        print(f"TESTING {config['name'].upper()} (NO COMPILATION)")
        print(f"{'=' * 80}")

        pipeline = SimpleFP8Pipeline(use_fp8=config["use_fp8"])
        pipeline.load_pipeline()

        result = pipeline.benchmark_pure_fp8(num_runs=2)
        results[config["name"]] = result

        # Cleanup
        del pipeline
        gc.collect()
        torch.cuda.empty_cache()

    # Compare results
    print(f"\\n{'=' * 80}")
    print("FINAL COMPARISON (NO COMPILATION)")
    print(f"{'=' * 80}")

    for name, result in results.items():
        print(f"{name}: {result['average_time']:.2f}s average")

    if "FP8" in results and "bfloat16" in results:
        fp8_time = results["FP8"]["average_time"]
        bf16_time = results["bfloat16"]["average_time"]

        if fp8_time < bf16_time:
            speedup = bf16_time / fp8_time
            print(f"\\n🚀 FP8 SPEEDUP: {speedup:.2f}x faster!")
        else:
            print(f"\\n⚠ FP8 was {fp8_time / bf16_time:.2f}x slower (might need more optimization)")


if __name__ == "__main__":
    test_fp8_vs_bf16()
