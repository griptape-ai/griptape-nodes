import torch
import torch._dynamo
import torch._inductor
import os
import platform
import functools
from pathlib import Path
from typing import Callable, Any, Optional


class TorchCompileOptimizer:
    """Torch.compile optimizer with aggressive settings and persistent caching."""
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize torch.compile optimizer with caching.
        
        Args:
            cache_dir: Directory for torch.compile cache. If None, uses default.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).parent / "torch_compile_cache"
        self.setup_caching()
        self.setup_aggressive_compile_settings()
    
    def setup_caching(self):
        """Setup persistent caching for torch.compile to reduce cold start times."""
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set cache directory for FX graph cache
        os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(self.cache_dir)
        
        # Enable FX graph caching (if available)
        if hasattr(torch._inductor.config, 'fx_graph_cache'):
            torch._inductor.config.fx_graph_cache = True
        
        # Enable triton caching
        os.environ["TRITON_CACHE_DIR"] = str(self.cache_dir / "triton")
        
        # Set cache size limits (if available)
        if hasattr(torch._inductor.config, 'fx_graph_cache_size_mb'):
            torch._inductor.config.fx_graph_cache_size_mb = 1024  # 1GB cache
        
        # Set dynamo cache size limit
        os.environ["TORCH_DYNAMO_CONFIG_CACHE_SIZE_LIMIT"] = "1024"
        
        # Windows-specific fixes
        if platform.system() == "Windows":
            # Disable problematic features on Windows
            os.environ["TORCHINDUCTOR_ASYNC_COMPILE"] = "0"
            # Use synchronous compilation
            if hasattr(torch._inductor.config, 'async_compile'):
                torch._inductor.config.async_compile = False
        
        print(f"Torch.compile cache directory: {self.cache_dir}")
        
    def setup_aggressive_compile_settings(self):
        """Configure aggressive torch.compile settings for maximum performance."""
        
        def safe_set_config(obj, attr, value):
            """Safely set config attribute if it exists."""
            if hasattr(obj, attr):
                setattr(obj, attr, value)
                return True
            return False
        
        enabled_settings = []
        
        # Inductor optimizations (fast ones only)
        if safe_set_config(torch._inductor.config, 'aggressive_fusion', True):
            enabled_settings.append("aggressive_fusion")
        if safe_set_config(torch._inductor.config, 'max_fusion_size', 64):  # Smaller for faster compile
            enabled_settings.append("max_fusion_size=64")
        # Skip coordinate_descent_tuning - very slow to compile
        if safe_set_config(torch._inductor.config, 'force_fuse_int_mm_with_mul', True):
            enabled_settings.append("force_fuse_int_mm_with_mul")
        
        # Memory optimizations
        if safe_set_config(torch._inductor.config, 'memory_planning', True):
            enabled_settings.append("memory_planning")
        if safe_set_config(torch._inductor.config, 'inplace_buffers', True):
            enabled_settings.append("inplace_buffers")
        
        # CUDA optimizations
        if torch.cuda.is_available():
            if hasattr(torch._inductor.config, 'triton'):
                if safe_set_config(torch._inductor.config.triton, 'unique_kernel_names', True):
                    enabled_settings.append("triton.unique_kernel_names")
                if safe_set_config(torch._inductor.config.triton, 'cudagraphs', True):
                    enabled_settings.append("triton.cudagraphs")
            
            if hasattr(torch._inductor.config, 'cuda'):
                if safe_set_config(torch._inductor.config.cuda, 'enable_cuda_lto', True):
                    enabled_settings.append("cuda.enable_cuda_lto")
            
        # Advanced optimizations (but limit slow ones)
        if safe_set_config(torch._inductor.config, 'pattern_matcher', True):
            enabled_settings.append("pattern_matcher")
        if safe_set_config(torch._inductor.config, 'pre_grad_fusion', True):
            enabled_settings.append("pre_grad_fusion")
        if safe_set_config(torch._inductor.config, 'post_grad_fusion', True):
            enabled_settings.append("post_grad_fusion")
        
        # Enable experimental features (fast ones only)
        if safe_set_config(torch._inductor.config, 'epilogue_fusion', True):
            enabled_settings.append("epilogue_fusion")
        # Skip split_reductions - it's slow to compile
        
        # Speed up compilation (but disable on Windows due to subprocess issues)
        if platform.system() != "Windows":
            if safe_set_config(torch._inductor.config, 'compile_threads', 8):
                enabled_settings.append("compile_threads=8")
        else:
            # On Windows, use single-threaded compilation to avoid subprocess issues
            if safe_set_config(torch._inductor.config, 'compile_threads', 1):
                enabled_settings.append("compile_threads=1 (Windows)")
            # Disable async compilation on Windows
            os.environ["TORCHINDUCTOR_ASYNC_COMPILE"] = "0"
        
        print(f"Enabled torch.compile settings: {enabled_settings}")
    
    def get_compile_config(self, mode: str = "fast") -> dict:
        """
        Get compile configuration based on performance mode.
        
        Args:
            mode: Compilation mode:
                - "fast": Quick compilation (~30s), good performance  
                - "default": Balanced compilation and performance
                - "reduce-overhead": Good performance, faster than max-autotune
                - "max-autotune": Maximum performance, slowest compilation (2+ min)
                - "max-autotune-no-cudagraphs": Like max-autotune without cudagraphs
                - "custom": Custom options
        
        Returns:
            Dictionary with compile configuration
        """
        configs = {
            "default": {
                "mode": "default",
                "dynamic": False,
                "fullgraph": False,
                "options": None
            },
            "reduce-overhead": {
                "mode": "reduce-overhead", 
                "dynamic": False,
                "fullgraph": True,
                "options": None
            },
            "max-autotune": {
                "mode": "max-autotune",
                "dynamic": False, 
                "fullgraph": False,  # Allow graph breaks for faster compilation
                "options": None
            },
            "max-autotune-no-cudagraphs": {
                "mode": "max-autotune-no-cudagraphs",
                "dynamic": False,
                "fullgraph": True, 
                "options": None
            },
            "fast": {
                "mode": "reduce-overhead",
                "dynamic": False,
                "fullgraph": False,  # Allow breaks for speed
                "options": None
            },
            "custom": {
                "mode": None,
                "dynamic": False,
                "fullgraph": False,  # Faster compilation
                "options": {
                    "triton.cudagraphs": True,
                    "epilogue_fusion": True,
                    "max_autotune": False,  # Disable slow autotuning
                    "max_autotune_gemm": False
                }
            }
        }
        
        return configs.get(mode, configs["fast"])
    
    def compile_transformer(self, transformer_model: torch.nn.Module, mode: str = "fast") -> torch.nn.Module:
        """
        Compile transformer model with aggressive optimizations.
        
        Args:
            transformer_model: The transformer model to compile
            mode: Compilation mode
            
        Returns:
            Compiled transformer model
        """
        config = self.get_compile_config(mode)
        
        print(f"Compiling transformer with mode: {mode}")
        print(f"Config: {config}")
        
        # Apply torch.compile with configuration
        compile_kwargs = {
            "dynamic": config["dynamic"],
            "fullgraph": config["fullgraph"]
        }
        
        # Add mode OR options, but not both
        if config["mode"] is not None:
            compile_kwargs["mode"] = config["mode"]
        elif config["options"] is not None:
            compile_kwargs["options"] = config["options"]
        
        compiled_model = torch.compile(transformer_model, **compile_kwargs)
        
        return compiled_model
    
    def compile_individual_layers(self, transformer_model: torch.nn.Module, mode: str = "max-autotune") -> torch.nn.Module:
        """
        Compile individual transformer layers for better granular optimization.
        
        Args:
            transformer_model: The transformer model
            mode: Compilation mode
            
        Returns:
            Model with compiled individual layers
        """
        config = self.get_compile_config(mode)
        
        print(f"Compiling individual transformer layers with mode: {mode}")
        
        # Look for transformer blocks and compile them individually
        for name, module in transformer_model.named_children():
            if any(layer_type in name.lower() for layer_type in ['block', 'layer', 'transformer']):
                print(f"Compiling layer: {name}")
                
                # Apply torch.compile with configuration
                compile_kwargs = {
                    "dynamic": config["dynamic"],
                    "fullgraph": config["fullgraph"]
                }
                
                # Add mode OR options, but not both
                if config["mode"] is not None:
                    compile_kwargs["mode"] = config["mode"]
                elif config["options"] is not None:
                    compile_kwargs["options"] = config["options"]
                
                compiled_layer = torch.compile(module, **compile_kwargs)
                setattr(transformer_model, name, compiled_layer)
        
        return transformer_model
    
    def compile_attention_layers(self, transformer_model: torch.nn.Module, mode: str = "max-autotune") -> torch.nn.Module:
        """
        Compile only attention layers for targeted optimization.
        
        Args:
            transformer_model: The transformer model
            mode: Compilation mode
            
        Returns:
            Model with compiled attention layers
        """
        config = self.get_compile_config(mode)
        
        print(f"Compiling attention layers with mode: {mode}")
        
        def compile_attention_recursive(module, prefix=""):
            for name, child in module.named_children():
                full_name = f"{prefix}.{name}" if prefix else name
                
                # Check if this is an attention layer
                if any(attn_type in name.lower() for attn_type in ['attn', 'attention', 'self_attn', 'cross_attn']):
                    print(f"Compiling attention layer: {full_name}")
                    
                    # Apply torch.compile with configuration
                    compile_kwargs = {
                        "dynamic": config["dynamic"],
                        "fullgraph": config["fullgraph"]
                    }
                    
                    # Add mode OR options, but not both
                    if config["mode"] is not None:
                        compile_kwargs["mode"] = config["mode"]
                    elif config["options"] is not None:
                        compile_kwargs["options"] = config["options"]
                    
                    compiled_child = torch.compile(child, **compile_kwargs)
                    setattr(module, name, compiled_child)
                else:
                    # Recursively search for attention layers
                    compile_attention_recursive(child, full_name)
        
        compile_attention_recursive(transformer_model)
        return transformer_model
    
    def warmup_compiled_model(self, compiled_model: torch.nn.Module, sample_inputs: dict, num_warmup: int = 3):
        """
        Warmup compiled model to trigger compilation and populate cache.
        
        Args:
            compiled_model: The compiled model
            sample_inputs: Sample inputs for warmup
            num_warmup: Number of warmup iterations
        """
        print(f"Warming up compiled model with {num_warmup} iterations...")
        
        successful_warmups = 0
        with torch.no_grad():
            for i in range(num_warmup):
                print(f"Warmup iteration {i+1}/{num_warmup}")
                try:
                    _ = compiled_model(**sample_inputs)
                    torch.cuda.synchronize()
                    successful_warmups += 1
                    print(f"  ✓ Warmup iteration {i+1} successful")
                except Exception as e:
                    print(f"  ✗ Warmup iteration {i+1} failed: {type(e).__name__}")
                    # Don't print full error to reduce noise
                    if "dimension" in str(e).lower() or "shape" in str(e).lower():
                        print(f"    Likely dimension mismatch - sample inputs may not match model")
                    
        print(f"Warmup completed: {successful_warmups}/{num_warmup} iterations successful")
        return successful_warmups > 0
    
    def get_cache_info(self) -> dict:
        """Get information about the compile cache."""
        cache_info = {
            "cache_dir": str(self.cache_dir),
            "cache_exists": self.cache_dir.exists(),
            "fx_graph_cache_enabled": getattr(torch._inductor.config, 'fx_graph_cache', False),
        }
        
        if self.cache_dir.exists():
            cache_files = list(self.cache_dir.glob("**/*"))
            cache_info["num_cache_files"] = len(cache_files)
            cache_info["cache_size_mb"] = sum(f.stat().st_size for f in cache_files if f.is_file()) / (1024 * 1024)
        
        return cache_info
    
    def clear_cache(self):
        """Clear the torch.compile cache."""
        import shutil
        
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            print(f"Cleared cache directory: {self.cache_dir}")
        
        # Clear dynamo cache
        torch._dynamo.reset()
        print("Cleared dynamo cache")


def create_sample_inputs_for_flux(batch_size: int = 1, height: int = 512, width: int = 512, device: str = "cuda") -> dict:
    """Create sample inputs for Flux transformer for warmup."""
    # More conservative sizes that should work with actual Flux model
    latent_height = height // 8  # 64
    latent_width = width // 8    # 64
    seq_len = latent_height * latent_width  # 4096
    
    # Use actual Flux transformer input dimensions
    sample_inputs = {
        "hidden_states": torch.randn(batch_size, seq_len, 64, dtype=torch.bfloat16, device=device),  # Reduced channel dim
        "encoder_hidden_states": torch.randn(batch_size, 256, 4096, dtype=torch.bfloat16, device=device),  # T5 embeddings
        "pooled_projections": torch.randn(batch_size, 768, dtype=torch.bfloat16, device=device),  # CLIP pooled
        "timestep": torch.randn(batch_size, 256, dtype=torch.bfloat16, device=device),  # Timestep embedding
    }
    
    return sample_inputs


if __name__ == "__main__":
    # Example usage
    optimizer = TorchCompileOptimizer()
    
    # Print cache info
    cache_info = optimizer.get_cache_info()
    print(f"Cache info: {cache_info}")
    
    # Test with a simple model
    class SimpleTransformer(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = torch.nn.ModuleList([
                torch.nn.TransformerEncoderLayer(512, 8, batch_first=True)
                for _ in range(6)
            ])
        
        def forward(self, x):
            for layer in self.layers:
                x = layer(x)
            return x
    
    model = SimpleTransformer().cuda().bfloat16()
    
    # Test different compilation strategies
    print("\n" + "="*60)
    print("Testing torch.compile strategies")
    print("="*60)
    
    # Strategy 1: Compile whole model
    compiled_model = optimizer.compile_transformer(model, mode="max-autotune")
    
    # Strategy 2: Compile individual layers
    # model_layers = optimizer.compile_individual_layers(model.clone(), mode="max-autotune")
    
    # Create sample inputs and warmup
    sample_inputs = {"x": torch.randn(2, 100, 512, dtype=torch.bfloat16, device="cuda")}
    optimizer.warmup_compiled_model(compiled_model, sample_inputs)
    
    print("\nCache info after warmup:")
    cache_info = optimizer.get_cache_info()
    print(f"Cache info: {cache_info}")