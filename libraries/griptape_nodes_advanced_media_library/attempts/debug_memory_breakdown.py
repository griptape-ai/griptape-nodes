"""
Debug script to see memory breakdown of FluxKontextPipeline components
"""

import torch
from flux_complete_comparison import FluxComparison

def analyze_component_memory(pipeline):
    """Analyze memory usage of each pipeline component"""
    
    print("\nCOMPONENT MEMORY BREAKDOWN:")
    print("-" * 50)
    
    total_memory = 0
    
    components = [
        ('transformer', 'Transformer'),
        ('vae', 'VAE'),
        ('text_encoder', 'Text Encoder 1'),
        ('text_encoder_2', 'Text Encoder 2'),
        ('scheduler', 'Scheduler'),
        ('tokenizer', 'Tokenizer'),
        ('tokenizer_2', 'Tokenizer 2')
    ]
    
    for attr_name, display_name in components:
        if hasattr(pipeline.pipeline, attr_name):
            component = getattr(pipeline.pipeline, attr_name)
            if component is not None and hasattr(component, 'parameters'):
                component_memory = 0
                quantized_params = 0
                total_params = 0
                
                for param in component.parameters():
                    param_size = param.numel() * param.element_size()
                    component_memory += param_size
                    total_params += 1
                    
                    if hasattr(param, 'quant_state'):
                        quantized_params += 1
                
                component_memory_gb = component_memory / (1024**3)
                total_memory += component_memory_gb
                
                quant_status = f"({quantized_params}/{total_params} quantized)" if total_params > 0 else ""
                print(f"{display_name:<20}: {component_memory_gb:>8.2f} GB {quant_status}")
    
    print("-" * 50)
    print(f"{'Total':<20}: {total_memory:>8.2f} GB")
    
    return total_memory

def compare_quantization_memory():
    """Compare memory breakdown between 8-bit and 4-bit"""
    
    configs = [
        {'name': '8bit', 'bits': 8},
        {'name': '4bit', 'bits': 4}
    ]
    
    for config in configs:
        print(f"\n{'='*60}")
        print(f"ANALYZING {config['bits']}-BIT QUANTIZATION")
        print(f"{'='*60}")
        
        pipeline = FluxComparison(
            config_name=f"{config['name']}_analysis",
            torch_dtype=torch.bfloat16,
            quantization_bits=config['bits']
        )
        
        # Load pipeline
        pipeline.load_pipeline()
        
        # Analyze components
        total_calculated = analyze_component_memory(pipeline)
        
        # Compare with actual GPU memory
        actual_memory = pipeline.get_gpu_memory_usage()['allocated']
        
        print(f"\nCalculated total: {total_calculated:.2f} GB")
        print(f"Actual GPU usage: {actual_memory:.2f} GB")
        print(f"Difference: {actual_memory - total_calculated:.2f} GB (overhead)")
        
        # Clean up
        pipeline.clear_gpu_memory()
        del pipeline

if __name__ == "__main__":
    compare_quantization_memory()