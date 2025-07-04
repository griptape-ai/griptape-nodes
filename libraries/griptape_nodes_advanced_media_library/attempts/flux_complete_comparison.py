"""
Complete FluxKontextPipeline comparison:
- Default (no quantization, float32)
- bfloat16 
- 8-bit quantization
- 4-bit quantization
"""

import os
import time
import warnings
from pathlib import Path
from typing import Optional, Union, Dict, Any
import gc

import torch
import psutil

try:
    import bitsandbytes as bnb
    HAS_BITSANDBYTES = True
except ImportError:
    HAS_BITSANDBYTES = False
    raise ImportError("bitsandbytes required. Install with: pip install bitsandbytes")

try:
    from diffusers import FluxKontextPipeline
    from diffusers.quantizers import PipelineQuantizationConfig
    from diffusers.utils import logging
    HAS_DIFFUSERS = True
except ImportError:
    HAS_DIFFUSERS = False
    raise ImportError("Please install diffusers from main branch: pip install git+https://github.com/huggingface/diffusers.git")

# Configure logging
logging.set_verbosity_error()
warnings.filterwarnings("ignore", category=UserWarning)

class FluxComparison:
    """Complete FluxKontextPipeline comparison with different precisions"""
    
    def __init__(self, 
                 model_id: str = "black-forest-labs/FLUX.1-Kontext-dev",
                 config_name: str = "default",
                 torch_dtype: torch.dtype = torch.float32,
                 quantization_bits: Optional[int] = None):
        
        self.model_id = model_id
        self.config_name = config_name
        self.torch_dtype = torch_dtype
        self.quantization_bits = quantization_bits
        self.pipeline = None
        
        self._setup_cuda()
        
    def _setup_cuda(self):
        """Setup CUDA optimizations"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            
            # Enable TensorFloat-32 for Ampere+ GPUs
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            
    def get_gpu_memory_usage(self) -> Dict[str, float]:
        """Get current GPU memory usage"""
        if not torch.cuda.is_available():
            return {'allocated': 0, 'reserved': 0, 'free': 0}
            
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        free = total - reserved
        
        return {
            'allocated': allocated,
            'reserved': reserved, 
            'free': free,
            'total': total
        }
        
    def clear_gpu_memory(self) -> Dict[str, float]:
        """Clear GPU memory and return memory usage before/after"""
        if not torch.cuda.is_available():
            return {'before': 0, 'after': 0}
            
        # Get memory before clearing
        before = torch.cuda.memory_allocated() / 1024**3
        
        # Clear pipeline
        if hasattr(self, 'pipeline') and self.pipeline is not None:
            del self.pipeline
            self.pipeline = None
            
        # Force garbage collection
        gc.collect()
        
        # Clear CUDA cache multiple times for better cleanup
        for _ in range(3):
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            time.sleep(0.1)  # Small delay to help with cleanup
        
        # Get memory after clearing
        after = torch.cuda.memory_allocated() / 1024**3
        
        return {
            'before': before,
            'after': after,
            'cleared': before - after
        }
        
    def _create_quantization_config(self) -> PipelineQuantizationConfig:
        """Create quantization configuration"""
        if self.quantization_bits == 8:
            quant_backend = 'bitsandbytes_8bit'
            quant_kwargs = {
                'bnb_8bit_use_double_quant': True,
            }
        elif self.quantization_bits == 4:
            quant_backend = 'bitsandbytes_4bit'
            quant_kwargs = {
                'bnb_4bit_compute_dtype': torch.bfloat16,
                'bnb_4bit_use_double_quant': True,
                'bnb_4bit_quant_type': 'nf4',
            }
        else:
            raise ValueError(f"Unsupported quantization bits: {self.quantization_bits}. Use 4 or 8.")
            
        return PipelineQuantizationConfig(
            quant_backend=quant_backend,
            quant_kwargs=quant_kwargs,
            components_to_quantize=['transformer', 'text_encoder', 'text_encoder_2']  # Quantize more components
        )
        
    def load_pipeline(self):
        """Load pipeline with specified configuration"""
        print(f"Loading {self.config_name} configuration...")
        print(f"  Model: {self.model_id}")
        print(f"  Torch dtype: {self.torch_dtype}")
        if self.quantization_bits:
            print(f"  Quantization: {self.quantization_bits}-bit")
        
        # Get memory before loading
        memory_before = self.get_gpu_memory_usage()
        print(f"  GPU Memory before: {memory_before['allocated']:.2f} GB allocated")
        
        # Clear and reset memory tracking
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        
        start_time = time.time()
        
        # Load with or without quantization
        if self.quantization_bits is not None:
            quantization_config = self._create_quantization_config()
            
            self.pipeline = FluxKontextPipeline.from_pretrained(
                self.model_id,
                torch_dtype=self.torch_dtype,
                quantization_config=quantization_config,
                device_map="balanced",
                use_safetensors=True,
            )
        else:
            self.pipeline = FluxKontextPipeline.from_pretrained(
                self.model_id,
                torch_dtype=self.torch_dtype,
                use_safetensors=True,
            )
            
            # Move to CUDA if no device_map was used (non-quantized models)
            if torch.cuda.is_available():
                print("  Moving pipeline to CUDA...")
                self.pipeline = self.pipeline.to("cuda")
        
        # Enable attention slicing for memory efficiency
        self.pipeline.enable_attention_slicing()
        
        load_time = time.time() - start_time
        print(f"  Pipeline loaded in {load_time:.2f}s")
        
        # Get memory after loading
        memory_after = self.get_gpu_memory_usage()
        model_memory_usage = memory_after['allocated'] - memory_before['allocated']
        
        print(f"  GPU Memory after: {memory_after['allocated']:.2f} GB allocated")
        print(f"  Model memory usage: {model_memory_usage:.2f} GB")
        print(f"  GPU Memory free: {memory_after['free']:.2f} GB")
        
        return model_memory_usage
        
    def generate_and_time(self, 
                         prompt: str,
                         num_inference_steps: int = 20,
                         height: int = 1024,
                         width: int = 1024) -> Dict[str, Any]:
        """Generate image and measure timing"""
        
        if self.pipeline is None:
            raise ValueError("Pipeline not loaded. Call load_pipeline() first.")
            
        # Clear cache before generation
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            
        start_time = time.time()
        
        with torch.no_grad():
            result = self.pipeline(
                prompt=prompt,
                num_inference_steps=num_inference_steps,
                height=height,
                width=width,
                guidance_scale=2.5
            )
            
        generation_time = time.time() - start_time
        
        # Memory stats
        if torch.cuda.is_available():
            memory_peak = torch.cuda.max_memory_allocated() / 1024**3
            memory_current = torch.cuda.memory_allocated() / 1024**3
        else:
            memory_peak = 0
            memory_current = 0
            
        return {
            'image': result.images[0],
            'generation_time': generation_time,
            'memory_peak_gb': memory_peak,
            'memory_current_gb': memory_current,
            'steps': num_inference_steps
        }
        
    def benchmark_inference_speed(self, 
                                 prompt: str = "A futuristic city at sunset",
                                 num_tests: int = 2) -> Dict[str, Any]:
        """Benchmark inference speed"""
        
        print(f"\n=== Benchmarking {self.config_name} ===")
        
        results = []
        
        for i in range(num_tests):
            print(f"\nRun {i+1}/{num_tests}:")
            
            result = self.generate_and_time(
                prompt=prompt,
                num_inference_steps=20,
                height=1024,
                width=1024
            )
            
            print(f"  Generation time: {result['generation_time']:.2f}s")
            print(f"  Memory peak: {result['memory_peak_gb']:.2f} GB")
            print(f"  Memory current: {result['memory_current_gb']:.2f} GB")
            
            results.append(result)
            
            # Save first result
            if i == 0:
                result['image'].save(f"output_{self.config_name}_run{i+1}.png")
                
        # Calculate statistics
        times = [r['generation_time'] for r in results]
        
        stats = {
            'config_name': self.config_name,
            'torch_dtype': str(self.torch_dtype),
            'quantization_bits': self.quantization_bits,
            'first_inference_time': times[0],
            'subsequent_times': times[1:] if len(times) > 1 else [],
            'average_time': sum(times) / len(times),
            'speed_improvement': (times[0] - times[1]) / times[0] * 100 if len(times) > 1 else 0,
            'memory_peak_gb': results[0]['memory_peak_gb'],
            'memory_current_gb': results[0]['memory_current_gb']
        }
        
        return stats

def test_all_configurations():
    """Test all configurations: default, bfloat16, 8-bit, 4-bit"""
    
    # Configuration definitions
    configs = [
        {
            'name': 'default_float32',
            'torch_dtype': torch.float32,
            'quantization_bits': None,
            'description': 'Default (float32, no quantization)'
        },
        {
            'name': 'bfloat16',
            'torch_dtype': torch.bfloat16,
            'quantization_bits': None,
            'description': 'bfloat16 precision'
        },
        {
            'name': '8bit_quantized',
            'torch_dtype': torch.bfloat16,
            'quantization_bits': 8,
            'description': '8-bit quantization'
        },
        {
            'name': '4bit_quantized',
            'torch_dtype': torch.bfloat16,
            'quantization_bits': 4,
            'description': '4-bit quantization'
        }
    ]
    
    results = {}
    
    # Initial memory state
    if torch.cuda.is_available():
        initial_memory = torch.cuda.memory_allocated() / 1024**3
        print(f"Initial GPU memory: {initial_memory:.2f} GB")
        print(f"Total GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    
    for config in configs:
        print("\n" + "=" * 100)
        print(f"TESTING: {config['description'].upper()}")
        print("=" * 100)
        
        try:
            pipeline = FluxComparison(
                config_name=config['name'],
                torch_dtype=config['torch_dtype'],
                quantization_bits=config['quantization_bits']
            )
            
            model_memory = pipeline.load_pipeline()
            benchmark_result = pipeline.benchmark_inference_speed()
            benchmark_result['model_memory_gb'] = model_memory
            
            results[config['name']] = benchmark_result
            
            # Clear memory and verify
            print(f"\nClearing {config['name']} from memory...")
            clear_result = pipeline.clear_gpu_memory()
            print(f"Memory before clear: {clear_result['before']:.2f} GB")
            print(f"Memory after clear: {clear_result['after']:.2f} GB")
            print(f"Memory freed: {clear_result['cleared']:.2f} GB")
            
            del pipeline
            gc.collect()
            
            # Additional cleanup attempts
            for _ in range(3):
                torch.cuda.empty_cache()
                time.sleep(0.2)
            
        except Exception as e:
            print(f"{config['name']} failed: {e}")
            results[config['name']] = {'error': str(e)}
            
            # Still try to clear memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        # Verify memory cleanup
        if torch.cuda.is_available():
            current_memory = torch.cuda.memory_allocated() / 1024**3
            print(f"Current memory after cleanup: {current_memory:.2f} GB")
            if current_memory > initial_memory + 1.0:  # Allow 1GB tolerance
                print("WARNING: Memory may not be fully cleared!")
                # Force additional cleanup
                for _ in range(5):
                    torch.cuda.empty_cache()
                    gc.collect()
                    time.sleep(0.1)
                current_memory = torch.cuda.memory_allocated() / 1024**3
                print(f"Memory after forced cleanup: {current_memory:.2f} GB")
    
    # Print comprehensive comparison
    print("\n" + "=" * 100)
    print("COMPREHENSIVE COMPARISON")
    print("=" * 100)
    
    successful_results = {k: v for k, v in results.items() if 'error' not in v}
    
    if successful_results:
        print("\nConfiguration Summary:")
        print("-" * 80)
        print(f"{'Config':<20} {'Model Mem':<12} {'1st Gen':<10} {'2nd Gen':<10} {'Speedup':<10}")
        print("-" * 80)
        
        for config_name, result in successful_results.items():
            speedup = f"{result['speed_improvement']:.1f}%" if result['speed_improvement'] > 0 else "N/A"
            second_time = f"{result['subsequent_times'][0]:.2f}s" if result['subsequent_times'] else "N/A"
            
            print(f"{config_name:<20} {result['model_memory_gb']:<11.2f}G {result['first_inference_time']:<9.2f}s "
                  f"{second_time:<10} {speedup:<10}")
        
        # Memory efficiency analysis
        print(f"\nMemory Efficiency Analysis:")
        print("-" * 50)
        if 'default_float32' in successful_results:
            baseline = successful_results['default_float32']['model_memory_gb']
            for config_name, result in successful_results.items():
                if config_name != 'default_float32':
                    savings = baseline - result['model_memory_gb']
                    savings_percent = (savings / baseline) * 100
                    print(f"{config_name}: {savings:.2f} GB saved ({savings_percent:.1f}%)")
    
    # Print any errors
    error_results = {k: v for k, v in results.items() if 'error' in v}
    if error_results:
        print(f"\nFailed Configurations:")
        print("-" * 40)
        for config_name, result in error_results.items():
            print(f"{config_name}: {result['error']}")
    
    return results

if __name__ == "__main__":
    test_all_configurations()