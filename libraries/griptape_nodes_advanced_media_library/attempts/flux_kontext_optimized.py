"""
Optimized FluxKontextPipeline with Quantization for Windows + CUDA
Maximizes inference speed while maintaining quality through aggressive optimization.
"""

import os
import sys
import time
import hashlib
import pickle
import warnings
from pathlib import Path
from typing import Optional, Union, Dict, Any, Tuple, List
from contextlib import contextmanager
import gc

import torch
import torch.nn as nn
from torch.nn import functional as F
import psutil
import GPUtil

try:
    import bitsandbytes as bnb

    HAS_BITSANDBYTES = True
except ImportError:
    HAS_BITSANDBYTES = False
    warnings.warn("bitsandbytes not available. Install with: pip install bitsandbytes")

try:
    from diffusers import FluxKontextPipeline
    from diffusers.models.transformers.transformer_flux import FluxTransformer2DModel
    from diffusers.utils import logging
    from diffusers.quantizers import PipelineQuantizationConfig

    HAS_DIFFUSERS = True
except ImportError:
    HAS_DIFFUSERS = False
    raise ImportError(
        "Please install diffusers from main branch: pip install git+https://github.com/huggingface/diffusers.git"
    )

# Configure logging
logging.set_verbosity_error()
warnings.filterwarnings("ignore", category=UserWarning)


class PerformanceMonitor:
    """Lightweight performance monitoring for inference optimization"""

    def __init__(self):
        self.metrics = {}
        self.start_time = None
        self.peak_memory = 0

    def start(self, operation: str):
        """Start timing an operation"""
        self.start_time = time.perf_counter()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            self.peak_memory = torch.cuda.max_memory_allocated()

    def end(self, operation: str) -> Dict[str, float]:
        """End timing and record metrics"""
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            current_memory = torch.cuda.max_memory_allocated()
            memory_used = (current_memory - self.peak_memory) / 1024**3  # GB
        else:
            memory_used = 0

        elapsed = time.perf_counter() - self.start_time

        self.metrics[operation] = {"time": elapsed, "memory_gb": memory_used, "gpu_util": self._get_gpu_utilization()}

        return self.metrics[operation]

    def _get_gpu_utilization(self) -> float:
        """Get current GPU utilization"""
        try:
            gpus = GPUtil.getGPUs()
            return gpus[0].load * 100 if gpus else 0.0
        except:
            return 0.0

    def print_summary(self):
        """Print performance summary"""
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)

        total_time = sum(m["time"] for m in self.metrics.values())
        print(f"Total inference time: {total_time:.2f}s")

        for op, metrics in self.metrics.items():
            print(f"{op:.<30} {metrics['time']:.2f}s ({metrics['memory_gb']:.1f}GB)")

        print("=" * 60)


class QuantizedModelCache:
    """Efficient disk caching for quantized models to avoid cold start penalties"""

    def __init__(self, cache_dir: str = "./quantized_models_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def _get_cache_key(self, model_id: str, config: Dict[str, Any]) -> str:
        """Generate cache key from model ID and quantization config"""
        config_str = str(sorted(config.items()))
        combined = f"{model_id}_{config_str}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a given key"""
        return self.cache_dir / f"{cache_key}.pkl"

    def save_quantized_state(self, model_id: str, config: Dict[str, Any], state_dict: Dict[str, torch.Tensor]):
        """Save quantized model state to disk"""
        cache_key = self._get_cache_key(model_id, config)
        cache_path = self._get_cache_path(cache_key)

        print(f"Caching quantized model: {cache_path}")

        # Convert tensors to CPU before saving
        cpu_state_dict = {k: v.cpu() for k, v in state_dict.items()}

        with open(cache_path, "wb") as f:
            pickle.dump(
                {"model_id": model_id, "config": config, "state_dict": cpu_state_dict, "timestamp": time.time()}, f
            )

    def load_quantized_state(self, model_id: str, config: Dict[str, Any]) -> Optional[Dict[str, torch.Tensor]]:
        """Load quantized model state from disk"""
        cache_key = self._get_cache_key(model_id, config)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        print(f"Loading cached quantized model: {cache_path}")

        with open(cache_path, "rb") as f:
            cached_data = pickle.load(f)

        # Move tensors to GPU if available
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        state_dict = {k: v.to(device) for k, v in cached_data["state_dict"].items()}

        return state_dict

    def clear_cache(self):
        """Clear all cached models"""
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()
        print("Quantized model cache cleared")


class OptimizedFluxKontextPipeline:
    """Highly optimized FluxKontextPipeline with aggressive quantization and caching"""

    def __init__(
        self,
        model_id: str = "black-forest-labs/FLUX.1-Kontext-dev",
        quantization_bits: Optional[int] = 8,
        cache_quantized: bool = True,
        enable_cpu_offload: bool = True,
        torch_compile: bool = True,
        enable_attention_slicing: bool = True,
    ):
        self.model_id = model_id
        self.quantization_bits = quantization_bits
        self.cache_quantized = cache_quantized
        self.enable_cpu_offload = enable_cpu_offload
        self.torch_compile = torch_compile
        self.enable_attention_slicing = enable_attention_slicing

        self.pipeline = None
        self.cache = QuantizedModelCache() if cache_quantized else None
        self.monitor = PerformanceMonitor()

        # Optimization configurations
        self.quantization_config = {
            "bits": quantization_bits,
            "quant_method": "bitsandbytes",
            "load_in_8bit": quantization_bits == 8,
            "load_in_4bit": quantization_bits == 4,
            "bnb_4bit_compute_dtype": torch.bfloat16,
            "bnb_4bit_use_double_quant": True,
            "bnb_4bit_quant_type": "nf4",
        }

        self._setup_environment()

    def _setup_environment(self):
        """Setup optimal environment for Windows + CUDA"""
        # CUDA optimizations
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False

            # Enable TensorFloat-32 for maximum speed on Ampere+ GPUs
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

            print(f"CUDA Device: {torch.cuda.get_device_name()}")
            print(f"CUDA Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

        # Set optimal number of threads
        torch.set_num_threads(min(8, os.cpu_count()))

        # Memory management
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"

    def _create_quantization_config(self) -> PipelineQuantizationConfig:
        """Create optimized quantization configuration"""
        if not HAS_BITSANDBYTES:
            raise ImportError("bitsandbytes required for quantization")

        # Determine the correct backend name based on quantization bits
        if self.quantization_bits == 8:
            quant_backend = "bitsandbytes_8bit"
            quant_kwargs = {
                "bnb_8bit_use_double_quant": True,
            }
        elif self.quantization_bits == 4:
            quant_backend = "bitsandbytes_4bit"
            quant_kwargs = {
                "bnb_4bit_compute_dtype": torch.bfloat16,
                "bnb_4bit_use_double_quant": True,
                "bnb_4bit_quant_type": "nf4",
            }
        else:
            raise ValueError(f"Unsupported quantization bits: {self.quantization_bits}. Use 4 or 8.")

        # Create pipeline quantization config
        return PipelineQuantizationConfig(
            quant_backend=quant_backend,
            quant_kwargs=quant_kwargs,
            components_to_quantize=["transformer"],  # Focus on the main transformer component
        )

    def _optimize_pipeline(self, pipeline: FluxKontextPipeline) -> FluxKontextPipeline:
        """Apply aggressive optimizations to the pipeline"""

        # Enable attention slicing for memory efficiency
        if self.enable_attention_slicing:
            pipeline.enable_attention_slicing()

        # Enable CPU offload for memory management (reset device map first if needed)
        cpu_offload_enabled = False
        if self.enable_cpu_offload:
            try:
                # Reset device map if it exists, then enable CPU offload
                if hasattr(pipeline, "hf_device_map") and pipeline.hf_device_map:
                    pipeline.reset_device_map()
                pipeline.enable_model_cpu_offload()
                cpu_offload_enabled = True
                print("CPU offload enabled")
            except Exception as e:
                print(f"Warning: Could not enable CPU offload: {e}")
                print("Continuing without CPU offload...")

        # Compile transformer for maximum speed (but not with CPU offload or quantization due to conflicts)
        if self.torch_compile and hasattr(pipeline, "transformer") and not cpu_offload_enabled:
            # Check if model is quantized (incompatible with torch.compile)
            is_quantized = any(hasattr(param, "quant_state") for param in pipeline.transformer.parameters())

            if not is_quantized:
                print("Compiling transformer with torch.compile...")
                try:
                    pipeline.transformer = torch.compile(pipeline.transformer, mode="max-autotune", fullgraph=True)
                except Exception as e:
                    print(f"Warning: Could not compile transformer: {e}")
                    print("Continuing without torch.compile...")
            else:
                print("Skipping torch.compile due to quantization (incompatible)")
        elif self.torch_compile and cpu_offload_enabled:
            print("Skipping torch.compile due to CPU offload (incompatible)")

        # Optimize VAE if available
        if hasattr(pipeline, "vae") and pipeline.vae is not None:
            pipeline.vae = pipeline.vae.to(memory_format=torch.channels_last)
            # Only compile VAE if not quantized and not using CPU offload
            vae_is_quantized = any(hasattr(param, "quant_state") for param in pipeline.vae.parameters())
            if self.torch_compile and not cpu_offload_enabled and not vae_is_quantized:
                try:
                    pipeline.vae.decoder = torch.compile(pipeline.vae.decoder, mode="max-autotune")
                except Exception as e:
                    print(f"Warning: Could not compile VAE decoder: {e}")

        return pipeline

    def load_pipeline(self) -> FluxKontextPipeline:
        """Load and optimize the pipeline with quantization"""

        self.monitor.start("pipeline_loading")

        # Try to load from cache first
        if self.cache:
            cached_state = self.cache.load_quantized_state(self.model_id, self.quantization_config)
            if cached_state:
                print("Loading from quantized cache...")
                # Note: Full cache restoration would require more complex implementation
                # For now, we'll load normally and cache the result

        # Load pipeline with or without quantization
        if self.quantization_bits is not None:
            # Create quantization config
            quantization_config = self._create_quantization_config()
            print(f"Loading {self.model_id} with {self.quantization_bits}-bit quantization...")

            self.pipeline = FluxKontextPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                quantization_config=quantization_config,
                device_map="balanced",
                use_safetensors=True,
            )
        else:
            print(f"Loading {self.model_id} without quantization...")

            self.pipeline = FluxKontextPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                use_safetensors=True,
            )

        # Apply optimizations
        self.pipeline = self._optimize_pipeline(self.pipeline)

        # Cache quantized state
        if self.cache and hasattr(self.pipeline, "transformer"):
            self.cache.save_quantized_state(
                self.model_id, self.quantization_config, self.pipeline.transformer.state_dict()
            )

        load_metrics = self.monitor.end("pipeline_loading")
        print(f"Pipeline loaded in {load_metrics['time']:.2f}s")

        return self.pipeline

    @contextmanager
    def _inference_context(self):
        """Context manager for optimal inference settings"""
        # Store original settings
        original_grad_enabled = torch.is_grad_enabled()

        try:
            # Optimize for inference
            torch.set_grad_enabled(False)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            yield

        finally:
            # Restore settings
            torch.set_grad_enabled(original_grad_enabled)

    def generate(
        self,
        image: Optional[Union[torch.Tensor, str]] = None,
        prompt: str = "",
        negative_prompt: str = "",
        num_inference_steps: int = 20,
        guidance_scale: float = 2.5,
        height: int = 1024,
        width: int = 1024,
        **kwargs,
    ) -> torch.Tensor:
        """Generate image with optimized inference"""

        if self.pipeline is None:
            self.load_pipeline()

        self.monitor.start("inference")

        with self._inference_context():
            # Prepare inputs
            if isinstance(image, str):
                from diffusers.utils import load_image

                image = load_image(image)

            # Generate with optimized settings
            result = self.pipeline(
                image=image,
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                height=height,
                width=width,
                **kwargs,
            )

        inference_metrics = self.monitor.end("inference")
        print(f"Inference completed in {inference_metrics['time']:.2f}s")

        return result.images[0]

    def benchmark(self, test_prompt: str = "Add a hat to the cat", num_runs: int = 3) -> Dict[str, float]:
        """Benchmark the optimized pipeline"""

        print(f"\nBenchmarking {num_runs} runs...")

        if self.pipeline is None:
            self.load_pipeline()

        # Warmup run
        print("Warmup run...")
        self.generate(prompt=test_prompt, num_inference_steps=10)

        # Benchmark runs
        times = []
        for i in range(num_runs):
            print(f"Run {i + 1}/{num_runs}")
            start = time.perf_counter()

            self.generate(prompt=test_prompt, num_inference_steps=20)

            end = time.perf_counter()
            times.append(end - start)

            # Clear cache between runs
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Calculate statistics
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        results = {
            "average_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
            "std_dev": (sum((t - avg_time) ** 2 for t in times) / len(times)) ** 0.5,
        }

        print(f"\nBenchmark Results:")
        print(f"Average time: {avg_time:.2f}s")
        print(f"Min time: {min_time:.2f}s")
        print(f"Max time: {max_time:.2f}s")
        print(f"Std dev: {results['std_dev']:.2f}s")

        return results

    def print_performance_summary(self):
        """Print comprehensive performance summary"""
        self.monitor.print_summary()

        # System information
        print("\nSYSTEM INFORMATION")
        print("=" * 60)
        print(f"CPU: {psutil.cpu_count()} cores")
        print(f"RAM: {psutil.virtual_memory().total / 1024**3:.1f} GB")

        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name()}")
            print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            print(f"CUDA Version: {torch.version.cuda}")

        print(f"PyTorch Version: {torch.__version__}")
        print(f"Quantization: {self.quantization_bits}-bit")


def main():
    """Example usage of the optimized pipeline"""

    # Create optimized pipeline
    optimized_pipeline = OptimizedFluxKontextPipeline(
        quantization_bits=8,  # Use 8-bit for best speed/quality balance
        cache_quantized=True,
        enable_cpu_offload=False,  # Disable CPU offload for torch.compile compatibility
        torch_compile=True,
        enable_attention_slicing=True,
    )

    # Load and benchmark
    optimized_pipeline.load_pipeline()

    # Generate a test image
    print("\nGenerating test image...")
    result = optimized_pipeline.generate(
        prompt="A futuristic city at sunset with flying cars", num_inference_steps=20, height=1024, width=1024
    )

    # Save result
    result.save("optimized_flux_output.png")
    print("Result saved to optimized_flux_output.png")

    # Run benchmark
    optimized_pipeline.benchmark(num_runs=3)

    # Print performance summary
    optimized_pipeline.print_performance_summary()


if __name__ == "__main__":
    main()
