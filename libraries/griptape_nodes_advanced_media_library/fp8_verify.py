from fp8_load import load_pipeline, load_fp8_pipeline

def count_layer_types(module):
    """Count different layer types."""
    counts = {}
    for name, child in module.named_modules():
        layer_type = child.__class__.__name__
        counts[layer_type] = counts.get(layer_type, 0) + 1
    return counts

print("Loading standard pipeline...")
standard_pipeline = load_pipeline()
standard_counts = count_layer_types(standard_pipeline.transformer)

print("Loading FP8 pipeline...")
fp8_pipeline = load_fp8_pipeline()
fp8_counts = count_layer_types(fp8_pipeline.transformer)

print("\n" + "="*50)
print("LAYER TYPE COMPARISON")
print("="*50)

all_types = set(standard_counts.keys()) | set(fp8_counts.keys())
for layer_type in sorted(all_types):
    std_count = standard_counts.get(layer_type, 0)
    fp8_count = fp8_counts.get(layer_type, 0)
    if std_count != fp8_count:
        print(f"{layer_type}: {std_count} → {fp8_count}")

print(f"\nLinear: {standard_counts.get('Linear', 0)} → {fp8_counts.get('Linear', 0)}")
print(f"FP8Linear: {standard_counts.get('FP8Linear', 0)} → {fp8_counts.get('FP8Linear', 0)}")
print(f"Total converted: {fp8_counts.get('FP8Linear', 0)} / {standard_counts.get('Linear', 0)} ({100 * fp8_counts.get('FP8Linear', 0) / standard_counts.get('Linear', 0):.1f}%)")