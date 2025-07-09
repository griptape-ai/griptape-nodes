import onnxruntime as ort
import torch
import numpy as np
import time
import gc
from pathlib import Path


class TensorRTVAEDecoder:
    """TensorRT-optimized VAE decoder for H100"""

    def __init__(self, onnx_path, use_fp16=True, profile_shapes=None):
        """
        Initialize TensorRT-optimized decoder

        Args:
            onnx_path: Path to ONNX model
            use_fp16: Use FP16 precision (recommended for H100)
            profile_shapes: Dict with min/opt/max shapes for optimization
        """
        # Default profile for common Flux resolutions
        if profile_shapes is None:
            profile_shapes = {
                "min": (1, 16, 64, 64),  # 512x512 output
                "opt": (1, 16, 128, 128),  # 1024x1024 output
                "max": (4, 16, 256, 256),  # 2048x2048 output or batch 4
            }

        # TensorRT provider options
        trt_provider_options = {
            "device_id": 0,
            "trt_max_workspace_size": 8 * 1024 * 1024 * 1024,  # 8GB workspace
            "trt_fp16_enable": use_fp16,
            "trt_engine_cache_enable": True,
            "trt_engine_cache_path": str(Path(onnx_path).parent),
            "trt_timing_cache_enable": True,
            "trt_force_sequential_engine_build": False,
            # Profile for dynamic shapes
            "trt_profile_min_shapes": f"latent_sample:{profile_shapes['min']}",
            "trt_profile_opt_shapes": f"latent_sample:{profile_shapes['opt']}",
            "trt_profile_max_shapes": f"latent_sample:{profile_shapes['max']}",
            # H100-specific optimizations
            "trt_cuda_graph_enable": True,  # Enable CUDA graphs for better performance
            "trt_preview_features": "1",  # Enable preview features
        }

        # Session options
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.enable_mem_pattern = True
        sess_options.enable_mem_reuse = True

        # Providers - TensorRT first
        providers = [
            ("TensorrtExecutionProvider", trt_provider_options),
            (
                "CUDAExecutionProvider",
                {
                    "device_id": 0,
                    "arena_extend_strategy": "kSameAsRequested",
                    "gpu_mem_limit": 80 * 1024 * 1024 * 1024,
                },
            ),
            "CPUExecutionProvider",
        ]

        print(f"Initializing TensorRT session (this may take a while on first run)...")
        start_time = time.time()

        try:
            self.session = ort.InferenceSession(onnx_path, sess_options=sess_options, providers=providers)

            # Verify TensorRT is being used
            actual_providers = self.session.get_providers()
            print(f"Session providers: {actual_providers}")

            if "TensorrtExecutionProvider" not in actual_providers:
                print("⚠️ WARNING: TensorRT provider not active! Falling back to CUDA.")
            else:
                print(f"✅ TensorRT initialized in {time.time() - start_time:.1f}s")

            # Get I/O info
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name

            # Warmup with different shapes to build TRT engines
            self._warmup_trt(profile_shapes)

        except Exception as e:
            print(f"Error creating TensorRT session: {e}")
            raise

    def _warmup_trt(self, profile_shapes):
        """Warmup to build TRT engines for different input sizes"""
        print("Building TensorRT engines for different input sizes...")

        # Test key sizes to prebuild engines
        test_sizes = [
            (1, 16, 64, 64),  # 512x512
            (1, 16, 128, 128),  # 1024x1024
            (1, 16, 192, 192),  # 1536x1536
        ]

        for shape in test_sizes:
            dummy = np.random.randn(*shape).astype(np.float32)
            try:
                print(f"  Building engine for {shape}...", end="", flush=True)
                start = time.time()
                _ = self.session.run([self.output_name], {self.input_name: dummy})
                print(f" done ({time.time() - start:.1f}s)")
            except Exception as e:
                print(f" failed: {e}")

        # Clear GPU memory
        torch.cuda.empty_cache()
        gc.collect()

    def decode(self, latents, return_dict=False):
        """Decode latents using TensorRT"""
        # Convert to numpy
        if isinstance(latents, torch.Tensor):
            device = latents.device
            latents_np = latents.cpu().contiguous().numpy()
        else:
            device = torch.device("cuda")
            latents_np = np.ascontiguousarray(latents)

        # Run inference
        output = self.session.run([self.output_name], {self.input_name: latents_np})[0]
        output_tensor = torch.from_numpy(output).to(device)

        if return_dict:
            from diffusers.models.autoencoders.vae import DecoderOutput

            return DecoderOutput(sample=output_tensor)
        return (output_tensor,)

    def to(self, device):
        """Compatibility method"""
        return self


def export_optimized_for_tensorrt(vae, output_path):
    """Export ONNX model optimized for TensorRT conversion"""
    import torch.onnx

    print("Exporting ONNX model optimized for TensorRT...")

    # Use multiple representative shapes
    dummy_input = torch.randn(1, 16, 128, 128, dtype=torch.float32)

    # Export with TensorRT-friendly settings
    with torch.no_grad():
        torch.onnx.export(
            vae.decoder,
            dummy_input,
            output_path,
            input_names=["latent_sample"],
            output_names=["sample"],
            dynamic_axes={
                "latent_sample": {0: "batch", 2: "height", 3: "width"},
                "sample": {0: "batch", 2: "height", 3: "width"},
            },
            opset_version=17,
            do_constant_folding=True,
            export_params=True,
            # TensorRT-specific optimizations
            operator_export_type=torch.onnx.OperatorExportTypes.ONNX,
            keep_initializers_as_inputs=False,
        )

    print(f"Exported to {output_path}")

    # Optimize ONNX model for TensorRT
    optimize_onnx_for_tensorrt(output_path)


def optimize_onnx_for_tensorrt(onnx_path):
    """Apply optimizations to ONNX model for better TensorRT conversion"""
    try:
        import onnx
        from onnxruntime.transformers import optimizer

        print("Applying TensorRT-specific optimizations...")

        # Load and optimize
        optimized_model = optimizer.optimize_model(
            onnx_path,
            model_type="vae",
            opt_level=99,
            use_gpu=True,
            disabled_optimizers=["NchwcTransformer"],  # Can interfere with TRT
        )

        # Save optimized version
        opt_path = Path(onnx_path).parent / f"{Path(onnx_path).stem}_trt_optimized.onnx"
        optimized_model.save_model_to_file(str(opt_path))
        print(f"Optimized model saved to {opt_path}")

        return opt_path
    except Exception as e:
        print(f"ONNX optimization failed: {e}")
        return onnx_path


def benchmark_tensorrt(vae_pytorch, vae_onnx, vae_trt):
    """Benchmark PyTorch vs ONNX vs TensorRT"""

    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON: PyTorch vs ONNX vs TensorRT")
    print("=" * 60)

    test_configs = [
        (1, 64, 64, "512x512"),
        (1, 128, 128, "1024x1024"),
        (1, 192, 192, "1536x1536"),
        (1, 256, 256, "2048x2048"),
        (2, 128, 128, "Batch 2 @ 1024x1024"),
    ]

    results = []

    for batch, h, w, desc in test_configs:
        print(f"\n{desc}:")

        try:
            # Create input
            latents = torch.randn(batch, 16, h, w, dtype=torch.float32).cuda()

            # PyTorch
            torch.cuda.synchronize()
            times = []
            for _ in range(10):
                start = time.perf_counter()
                with torch.no_grad():
                    _ = vae_pytorch.decode(latents, return_dict=False)[0]
                torch.cuda.synchronize()
                times.append(time.perf_counter() - start)
            pytorch_time = np.median(times)

            # ONNX
            torch.cuda.synchronize()
            times = []
            for _ in range(10):
                start = time.perf_counter()
                _ = vae_onnx.decode(latents, return_dict=False)[0]
                torch.cuda.synchronize()
                times.append(time.perf_counter() - start)
            onnx_time = np.median(times)

            # TensorRT
            torch.cuda.synchronize()
            times = []
            for _ in range(10):
                start = time.perf_counter()
                _ = vae_trt.decode(latents, return_dict=False)[0]
                torch.cuda.synchronize()
                times.append(time.perf_counter() - start)
            trt_time = np.median(times)

            print(f"  PyTorch:  {pytorch_time * 1000:.2f}ms")
            print(f"  ONNX:     {onnx_time * 1000:.2f}ms ({pytorch_time / onnx_time:.2f}x)")
            print(f"  TensorRT: {trt_time * 1000:.2f}ms ({pytorch_time / trt_time:.2f}x)")

            results.append(
                {
                    "config": desc,
                    "pytorch": pytorch_time,
                    "onnx": onnx_time,
                    "trt": trt_time,
                    "speedup_onnx": pytorch_time / onnx_time,
                    "speedup_trt": pytorch_time / trt_time,
                }
            )

        except Exception as e:
            print(f"  Error: {e}")
        finally:
            torch.cuda.empty_cache()
            gc.collect()

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        avg_speedup_onnx = np.mean([r["speedup_onnx"] for r in results])
        avg_speedup_trt = np.mean([r["speedup_trt"] for r in results])
        print(f"Average ONNX speedup: {avg_speedup_onnx:.2f}x")
        print(f"Average TensorRT speedup: {avg_speedup_trt:.2f}x")

        best_trt = max(results, key=lambda x: x["speedup_trt"])
        print(f"Best TensorRT speedup: {best_trt['speedup_trt']:.2f}x at {best_trt['config']}")


def main():
    """Test TensorRT optimization"""
    print("H100 TensorRT Optimization")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")

    # Check TensorRT availability
    providers = ort.get_available_providers()
    if "TensorrtExecutionProvider" not in providers:
        print("\n❌ TensorRT provider not available!")
        print("Install with: pip install onnxruntime-gpu[tensorrt]")
        return

    # Load models
    from diffusers import AutoencoderKL

    print("\nLoading PyTorch VAE...")
    vae_pytorch = (
        AutoencoderKL.from_pretrained(
            "black-forest-labs/FLUX.1-Kontext-dev", subfolder="vae", torch_dtype=torch.float32
        )
        .cuda()
        .eval()
    )

    # Load regular ONNX
    print("\nLoading ONNX VAE...")
    from claude_vae_to_onnx_something import OptimizedONNXVAEDecoder

    vae_onnx = OptimizedONNXVAEDecoder("flux_kontext_vae_decoder.onnx")

    # Load TensorRT version
    print("\nLoading TensorRT VAE...")
    vae_trt = TensorRTVAEDecoder(
        "flux_kontext_vae_decoder.onnx",
        use_fp16=True,  # H100 has excellent FP16 performance
        profile_shapes={
            "min": (1, 16, 64, 64),
            "opt": (1, 16, 128, 128),
            "max": (4, 16, 256, 256),
        },
    )

    # Run benchmarks
    benchmark_tensorrt(vae_pytorch, vae_onnx, vae_trt)

    print("\n" + "=" * 60)
    print("OPTIMIZATION TIPS FOR H100")
    print("=" * 60)
    print("1. Use FP16 precision - H100 has 2x throughput with FP16")
    print("2. Enable CUDA graphs for fixed input sizes")
    print("3. Use larger batch sizes when possible")
    print("4. Consider INT8 quantization for even more speed")
    print("5. Profile your specific use case with Nsight Systems")


if __name__ == "__main__":
    main()
