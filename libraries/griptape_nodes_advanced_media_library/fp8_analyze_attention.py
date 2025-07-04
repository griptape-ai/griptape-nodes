from fp8_load import load_pipeline
import torch.nn as nn

def analyze_transformer_structure(module, name="", depth=0, max_depth=3):
    """Recursively analyze transformer structure to find attention layers."""
    indent = "  " * depth
    
    if depth > max_depth:
        return
    
    print(f"{indent}{name}: {module.__class__.__name__}")
    
    # Look for attention-related modules
    if any(keyword in name.lower() for keyword in ['attn', 'attention', 'self_attn']):
        print(f"{indent}  *** ATTENTION MODULE FOUND ***")
        
        # Print all Linear layers in attention module
        for child_name, child in module.named_children():
            if isinstance(child, nn.Linear):
                print(f"{indent}    Linear: {child_name} -> in_features={child.in_features}, out_features={child.out_features}")
    
    # Continue recursively
    for child_name, child in module.named_children():
        if isinstance(child, nn.Module):
            analyze_transformer_structure(child, f"{name}.{child_name}" if name else child_name, depth + 1, max_depth)


def find_all_linear_layers(module, name="", path_filter=None):
    """Find all Linear layers, optionally filtered by path."""
    linear_layers = []
    
    for child_name, child in module.named_modules():
        if isinstance(child, nn.Linear):
            full_path = f"{name}.{child_name}" if name else child_name
            if path_filter is None or any(filter_str in full_path.lower() for filter_str in path_filter):
                linear_layers.append((full_path, child))
    
    return linear_layers


def count_layer_types(module):
    """Count different layer types."""
    counts = {}
    for name, child in module.named_modules():
        layer_type = child.__class__.__name__
        counts[layer_type] = counts.get(layer_type, 0) + 1
    return counts


if __name__ == "__main__":
    print("Loading pipeline to analyze transformer structure...")
    pipeline = load_pipeline()
    
    print("\n" + "="*60)
    print("TRANSFORMER STRUCTURE ANALYSIS")
    print("="*60)
    
    analyze_transformer_structure(pipeline.transformer, "transformer")
    
    print("\n" + "="*60)
    print("LAYER TYPE COUNTS")
    print("="*60)
    
    layer_counts = count_layer_types(pipeline.transformer)
    for layer_type, count in sorted(layer_counts.items()):
        print(f"{layer_type}: {count}")
    
    print("\n" + "="*60)
    print("LINEAR LAYER SUMMARY")
    print("="*60)
    
    all_linear = find_all_linear_layers(pipeline.transformer, "transformer")
    print(f"Total Linear layers: {len(all_linear)}")
    
    attention_linear = find_all_linear_layers(pipeline.transformer, "transformer", 
                                            path_filter=['attn', 'attention', 'qkv', 'to_q', 'to_k', 'to_v', 'q_proj', 'k_proj', 'v_proj'])
    
    print(f"Attention Linear layers: {len(attention_linear)}")
    
    print("\nFirst 10 attention layers:")
    for path, layer in attention_linear[:10]:
        print(f"  {path}: {layer.in_features}→{layer.out_features}")
    
    if len(attention_linear) > 10:
        print(f"  ... and {len(attention_linear) - 10} more")
    
    print("\nFirst 10 non-attention linear layers:")
    non_attention = [item for item in all_linear if item not in attention_linear]
    for path, layer in non_attention[:10]:
        print(f"  {path}: {layer.in_features}→{layer.out_features}")
    
    if len(non_attention) > 10:
        print(f"  ... and {len(non_attention) - 10} more")