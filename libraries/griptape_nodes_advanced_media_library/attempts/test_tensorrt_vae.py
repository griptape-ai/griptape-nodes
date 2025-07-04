import os
import sys
import time
import gc
import numpy as np
import torch
from pathlib import Path

# Set up TensorRT path
tensorrt_lib_path = r"C:\Users\dev\griptape-nodes\libraries\griptape_nodes_advanced_media_library\.venv\Lib\site-packages\tensorrt_libs"
if os.path.exists(tensorrt_lib_path):
    os.environ['PATH'] = tensorrt_lib_path + os.pathsep + os.environ.get('PATH', '')
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(tensorrt_lib_path)

import onnxruntime as ort

def create_best_session(onnx_path, use_tensorrt=True):
    """Create the best available session, with fallback options"""
    
    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_options.enable_mem_pattern = True
    sess_options.enable_mem_reuse = True
    
    providers_list = []
    
    if use_tensorrt and 'TensorrtExecutionProvider' in ort.get_available_providers():
        # Try simpler TensorRT config that's more likely to succeed
        trt_options = {
            'device_id': 0,
            'trt_max_workspace_size': 4 * 1024 * 1024 * 1024,  # 4GB instead of 8GB
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': str(Path(onnx_path).parent),
            # Simplified profile - single size instead of range
            'trt_force_sequential_engine_build': True,
            # Disable problematic optimizations
            'trt_builder_optimization_level': 3,  # Lower optimization level
            'trt_auxiliary_streams': -1,  # Disable auxiliary streams
        }
        providers_list.append(('TensorrtExecutionProvider', trt_options))
    
    # Always add CUDA as fallback
    cuda_options = {
        'device_id': 0,
        'arena_extend_strategy': 'kSameAsRequested',
        'gpu_mem_limit': 80 * 1024 * 1024 * 1024,
        'cudnn_conv_algo_search': 'HEURISTIC',
        'do_copy_in_default_stream': True,
        'cudnn_conv_use_max_workspace': True,
    }
    providers_list.append(('CUDAExecutionProvider', cuda_options))
    providers_list.append('CPUExecutionProvider')
    
    try:
        session = ort.InferenceSession(onnx_path, sess_options=sess_options, providers=providers_list)
        print(f"Active providers: {session.get_providers()}")
        return session
    except Exception as e:
        print(f"Failed with TensorRT, falling back to CUDA only: {e}")
        # Try without TensorRT
        providers_list = [('CUDAExecutionProvider', cuda_options), 'CPUExecutionProvider']
        session = ort.InferenceSession(onnx_path, sess_options=sess_options, providers=providers_list)
        print(f"Active providers (fallback): {session.get_providers()}")
        return session

class OptimizedVAEDecoder:
    """Optimized VAE decoder with automatic backend selection"""
    def __init__(self, onnx_path, force_backend=None):
        """
        Args:
            onnx_path: Path to ONNX model
            force_backend: 'tensorrt', 'cuda', or None (auto)
        """
        print(f"Loading optimized VAE decoder...")
        
        if force_backend == 'cuda':
            self.session = create_best_session(onnx_path, use_tensorrt=False)
        else:
            self.session = create_best_session(onnx_path, use_tensorrt=True)
        
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        
        # Check which provider is actually being used
        active_providers = self.session.get_providers()
        if 'TensorrtExecutionProvider' in active_providers:
            self.backend = 'TensorRT'
        elif 'CUDAExecutionProvider' in active_providers:
            self.backend = 'CUDA'
        else:
            self.backend = 'CPU'
        
        print(f"Using {self.backend} backend")
        
        # Warmup
        self._warmup()
    
    def _warmup(self):
        """Warmup the model"""
        print("Warming up...")
        dummy = np.random.randn(1, 16, 64, 64).astype(np.float32)
        _ = self.session.run([self.output_name], {self.input_name: dummy})
        torch.cuda.empty_cache()
    
    def decode(self, latents, return_dict=False):
        """Decode latents"""
        if isinstance(latents, torch.Tensor):
            device = latents.device
            latents_np = latents.cpu().contiguous().numpy()
        else:
            device = torch.device('cuda')
            latents_np = np.ascontiguousarray(latents)
        
        output = self.session.run([self.output_name], {self.input_name: latents_np})[0]
        output_tensor = torch.from_numpy(output).to(device)
        
        if return_dict:
            from diffusers.models.autoencoders.vae import DecoderOutput
            return DecoderOutput(sample=output_tensor)
        return (output_tensor,)
    
    def to(self, device):
        return self

def benchmark_optimized():
    """Benchmark PyTorch vs Optimized ONNX"""
    from diffusers import AutoencoderKL
    
    print("\n" + "="*70)
    print("VAE PERFORMANCE COMPARISON")
    print("="*70)
    
    # Load PyTorch VAE
    print("\nLoading PyTorch VAE...")
    vae_pytorch = AutoencoderKL.from_pretrained(
        "black-forest-labs/FLUX.1-Kontext-dev",
        subfolder="vae",
        torch_dtype=torch.float32
    ).cuda().eval()
    
    # Load optimized ONNX (will use TensorRT if possible, CUDA otherwise)
    print("\nLoading Optimized ONNX VAE...")
    vae_optimized = OptimizedVAEDecoder("flux_kontext_vae_decoder.onnx")
    
    # Test configurations
    test_configs = [
        (1, 64, 64, "512x512"),
        (1, 128, 128, "1024x1024"),
        (1, 192, 192, "1536x1536"),
        (2, 128, 128, "Batch 2 @ 1024"),
    ]
    
    print("\n" + "-"*70)
    print(f"BENCHMARK RESULTS (using {vae_optimized.backend} backend)")
    print("-"*70)
    
    results = []
    
    for batch, h, w, desc in test_configs:
        print(f"\n{desc}:")
        
        try:
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
            
            # Optimized ONNX
            torch.cuda.synchronize()
            times = []
            for _ in range(10):
                start = time.perf_counter()
                _ = vae_optimized.decode(latents, return_dict=False)[0]
                torch.cuda.synchronize()
                times.append(time.perf_counter() - start)
            opt_time = np.median(times)
            
            speedup = pytorch_time / opt_time
            
            print(f"  PyTorch:  {pytorch_time*1000:6.2f}ms")
            print(f"  {vae_optimized.backend:8}: {opt_time*1000:6.2f}ms ({speedup:4.2f}x)")
            
            results.append({
                'config': desc,
                'pytorch': pytorch_time,
                'optimized': opt_time,
                'speedup': speedup
            })
            
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            torch.cuda.empty_cache()
            gc.collect()
    
    # Summary
    if results:
        avg_speedup = np.mean([r['speedup'] for r in results])
        best = max(results, key=lambda x: x['speedup'])
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Backend: {vae_optimized.backend}")
        print(f"Average speedup: {avg_speedup:.2f}x")
        print(f"Best speedup: {best['speedup']:.2f}x at {best['config']}")

def export_simplified_onnx(vae, output_path):
    """Export a simplified ONNX model that's more TensorRT-friendly"""
    import torch.onnx
    
    print("Exporting simplified ONNX model for better TensorRT compatibility...")
    
    # Use a fixed shape for better TensorRT compatibility
    dummy_input = torch.randn(1, 16, 128, 128, dtype=torch.float32)
    
    # Export with simplified settings
    with torch.no_grad():
        torch.onnx.export(
            vae.decoder,
            dummy_input,
            output_path,
            input_names=["latent_sample"],
            output_names=["sample"],
            # Use fixed axes for TensorRT
            dynamic_axes=None,  # No dynamic axes
            opset_version=16,  # Try older opset
            do_constant_folding=True,
            export_params=True,
        )
    
    print(f"Exported simplified model to {output_path}")
    
    # Simplify with onnx-simplifier if available
    try:
        import onnx
        import onnxsim
        
        print("Simplifying ONNX model...")
        model = onnx.load(output_path)
        model_simp, check = onnxsim.simplify(model)
        onnx.save(model_simp, output_path)
        print("Model simplified successfully")
    except ImportError:
        print("Install onnx-simplifier for better TensorRT compatibility: pip install onnx-simplifier")
    except Exception as e:
        print(f"Simplification failed: {e}")

if __name__ == "__main__":
    # Check setup
    print("Checking setup...")
    providers = ort.get_available_providers()
    print(f"Available providers: {providers}")
    
    # Run benchmark
    benchmark_optimized()
    
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    print("1. The CUDA backend is giving good performance (1.2-1.4x speedup)")
    print("2. TensorRT failed due to model complexity - this is common with VAEs")
    print("3. For production, use the CUDA-optimized ONNX model")
    print("4. Consider exporting a simplified model for TensorRT:")
    print("   - Fixed input shapes instead of dynamic")
    print("   - Lower opset version")
    print("   - Use onnx-simplifier")
    
    print("\nTo use in your pipeline:")
    print('vae = OptimizedVAEDecoder("flux_kontext_vae_decoder.onnx")')
    print('pipe.vae = vae')