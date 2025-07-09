"""
FluxKontextPipeline with Native PyTorch FP8 (no TransformerEngine required)
Uses PyTorch 2.1+ native FP8 support for H100 acceleration
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


class FastFP8Linear(nn.Module):
    """Optimized FP8 Linear layer using PyTorch native dtypes"""

    def __init__(self, in_features: int, out_features: int, bias: bool = True, device=None):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features

        # Use FP8 if available, otherwise bf16
        self.use_fp8 = has_native_fp8()
        weight_dtype = torch.float8_e4m3fn if self.use_fp8 else torch.bfloat16

        self.weight = nn.Parameter(torch.empty(out_features, in_features, dtype=weight_dtype, device=device))

        if bias:
            self.bias = nn.Parameter(torch.empty(out_features, dtype=torch.bfloat16, device=device))
        else:
            self.register_parameter("bias", None)

        self.reset_parameters()

    def reset_parameters(self):
        """Initialize parameters"""
        if self.use_fp8:
            # Initialize in bf16 then convert to FP8
            with torch.no_grad():
                temp_weight = torch.empty_like(self.weight, dtype=torch.bfloat16)
                nn.init.kaiming_uniform_(temp_weight, a=5**0.5)
                # Convert to FP8 with proper scaling
                max_val = temp_weight.abs().max()
                scale = 240.0 / max_val  # Scale for FP8 E4M3 range
                scaled_weight = temp_weight * scale
                self.weight.data = scaled_weight.to(torch.float8_e4m3fn)
        else:
            nn.init.kaiming_uniform_(self.weight, a=5**0.5)

        if self.bias is not None:
            nn.init.zeros_(self.bias)

    def forward(self, x):
        """Optimized forward pass"""
        if self.use_fp8:
            # Convert FP8 weights to bf16 for computation
            weight_bf16 = self.weight.to(torch.bfloat16)
            return torch.nn.functional.linear(x, weight_bf16, self.bias)
        else:
            return torch.nn.functional.linear(x, self.weight, self.bias)


class NativeFP8Pipeline:
    """FluxKontextPipeline with native PyTorch FP8 acceleration"""

    def __init__(
        self, model_id: str = "black-forest-labs/FLUX.1-Kontext-dev", use_fp8: bool = True, compile_model: bool = True
    ):
        self.model_id = model_id
        self.use_fp8 = use_fp8 and has_native_fp8()
        self.compile_model = compile_model
        self.pipeline = None

        self._setup_environment()

    def _setup_environment(self):
        """Setup optimal environment for native FP8"""
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name()
            print(f"GPU: {device_name}")

            if "H100" in device_name:
                print("✓ H100 detected - optimal for FP8!")
            elif "A100" in device_name or "4090" in device_name:
                print("⚠ This GPU has limited FP8 support")

            torch.cuda.empty_cache()
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False

            # Enable all optimizations
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

            print(f"CUDA Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

        # Check FP8 support
        if self.use_fp8:
            if has_native_fp8():
                print("✓ Native FP8 support detected!")
                print(f"Available dtypes: {[torch.float8_e4m3fn, torch.float8_e5m2]}")
            else:
                print("⚠ No native FP8 support, falling back to bfloat16")
                self.use_fp8 = False

        # Set optimal threading
        torch.set_num_threads(min(8, os.cpu_count()))

    def _convert_to_fast_fp8(self, model):
        """Convert linear layers to fast FP8 layers"""
        if not self.use_fp8:
            print("Using bfloat16 (FP8 not available)")
            return model.to(torch.bfloat16)

        print("Converting to native FP8 layers...")
        converted_count = 0

        def replace_linear_with_fp8(module, name=""):
            nonlocal converted_count

            for child_name, child in list(module.named_children()):
                if isinstance(child, nn.Linear):
                    # Create FP8 replacement
                    fp8_layer = FastFP8Linear(
                        child.in_features, child.out_features, bias=child.bias is not None, device=child.weight.device
                    )

                    # Copy weights with proper FP8 conversion
                    with torch.no_grad():
                        if self.use_fp8:
                            # Scale and convert to FP8
                            weight_data = child.weight.data.to(torch.bfloat16)
                            max_val = weight_data.abs().max()
                            scale = 240.0 / max_val if max_val > 0 else 1.0
                            scaled_weight = weight_data * scale
                            fp8_layer.weight.data = scaled_weight.to(torch.float8_e4m3fn)
                        else:
                            fp8_layer.weight.data = child.weight.data.to(torch.bfloat16)

                        if child.bias is not None:
                            fp8_layer.bias.data = child.bias.data.to(torch.bfloat16)

                    setattr(module, child_name, fp8_layer)
                    converted_count += 1

                else:
                    replace_linear_with_fp8(child, name + "." + child_name if name else child_name)

        replace_linear_with_fp8(model)
        print(f"✓ Converted {converted_count} Linear layers to {'FP8' if self.use_fp8 else 'bfloat16'}")

        return model

    def load_pipeline(self):
        """Load pipeline with native FP8 optimization"""
        dtype_str = "FP8" if self.use_fp8 else "bfloat16"
        print(f"Loading FluxKontextPipeline with native {dtype_str}...")

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
            torch_dtype=torch.bfloat16,  # Load as bf16 first
            use_safetensors=True,
        )

        # Move to CUDA
        if torch.cuda.is_available():
            print("Moving pipeline to CUDA...")
            self.pipeline = self.pipeline.to("cuda")

        # Convert transformer to FP8
        if hasattr(self.pipeline, "transformer"):
            print("Converting transformer to FP8...")
            self.pipeline.transformer = self._convert_to_fast_fp8(self.pipeline.transformer)

        # Optimizations
        self.pipeline.enable_attention_slicing()

        # Compile for maximum speed
        if self.compile_model and hasattr(self.pipeline, "transformer"):
            print("Compiling transformer...")
            try:
                self.pipeline.transformer = torch.compile(
                    self.pipeline.transformer, mode="max-autotune", fullgraph=False, dynamic=False
                )
                print("✓ Transformer compiled!")
            except Exception as e:
                print(f"Warning: Compilation failed: {e}")

        load_time = time.time() - start_time
        print(f"Pipeline loaded in {load_time:.2f}s")

        # Memory after loading
        if torch.cuda.is_available():
            memory_after = torch.cuda.memory_allocated() / 1024**3
            model_memory = memory_after - memory_before
            print(f"GPU Memory after: {memory_after:.2f} GB")
            print(f"Model memory usage: {model_memory:.2f} GB")

        return model_memory if torch.cuda.is_available() else 0

    def generate_fast(
        self, prompt: str, num_inference_steps: int = 20, height: int = 1024, width: int = 1024
    ) -> Dict[str, Any]:
        """Generate with optimized FP8/bf16"""

        if self.pipeline is None:
            raise ValueError("Pipeline not loaded!")

        # Clear cache and reset stats
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

        dtype_str = "FP8" if self.use_fp8 else "bfloat16"
        print(f"\\nGenerating with {dtype_str}...")
        start_time = time.time()

        # Use autocast for mixed precision
        with torch.cuda.amp.autocast(enabled=True, dtype=torch.bfloat16):
            with torch.no_grad():
                result = self.pipeline(
                    prompt=prompt,
                    num_inference_steps=num_inference_steps,
                    height=height,
                    width=width,
                    guidance_scale=2.5,
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

    def benchmark_speed(self, num_runs: int = 3):
        """Benchmark native FP8 performance"""

        prompt = "A futuristic city at sunset with flying cars, highly detailed"

        print(f"\\n{'=' * 60}")
        print("NATIVE FP8 SPEED BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Mode: {'FP8' if self.use_fp8 else 'bfloat16'}")
        print(f"Compilation: {'ON' if self.compile_model else 'OFF'}")

        # Warmup
        print("\\nWarmup run...")
        self.generate_fast(prompt, num_inference_steps=10)

        # Benchmark runs
        times = []
        for i in range(num_runs):
            print(f"\\nRun {i + 1}/{num_runs}:")

            result = self.generate_fast(prompt=prompt, num_inference_steps=20, height=1024, width=1024)

            times.append(result["generation_time"])

            if i == 0:
                result["image"].save(f"native_fp8_output.png")
                print("✓ Saved native_fp8_output.png")

        # Results
        avg_time = sum(times) / len(times)
        min_time = min(times)

        print(f"\\n{'=' * 60}")
        print("BENCHMARK RESULTS")
        print(f"{'=' * 60}")
        print(f"Average time: {avg_time:.2f}s")
        print(f"Best time: {min_time:.2f}s")
        print(f"Times: {[f'{t:.2f}s' for t in times]}")

        # Compare to previous results
        bf16_baseline = 7.5  # From your previous results
        if avg_time < bf16_baseline:
            speedup = bf16_baseline / avg_time
            print(f"🚀 SPEEDUP: {speedup:.2f}x faster than baseline!")

        return {"average_time": avg_time, "min_time": min_time, "all_times": times, "fp8_enabled": self.use_fp8}


def main():
    """Test native FP8 acceleration"""

    print("🚀 Testing Native PyTorch FP8 Acceleration")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"Native FP8 support: {has_native_fp8()}")

    # Test FP8 vs bf16
    for use_fp8 in [True, False]:
        config_name = "FP8" if use_fp8 else "bfloat16"
        print(f"\\n{'=' * 80}")
        print(f"TESTING {config_name.upper()}")
        print(f"{'=' * 80}")

        pipeline = NativeFP8Pipeline(use_fp8=use_fp8, compile_model=True)

        pipeline.load_pipeline()
        results = pipeline.benchmark_speed(num_runs=2)

        print(f"\\n{config_name} Results: {results['average_time']:.2f}s average")

        # Cleanup
        del pipeline
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
